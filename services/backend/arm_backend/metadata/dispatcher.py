import asyncio
import contextvars
import logging
import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx

from arm_backend.identity.sources.registry import (
    fingerprint_sources,
    hint_sources_setting,
    online_source_ids,
    sources_for,
)
from arm_backend.metadata.base import LookupError, MetadataResult
from arm_backend.metadata.sources import Kind, OnlineSource, build_online_sources, capability
from arm_backend.metadata.tmdb import TMDBClient
from arm_common import Config, DiscType
from arm_common.schemas import ScanResult

logger = logging.getLogger("arm_backend.metadata.dispatcher")

PROVIDER_TIMEOUT_SECONDS = 8.0

DISPATCH_TIMEOUT_SECONDS = 25.0

_YEAR_SUFFIX_RE = re.compile(r"[\s_\-.]*\(?\d{4}\)?\s*$")
# A release year at the end of a disc-hint title (`THE_OFFICE_2005_S1_D2` ->
# "the office 2005"). Capped at 2029 so a title ending in a later number
# (BLADE_RUNNER_2049) is never shortened.
_HINT_YEAR_SUFFIX_RE = re.compile(r"\s*\(?(?:19\d{2}|20[0-2]\d)\)?$")
# DVDs commonly bake the broadcast standard into the volume label
# (e.g. `THE_MATRIX_NTSC` or `MOVIE_NTSC_1999`). It's noise for title
# matching — strip it before the underscore-to-space pass so OMDB/TMDB
# searches don't see "MATRIX NTSC".
_NTSC_TOKEN_RE = re.compile(r"_NTSC(?=[_.\s\-]|$)", re.IGNORECASE)
# Blu-rays bake disc-format branding into the title/label the same way.
# v2 stripped a fixed set of "Blu-rayTM" suffixes off the BDMV disc title
# (see arm/ripper/main/identify.py); reproduce that here generically so a
# label like `MOVIE_BLU_RAY`, `Movie - Blu-rayTM`, or `BLURAY` loses the
# branding before lookup. The optional `tm|™` covers the trademark glyph
# in either pre- or post-ASCII-normalised form.
_BLURAY_BRANDING_RE = re.compile(r"[\s_\-]*blu[\s_\-]?ray(?:\s*(?:tm|™))?", re.IGNORECASE)
# `_BD` (Blu-ray Disc) token, mirroring the `_NTSC` treatment.
_BD_TOKEN_RE = re.compile(r"_BD(?=[_.\s\-]|$)", re.IGNORECASE)

# One entry per source the dispatcher tried (or skipped) during an identify
# call: why the automatic match missed, shown on the job's review card.
AttemptStep = Literal["fingerprint", "disc_id", "title", "imdb"]
AttemptKind = Literal["movie", "tv", "music"]
AttemptOutcome = Literal["hit", "miss", "timeout", "error", "not_configured", "no_sources"]


@dataclass
class _AttemptLog:
    """One identify call's attempts, plus the skips it already recorded."""

    attempts: list[dict[str, Any]] = field(default_factory=list)
    skips_seen: set[tuple[str | None, str, str | None, str]] = field(default_factory=set)


# The current identify call's log. A context variable, not an attribute of the
# shared dispatcher: each request handler runs in its own asyncio task with its
# own copy of the context, so two discs identified at once never see (or
# suppress) each other's attempts.
_attempt_log: contextvars.ContextVar[_AttemptLog | None] = contextvars.ContextVar("identify_attempt_log", default=None)


def _normalize_volume_label(label: str) -> tuple[str, int | None]:
    # Fold compatibility glyphs WITHOUT dropping non-ASCII: NFKC turns
    # "Blu-ray™" → "Blu-rayTM" and full-width forms → half-width, but keeps
    # accents and non-Latin scripts intact ("Amélie", "Война и мир", "君の名は"
    # all survive) so worldwide titles still reach the providers. This is
    # deliberately NOT the NFKD→ASCII strip `slugify` uses — that targets
    # ASCII filename tokens; here we must preserve the real searchable title.
    cleaned = unicodedata.normalize("NFKC", label)
    cleaned = _NTSC_TOKEN_RE.sub("", cleaned)
    cleaned = _BD_TOKEN_RE.sub("", cleaned)
    cleaned = _BLURAY_BRANDING_RE.sub("", cleaned)
    cleaned = cleaned.replace("_", " ").replace(".", " ").strip()
    year: int | None = None
    m = re.search(r"(\d{4})", cleaned)
    if m:
        candidate = int(m.group(1))
        if 1900 <= candidate <= 2100:
            year = candidate
    cleaned = _YEAR_SUFFIX_RE.sub("", cleaned).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned, year


class MetadataDispatcher:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        sources: Mapping[str, OnlineSource] | None = None,
    ) -> None:
        self._http = http
        self._sources: dict[str, OnlineSource] = dict(sources) if sources is not None else build_online_sources(http)

    @property
    def last_attempts(self) -> list[dict[str, Any]]:
        """The attempts of the identify / identify_from_imdb call last made in
        the caller's context (task). Each call starts a fresh list in its own
        context (see `_attempt_log`), so concurrent identifies on this shared
        dispatcher are isolated; read it in the same task, after (or while
        cancelling) the call."""
        log = _attempt_log.get()
        return log.attempts if log is not None else []

    @property
    def sources(self) -> Mapping[str, OnlineSource]:
        """The online-source registry (shared with the metadata routes)."""
        return self._sources

    async def aclose(self) -> None:
        await self._http.aclose()

    async def identify(
        self,
        scan: ScanResult,
        cfg: Config,
        *,
        title_hint: str | None = None,
        title_hint_is_tv: bool = False,
        prefer_tv: bool = False,
    ) -> MetadataResult | None:
        self._reset_attempts()
        if scan.disc_type in (DiscType.DATA, DiscType.UNKNOWN):
            return None

        if scan.disc_type == DiscType.CD:
            return await self._identify_cd(scan, cfg)

        hit = await self._identify_video(
            scan, cfg, title_hint=title_hint, title_hint_is_tv=title_hint_is_tv, prefer_tv=prefer_tv
        )
        return await self.fill_external_ids(hit, cfg)

    async def _identify_cd(self, scan: ScanResult, cfg: Config) -> MetadataResult | None:
        if not scan.musicbrainz_disc_id:
            return None
        disc_id = scan.musicbrainz_disc_id
        for source in self._walk(cfg, "music", "disc_id", disc_id):
            lookup = capability(source, "lookup_disc_id")
            if lookup is None:
                continue
            hit = await self._call(
                source.id, lookup(cfg, disc_id, scan.cd_toc), step="disc_id", kind="music", detail=disc_id
            )
            if hit is not None:
                return hit
        return None

    async def _identify_video(
        self,
        scan: ScanResult,
        cfg: Config,
        *,
        title_hint: str | None = None,
        title_hint_is_tv: bool = False,
        prefer_tv: bool = False,
    ) -> MetadataResult | None:
        # Fingerprint sources first (the community crc64 → title DB). A hit
        # beats fuzzy title matching because the fingerprint is unique to the
        # disc and there's no false-positive risk.
        crc64 = next(
            (fp.value for fp in scan.fingerprints if fp.algo == "crc64" and fp.value),
            None,
        )
        if crc64:
            for source in fingerprint_sources(cfg, self._sources):
                lookup = capability(source, "lookup_fingerprint")
                if lookup is None:
                    continue
                hit = await self._call(
                    source.id, lookup(cfg, "crc64", crc64), step="fingerprint", kind=None, detail=crc64
                )
                if hit is not None:
                    return hit

        # Disc hints (bd_title / label, see arm_backend.identity) supply a
        # cleaner search title than the raw volume label — try it first, then
        # fall back to the normalized volume-label title. Empty and duplicate
        # (case-insensitive) candidates are skipped so a hint equal to the
        # label title doesn't double the provider calls. A hint that carries
        # a season claim (a season/box-set disc) is TV-shaped: search TV before
        # movie for THAT candidate only. The label-derived candidate keeps the
        # movie-first order. The label candidate's year is computed first so
        # the hint candidate — which has no year of its own — is searched with
        # the same year filter.
        label_title: str | None = None
        label_year: int | None = None
        if scan.volume_label:
            label_title, label_year = _normalize_volume_label(scan.volume_label)
        # D-4: the volume label is a search candidate only while the `label`
        # disc hint is enabled; an operator who ignores disc text gets no
        # label search at all. Its year still narrows the hint candidate.
        label_enabled = "label" in hint_sources_setting(cfg)

        candidates: list[tuple[str, int | None, bool]] = []
        if title_hint and title_hint.strip():
            hint = title_hint.strip()
            candidates.append((hint, label_year, title_hint_is_tv))
            # A trailing year can be the release year (THE_OFFICE_2005_S1_D2)
            # or part of the title (WONDER_WOMAN_1984, 1917), and the label
            # cannot tell which. Search the hint as given first, then without
            # the year.
            if without_year := _HINT_YEAR_SUFFIX_RE.sub("", hint).rstrip(" :,"):
                candidates.append((without_year, label_year, title_hint_is_tv))
        if label_title and label_enabled:
            candidates.append((label_title, label_year, False))
        seen: set[str] = set()
        unique: list[tuple[str, int | None, bool]] = []
        for title, year, tv_first in candidates:
            key = title.casefold()
            if key not in seen:
                seen.add(key)
                unique.append((title, year, tv_first))
        if prefer_tv:
            # The disc itself is TV-shaped (arm_common.disc_shape): search TV for
            # every candidate before any movie, so one candidate's movie
            # fallback can't win while another candidate would have found the
            # series.
            for kind in ("tv", "movie"):
                for title, year, _ in unique:
                    hit = await self._search_kind(title, year, cfg, kind)
                    if hit is not None:
                        return hit
            return None
        for title, year, tv_first in unique:
            kinds: tuple[Kind, Kind] = ("tv", "movie") if tv_first else ("movie", "tv")
            for kind in kinds:
                hit = await self._search_kind(title, year, cfg, kind)
                if hit is not None:
                    return hit
        return None

    async def _search_kind(self, title: str, year: int | None, cfg: Config, kind: Kind) -> MetadataResult | None:
        """One kind: every enabled source for it, in the operator's order."""
        for source in self._walk(cfg, kind, "title", title):
            search = capability(source, "search_title")
            if search is None:
                continue
            hit = await self._call(source.id, search(cfg, kind, title, year), step="title", kind=kind, detail=title)
            if hit is not None:
                return hit
        return None

    def has_imdb_lookup(self, cfg: Config, kind: Kind) -> bool:
        """True when an enabled source for `kind` can resolve an IMDb id (D-1)."""
        return any(capability(s, "lookup_imdb") is not None for s in sources_for(cfg, kind, self._sources))

    async def identify_from_imdb(self, imdb_id: str, cfg: Config, *, kind: Kind = "movie") -> MetadataResult | None:
        """Exact-ID identify for a TheDiscDB-matched disc (spec D-1): the
        enabled sources for `kind`, in rank order, first hit wins. None when
        the id is empty, no source offers the lookup, or every source misses
        (the caller falls back to the fuzzy identify in that last case)."""
        self._reset_attempts()
        if not imdb_id:
            return None
        for source in self._walk(cfg, kind, "imdb", imdb_id):
            lookup = capability(source, "lookup_imdb")
            if lookup is None:
                continue
            hit = await self._call(source.id, lookup(cfg, imdb_id), step="imdb", kind=kind, detail=imdb_id)
            if hit is not None:
                hit.payload.setdefault("imdb_id", imdb_id)
                return await self.fill_external_ids(hit, cfg)
        return None

    async def fill_external_ids(self, hit: MetadataResult | None, cfg: Config) -> MetadataResult | None:
        """Fill the ids a hit lacks so the stored identity lets every episode
        source find the show (spec S-10). A TMDb hit gets IMDb/TVDB ids from
        its `external_ids`; any other movie/TV hit with an IMDb id gets its
        TMDb id from TMDb /find through the tmdb source, when that source is
        configured. Ids already in the payload win; a failure or
        timeout (bounded by PROVIDER_TIMEOUT_SECONDS) changes nothing."""
        if hit is None or hit.kind not in ("movie", "tv"):
            return hit
        if hit.provider == "tmdb":
            return await self._fill_from_tmdb_external_ids(hit, cfg)
        imdb = hit.payload.get("imdb_id")
        if hit.payload.get("tmdb_id") or not isinstance(imdb, str) or not imdb:
            return hit
        tmdb = self._sources.get("tmdb")
        if tmdb is None or tmdb.configured(cfg) is not None:
            return hit
        lookup = capability(tmdb, "lookup_imdb")
        if lookup is None:
            return hit
        found = await self._call("tmdb", lookup(cfg, imdb))
        if found is None or found.kind != hit.kind or found.payload.get("id") is None:
            return hit
        hit.payload["tmdb_id"] = str(found.payload["id"])
        return hit

    async def _fill_from_tmdb_external_ids(self, hit: MetadataResult, cfg: Config) -> MetadataResult:
        kind = hit.kind
        if not cfg.tmdb_api_key or kind not in ("movie", "tv"):
            return hit
        tmdb_id = hit.payload.get("id")
        if tmdb_id is None:
            return hit
        try:
            found = await asyncio.wait_for(
                TMDBClient(cfg.tmdb_api_key, self._http).get_external_id_map(tmdb_id, kind),
                timeout=PROVIDER_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.info("metadata.tmdb_external_ids timeout id=%s", tmdb_id)
            return hit
        for key, value in found.items():
            hit.payload.setdefault(key, value)
        return hit

    def _reset_attempts(self) -> None:
        _attempt_log.set(_AttemptLog())

    def _log(self) -> _AttemptLog:
        log = _attempt_log.get()
        if log is None:
            log = _AttemptLog()
            _attempt_log.set(log)
        return log

    def _record(
        self,
        source: str | None,
        step: AttemptStep,
        kind: AttemptKind | None,
        outcome: AttemptOutcome,
        detail: str | None,
    ) -> None:
        self._log().attempts.append(
            {"source": source, "step": step, "kind": kind, "outcome": outcome, "detail": detail}
        )

    def _walk(self, cfg: Config, kind: AttemptKind, step: AttemptStep, detail: str | None) -> tuple[OnlineSource, ...]:
        """`sources_for(cfg, kind)`, recording the listed sources skipped for a
        missing key (`not_configured`) and, when nothing is listed for the kind
        at all, one `no_sources` entry. Each skip is recorded once per call,
        however many search candidates walk the same list."""
        walk = sources_for(cfg, kind, self._sources)
        skipped = False
        for sid in online_source_ids(cfg, kind):
            source = self._sources.get(sid)
            if source is None or kind not in source.media_types or source.configured(cfg) is None:
                continue
            skipped = True
            self._record_skip(sid, step, kind, "not_configured", detail)
        if not walk and not skipped:
            self._record_skip(None, step, kind, "no_sources", detail)
        return walk

    def _record_skip(
        self, source: str | None, step: AttemptStep, kind: AttemptKind, outcome: AttemptOutcome, detail: str | None
    ) -> None:
        key = (source, step, kind, outcome)
        seen = self._log().skips_seen
        if key not in seen:
            seen.add(key)
            self._record(source, step, kind, outcome, detail)

    async def _call(  # type: ignore[no-untyped-def]
        self,
        source_id: str,
        coro,
        *,
        step: AttemptStep | None = None,
        kind: AttemptKind | None = None,
        detail: str | None = None,
    ) -> MetadataResult | None:
        """Await one provider call. With a `step`, the outcome is recorded in
        `last_attempts` (id enrichment passes none: it is not a match)."""
        outcome: AttemptOutcome
        try:
            result: MetadataResult | None = await asyncio.wait_for(coro, timeout=PROVIDER_TIMEOUT_SECONDS)
            if result is not None:
                # The source id keys provider_raw and identity.provider.
                result.provider = source_id
            outcome = "miss" if result is None else "hit"
            if step == "disc_id" and result is not None and (result.payload or {}).get("toc_match") == "fuzzy":
                detail = "matched by track layout"
        except asyncio.TimeoutError:
            logger.info("metadata.%s timeout", source_id)
            result, outcome = None, "timeout"
        except LookupError as e:
            logger.info("metadata.%s miss: %s", source_id, e)
            result, outcome = None, "error"
        if step is not None:
            self._record(source_id, step, kind, outcome, detail)
        return result
