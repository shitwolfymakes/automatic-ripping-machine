import asyncio
import contextvars
import logging
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

import httpx

from arm_backend.metadata.base import LookupError, MetadataResult
from arm_backend.metadata.match.evidence import TITLE_SOURCES, DiscEvidence, evidence_from_scan
from arm_backend.metadata.match.retrieve import PROVIDER_TIMEOUT_SECONDS, Outcome, Retriever, Step, plan_kinds
from arm_backend.metadata.match.run import explain_exact, identify_weighted
from arm_backend.metadata.musicbrainz import TOC_NOT_FOUND
from arm_backend.metadata.source_selection import fingerprint_sources, online_source_ids, sources_for
from arm_backend.metadata.sources import Kind, OnlineSource, build_online_sources, capability
from arm_backend.metadata.tmdb import TMDBClient
from arm_common import Config, DiscType
from arm_common.schemas import IdentifyMatch, ScanResult

logger = logging.getLogger("arm_backend.metadata.dispatcher")

DISPATCH_TIMEOUT_SECONDS = 25.0

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


@dataclass(frozen=True)
class Identification:
    """What one identify concluded: the hit to apply (None for a shortlist or a miss) and, for a video disc,
    the weighted search's breakdown of why (`metadata_json.identify_match`)."""

    result: MetadataResult | None
    match: IdentifyMatch | None = None


class MetadataDispatcher:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        sources: Mapping[str, OnlineSource] | None = None,
    ) -> None:
        self._http = http
        self._sources: dict[str, OnlineSource] = dict(sources) if sources is not None else build_online_sources(http)
        # One retriever, so its one-hour cache and per-source limits serve every identify.
        self._retriever = Retriever(self._sources, timeout=PROVIDER_TIMEOUT_SECONDS, on_attempt=self._on_attempt)

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
        self, scan: ScanResult, cfg: Config, *, hint_ids: Collection[str] = TITLE_SOURCES, iso_name: str | None = None
    ) -> Identification:
        """Identify a disc. `hint_ids`: the enabled disc-hint sources (`bd_title`, `iso_name`, `label`); a
        disabled one contributes no text to the weighted search. `iso_name`: an ISO rip's file name."""
        self._reset_attempts()
        if scan.disc_type in (DiscType.DATA, DiscType.UNKNOWN):
            return Identification(None)

        if scan.disc_type == DiscType.CD:
            return Identification(await self._identify_cd(scan, cfg))

        ev = self._evidence(scan, hint_ids, iso_name)
        hit = await self.identify_from_fingerprint(scan, cfg)
        if hit is not None:
            hit = await self.fill_external_ids(hit, cfg) or hit
            return Identification(hit, explain_exact(ev, hit, "fingerprint"))
        for kind in plan_kinds(ev.p_tv):
            self._walk(cfg, kind, "title", ev.titles[0].parsed.core if ev.titles else None)
        weighted = await identify_weighted(self._retriever, cfg, ev)
        return Identification(await self.fill_external_ids(weighted.result, cfg), weighted.match)

    @staticmethod
    def _evidence(scan: ScanResult, hint_ids: Collection[str], iso_name: str | None) -> DiscEvidence:
        return evidence_from_scan(scan, iso_name=iso_name, now=datetime.now(timezone.utc), enabled=hint_ids)

    def explain_exact(
        self,
        scan: ScanResult,
        hit: MetadataResult,
        *,
        how: str,
        hint_ids: Collection[str],
        iso_name: str | None = None,
    ) -> Identification:
        """An exact hit found outside `identify` (TheDiscDB's release) with the text score the search would give
        it, for the card to flag a mapping the disc's own text does not support (D68). The hit applies either way."""
        return Identification(hit, explain_exact(self._evidence(scan, hint_ids, iso_name), hit, how))

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

    async def identify_from_fingerprint(self, scan: ScanResult, cfg: Config) -> MetadataResult | None:
        """The disc's fingerprint sources only: today the keyless
        community CRC64 database. Split out of `identify` so a caller that
        already holds an exact disc-map title can still consult it — it needs
        no API key, so it is the one online step a keyless install has — without
        also running the fuzzy title search that would outrank that title."""
        crc64 = next((fp.value for fp in scan.fingerprints if fp.algo == "crc64" and fp.value), None)
        if not crc64:
            return None
        for source in fingerprint_sources(cfg, self._sources):
            lookup = capability(source, "lookup_fingerprint")
            if lookup is None:
                continue
            hit = await self._call(source.id, lookup(cfg, "crc64", crc64), step="fingerprint", kind=None, detail=crc64)
            if hit is not None:
                return hit
        return None

    def has_imdb_lookup(self, cfg: Config, kind: Kind) -> bool:
        """True when an enabled source for `kind` can resolve an IMDb id."""
        return any(capability(s, "lookup_imdb") is not None for s in sources_for(cfg, kind, self._sources))

    async def identify_from_imdb(self, imdb_id: str, cfg: Config, *, kind: Kind = "movie") -> MetadataResult | None:
        """Exact-ID identify for a TheDiscDB-matched disc: the
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
        source find the show. A TMDb hit gets IMDb/TVDB ids from
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
        if "imdb_id" in hit.payload and "tvdb_id" in hit.payload:
            # A detail call already carried the ids (the retriever's runtime lookup does).
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

    def _on_attempt(self, source_id: str, kind: Kind, step: Step, outcome: Outcome, detail: str) -> None:
        """One call the retriever made, as an attempt on the identify call in the current task."""
        self._record(source_id, "title", kind, outcome, detail if step == "list" else f"details {detail}")

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
            if str(e) == TOC_NOT_FOUND:
                # The fuzzy TOC fallback ran and nothing fit: an answer, not a fault.
                outcome, detail = "miss", "no release fits the track layout"
        if step is not None:
            self._record(source_id, step, kind, outcome, detail)
        return result
