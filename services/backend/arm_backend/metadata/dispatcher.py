import asyncio
import logging
import re
import unicodedata
from collections.abc import Mapping

import httpx

from arm_backend.identity.sources.registry import fingerprint_sources, sources_for
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
        if scan.disc_type in (DiscType.DATA, DiscType.UNKNOWN):
            return None

        if scan.disc_type == DiscType.CD:
            return await self._identify_cd(scan, cfg)

        hit = await self._identify_video(
            scan, cfg, title_hint=title_hint, title_hint_is_tv=title_hint_is_tv, prefer_tv=prefer_tv
        )
        return await self._with_tmdb_ids(hit, cfg)

    async def _identify_cd(self, scan: ScanResult, cfg: Config) -> MetadataResult | None:
        if not scan.musicbrainz_disc_id:
            return None
        for source in sources_for(cfg, "music", self._sources):
            lookup = capability(source, "lookup_disc_id")
            if lookup is None:
                continue
            hit = await self._call(source.id, lookup(cfg, scan.musicbrainz_disc_id))
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
                hit = await self._call(source.id, lookup(cfg, "crc64", crc64))
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
        if label_title:
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
        for source in sources_for(cfg, kind, self._sources):
            search = capability(source, "search_title")
            if search is None:
                continue
            hit = await self._call(source.id, search(cfg, kind, title, year))
            if hit is not None:
                return hit
        return None

    async def identify_from_imdb(self, imdb_id: str, cfg: Config) -> MetadataResult | None:
        """Exact-ID identify for a TheDiscDB-matched disc. TMDb's /find
        endpoint resolves an IMDb id for both movies and TV; requires a TMDb
        key. Returns None (caller falls back to fuzzy identify) otherwise.
        PR 2 (spec D-1) replaces the fixed TMDb choice with a walk over
        `sources_for`."""
        tmdb = self._sources.get("tmdb")
        if not imdb_id or tmdb is None or tmdb.configured(cfg) is not None:
            return None
        lookup = capability(tmdb, "lookup_imdb")
        if lookup is None:
            return None
        hit = await self._call(tmdb.id, lookup(cfg, imdb_id))
        if hit is not None:
            hit.payload.setdefault("imdb_id", imdb_id)
        return await self._with_tmdb_ids(hit, cfg)

    async def _with_tmdb_ids(self, hit: MetadataResult | None, cfg: Config) -> MetadataResult | None:
        """Fill a TMDb hit's IMDb / TVDB ids (one `external_ids` call) so the
        stored identity lets every episode source find the show (spec 3.4).
        Ids already in the payload win; a failed or timed-out call (bounded
        by PROVIDER_TIMEOUT_SECONDS) changes nothing. The last direct client
        use in this module; PR 2b generalizes it to `fill_external_ids`."""
        if hit is None or hit.provider != "tmdb" or hit.kind not in ("movie", "tv") or not cfg.tmdb_api_key:
            return hit
        tmdb_id = hit.payload.get("id")
        if tmdb_id is None:
            return hit
        try:
            found = await asyncio.wait_for(
                TMDBClient(cfg.tmdb_api_key, self._http).get_external_id_map(tmdb_id, hit.kind),
                timeout=PROVIDER_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            logger.info("metadata.tmdb_external_ids timeout id=%s", tmdb_id)
            return hit
        for key, value in found.items():
            hit.payload.setdefault(key, value)
        return hit

    async def _call(self, source_id: str, coro) -> MetadataResult | None:  # type: ignore[no-untyped-def]
        try:
            result: MetadataResult | None = await asyncio.wait_for(coro, timeout=PROVIDER_TIMEOUT_SECONDS)
            if result is not None:
                # The source id keys provider_raw and identity.provider.
                result.provider = source_id
            return result
        except asyncio.TimeoutError:
            logger.info("metadata.%s timeout", source_id)
            return None
        except LookupError as e:
            logger.info("metadata.%s miss: %s", source_id, e)
            return None
