"""Collect the provider candidates a disc's queries find, merged across providers (spec 3).

One identify spends at most `MAX_LIST_CALLS` list searches, `MAX_DETAIL_CALLS` detail calls and one year-filtered
TMDb retry (D63, D70). A list call is each query against each enabled source for a kind, through the providers'
own `search_candidates` capability; a detail call fills the runtime of a promising candidate that has none.
Calls run in parallel, each source behind its own semaphore, and a source that fails drops out of that step.
Answers are cached for an hour (errors never), so a re-identify of the same disc costs no provider call.

Providers' results are merged into one `Candidate` per title: on a shared IMDb id, else on the same content
tokens, kind and a year within one. Pure scoring lives in `score.py`; this module only fetches and merges.
"""

from __future__ import annotations

import asyncio
import copy
import re
from collections.abc import Callable, Coroutine, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from arm_common import Config
from arm_common.enums import MediaType

from arm_backend.metadata.base import LookupError, LookupTimeout, MetadataResult
from arm_backend.metadata.details_cache import TtlCache
from arm_backend.metadata.match.evidence import DiscEvidence
from arm_backend.metadata.match.queries import Query
from arm_backend.metadata.match.score import Candidate, rank_candidates, score_candidate
from arm_backend.metadata.match.tokens import candidate_tokens
from arm_backend.metadata.source_selection import sources_for
from arm_backend.metadata.sources import Kind, OnlineSource, capability

MAX_LIST_CALLS = 12
MAX_DETAIL_CALLS = 3
MAX_YEAR_RETRIES = 1
LIST_LIMIT = 10
# A candidate is worth a detail call only when its text, year and kind already score this much (spec 3.2).
DETAIL_PRESCORE_MIN = 25.0
# A year at least this reliable that no unfiltered result carries gets one year-filtered TMDb retry.
YEAR_RETRY_MIN_RELIABILITY = 0.8
# p_tv at or above (below) these searches TV (movies) only.
TV_ONLY_P_TV = 0.75
MOVIE_ONLY_P_TV = 0.25

PROVIDER_TIMEOUT_SECONDS = 8.0
CACHE_TTL_SECONDS = 3600.0
CACHE_ENTRIES = 512
# Concurrent calls per source (TVmaze asks for at most 20 requests per 10 s).
SEMAPHORE_LIMITS: Mapping[str, int] = {"tmdb": 4, "omdb": 2, "tvmaze": 2, "tvdb": 2}
DEFAULT_SEMAPHORE_LIMIT = 2

Step = Literal["list", "detail"]
Outcome = Literal["hit", "miss", "timeout", "error"]
# (source id, kind, step, outcome, detail text): one provider call the retriever made.
AttemptSink = Callable[[str, Kind, Step, Outcome, str], None]

_RUNTIME_MIN_RE = re.compile(r"(\d+)\s*min")
_RUNTIME_HOUR_RE = re.compile(r"(\d+)\s*h")
_EMPTY_IDS = (None, "", "N/A")


def plan_kinds(p_tv: float) -> tuple[Kind, ...]:
    """The kinds to search: TV only for a TV-looking disc, movies only for a movie-looking one, else both."""
    if p_tv >= TV_ONLY_P_TV:
        return ("tv",)
    if p_tv <= MOVIE_ONLY_P_TV:
        return ("movie",)
    return ("movie", "tv")


def other_kind(kinds: Sequence[Kind]) -> Kind | None:
    """The kind the second pass searches: the one the first pass skipped; None when it searched both."""
    if len(kinds) != 1:
        return None
    return "tv" if kinds[0] == "movie" else "movie"


@dataclass
class Budget:
    """What one identify may still spend, and what it spent. Shared by both passes."""

    list_left: int = MAX_LIST_CALLS
    detail_left: int = MAX_DETAIL_CALLS
    retry_left: int = MAX_YEAR_RETRIES
    list_calls: int = 0
    detail_calls: int = 0
    cached: int = 0

    def take_list(self) -> bool:
        if self.list_left <= 0:
            return False
        self.list_left -= 1
        self.list_calls += 1
        return True

    def take_detail(self) -> bool:
        if self.detail_left <= 0:
            return False
        self.detail_left -= 1
        self.detail_calls += 1
        return True

    def take_retry(self) -> bool:
        if self.retry_left <= 0:
            return False
        self.retry_left -= 1
        self.list_calls += 1
        return True


@dataclass(frozen=True)
class Retrieved:
    """A merged candidate and the highest-ranked provider's own result, which an apply reads."""

    candidate: Candidate
    result: MetadataResult


@dataclass
class _Group:
    kind: Kind
    # Source id -> that source's result, in the order the sources first contributed.
    members: dict[str, MetadataResult] = field(default_factory=dict)

    def ids(self) -> dict[str, str]:
        merged: dict[str, str] = {}
        for source_id, result in self.members.items():
            for name, value in ids_of(source_id, result.payload).items():
                merged.setdefault(name, value)
        return merged


def ids_of(source_id: str, payload: Mapping[str, Any]) -> dict[str, str]:
    """The ids a provider's result carries, under the names `tmdb`, `imdb`, `tvdb`, `tvmaze`."""
    out: dict[str, str] = {}
    if source_id == "tmdb" and payload.get("id") not in _EMPTY_IDS:
        out["tmdb"] = str(payload["id"])
    for name, keys in (("imdb", ("imdb_id", "imdbID")), ("tvdb", ("tvdb_id",)), ("tvmaze", ("tvmaze_id",))):
        for key in keys:
            if payload.get(key) not in _EMPTY_IDS:
                out[name] = str(payload[key])
                break
    return out


def _native_id(source_id: str, payload: Mapping[str, Any]) -> str | None:
    """The id a source knows its own entry by (OMDb: the IMDb id)."""
    return ids_of(source_id, payload).get("imdb" if source_id == "omdb" else source_id)


def _positive(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else None


def _omdb_minutes(runtime: Any) -> float | None:
    """OMDb's `Runtime` text: "164 min", "2 h 44 min", "N/A"."""
    if not isinstance(runtime, str):
        return None
    mins = _RUNTIME_MIN_RE.search(runtime)
    hours = _RUNTIME_HOUR_RE.search(runtime)
    total = (int(hours.group(1)) * 60 if hours else 0) + (int(mins.group(1)) if mins else 0)
    return float(total) if total > 0 else None


def _tmdb_minutes(kind: Kind, payload: Mapping[str, Any]) -> float | None:
    if kind == "movie":
        return _positive(payload.get("runtime"))
    episode = payload.get("episode_run_time")
    if isinstance(episode, list) and episode:
        return _positive(episode[0])
    last = payload.get("last_episode_to_air")
    return _positive(last.get("runtime")) if isinstance(last, dict) else None


def runtime_of(source_id: str, kind: Kind, payload: Mapping[str, Any]) -> float | None:
    """The runtime in minutes a provider's result states: a film's length, or a show's episode length."""
    if source_id == "tmdb":
        return _tmdb_minutes(kind, payload)
    if source_id == "omdb":
        return _omdb_minutes(payload.get("Runtime"))
    return _positive(payload.get("averageRuntime")) or _positive(payload.get("runtime"))


def _years_compatible(a: int | None, b: int | None) -> bool:
    return a is None or b is None or abs(a - b) <= 1


def _same_entry(source_id: str, result: MetadataResult, group: _Group) -> bool | None:
    """True when `result` is an entry the group's own source already holds, None when it cannot join the group."""
    held = group.members.get(source_id)
    if held is None:
        return False
    mine, theirs = _native_id(source_id, result.payload), _native_id(source_id, held.payload)
    return True if mine is not None and mine == theirs else None


def _belongs(source_id: str, result: MetadataResult, group: _Group) -> bool:
    imdb = ids_of(source_id, result.payload).get("imdb")
    group_imdb = group.ids().get("imdb")
    if imdb and group_imdb:
        return imdb == group_imdb
    first = next(iter(group.members.values()))
    return _years_compatible(result.year, first.year) and candidate_tokens(result.title) == candidate_tokens(
        first.title
    )


def _add(groups: list[_Group], kind: Kind, source_id: str, result: MetadataResult) -> None:
    """Fold one provider result into the first group it belongs to, or start a new one."""
    result.provider = source_id
    for group in groups:
        if group.kind != kind:
            continue
        same = _same_entry(source_id, result, group)
        if same:
            return
        if same is False and _belongs(source_id, result, group):
            group.members[source_id] = result
            return
    groups.append(_Group(kind, {source_id: result}))


def _remerge(groups: list[_Group]) -> list[_Group]:
    """After details: groups that share an IMDb id are one title."""
    merged: list[_Group] = []
    for group in groups:
        imdb = group.ids().get("imdb")
        target = next(
            (
                m
                for m in merged
                if imdb
                and m.kind == group.kind
                and m.ids().get("imdb") == imdb
                and not set(m.members) & set(group.members)
            ),
            None,
        )
        if target is None:
            merged.append(group)
        else:
            target.members.update(group.members)
    return merged


class Retriever:
    """Fetches and merges candidates for one disc at a time; one instance (and cache) per dispatcher."""

    def __init__(
        self,
        sources: Mapping[str, OnlineSource],
        *,
        cache: TtlCache[Any, Any] | None = None,
        timeout: float = PROVIDER_TIMEOUT_SECONDS,
        on_attempt: AttemptSink | None = None,
    ) -> None:
        self._sources = sources
        self._cache: TtlCache[Any, Any] = cache if cache is not None else TtlCache(CACHE_TTL_SECONDS, CACHE_ENTRIES)
        self._timeout = timeout
        self._sink = on_attempt
        self._semaphores = {
            sid: asyncio.Semaphore(SEMAPHORE_LIMITS.get(sid, DEFAULT_SEMAPHORE_LIMIT)) for sid in sources
        }

    # -- public --------------------------------------------------------------------------------------------------

    async def search(
        self,
        cfg: Config,
        ev: DiscEvidence,
        queries: Sequence[Query],
        kinds: Sequence[Kind],
        budget: Budget,
    ) -> list[Retrieved]:
        """The merged candidates of `queries` over `kinds`, one pass. `budget` carries across passes."""
        groups: list[_Group] = []
        ranks = {kind: {s.id: i for i, s in enumerate(sources_for(cfg, kind, self._sources))} for kind in kinds}
        await self._list_step(cfg, queries, kinds, budget, groups)
        await self._year_retry(cfg, ev, queries, kinds, budget, groups)
        groups = await self._detail_step(cfg, ev, budget, groups)
        return [self._retrieved(g, ranks[g.kind]) for g in groups]

    # -- calls ---------------------------------------------------------------------------------------------------

    def _note(self, source_id: str, kind: Kind, step: Step, outcome: Outcome, detail: str) -> None:
        if self._sink is not None:
            self._sink(source_id, kind, step, outcome, detail)

    async def _guarded(self, source_id: str, kind: Kind, step: Step, detail: str, coro: Any) -> Any:
        """Await one provider call behind its semaphore and timeout. None on a timeout or an error."""
        async with self._semaphores.setdefault(source_id, asyncio.Semaphore(DEFAULT_SEMAPHORE_LIMIT)):
            try:
                result = await asyncio.wait_for(coro, timeout=self._timeout)
            except asyncio.TimeoutError, LookupTimeout:
                self._note(source_id, kind, step, "timeout", detail)
                return None
            except LookupError:
                self._note(source_id, kind, step, "error", detail)
                return None
        self._note(source_id, kind, step, "hit" if result else "miss", detail)
        return result

    @staticmethod
    def _list_key(source_id: str, kind: Kind, text: str, year: int | None) -> tuple[Any, ...]:
        return ("list", source_id, kind, tuple(sorted(candidate_tokens(text))), year)

    def _cached(self, key: tuple[Any, ...], budget: Budget) -> Any:
        found = self._cache.get(key)
        if found is None:
            return None
        budget.cached += 1
        return copy.deepcopy(found)

    def _remember(self, key: tuple[Any, ...], value: Any) -> None:
        self._cache.put(key, copy.deepcopy(value))

    async def _list_call(
        self, source: OnlineSource, cfg: Config, kind: Kind, text: str, year: int | None
    ) -> list[MetadataResult] | None:
        search = capability(source, "search_candidates")
        if search is None:
            return None
        extra: dict[str, Any] = {"year": year} if year is not None else {}
        found: list[MetadataResult] | None = await self._guarded(
            source.id, kind, "list", text, search(cfg, kind, text, LIST_LIMIT, enrich=False, **extra)
        )
        # A successful empty answer is cacheable; a failure is not, and says so by returning None.
        return found

    async def _list_step(
        self, cfg: Config, queries: Sequence[Query], kinds: Sequence[Kind], budget: Budget, groups: list[_Group]
    ) -> None:
        slots: list[tuple[Kind, str, list[MetadataResult] | None, Any]] = []
        for query in queries:
            for kind in kinds:
                for source in sources_for(cfg, kind, self._sources):
                    key = self._list_key(source.id, kind, query.text, None)
                    cached = self._cached(key, budget)
                    if cached is not None:
                        slots.append((kind, source.id, cached, None))
                    elif budget.take_list():
                        slots.append(
                            (kind, source.id, None, (key, self._list_call(source, cfg, kind, query.text, None)))
                        )
        await self._fill(slots, groups)

    async def _fill(
        self, slots: list[tuple[Kind, str, list[MetadataResult] | None, Any]], groups: list[_Group]
    ) -> None:
        pending = [slot[3][1] for slot in slots if slot[3] is not None]
        answers = iter(await asyncio.gather(*pending))
        for kind, source_id, cached, pending_call in slots:
            found = cached
            if pending_call is not None:
                found = next(answers)
                if found is not None:
                    self._remember(pending_call[0], found)
            for result in found or []:
                _add(groups, kind, source_id, result)

    async def _year_retry(
        self,
        cfg: Config,
        ev: DiscEvidence,
        queries: Sequence[Query],
        kinds: Sequence[Kind],
        budget: Budget,
        groups: list[_Group],
    ) -> None:
        """D70: one TMDb movie search filtered by a trusted year, when no unfiltered result carries that year."""
        strong = [y for y in ev.years if y.reliability >= YEAR_RETRY_MIN_RELIABILITY]
        tmdb = next((s for s in sources_for(cfg, "movie", self._sources) if s.id == "tmdb"), None)
        if not strong or not queries or tmdb is None or "movie" not in kinds or budget.retry_left <= 0:
            return
        year = strong[0].year
        if any(m.year == year for g in groups if g.kind == "movie" for m in g.members.values()):
            return
        key = self._list_key("tmdb", "movie", queries[0].text, year)
        found = self._cached(key, budget)
        if found is None:
            if not budget.take_retry():
                return
            found = await self._list_call(tmdb, cfg, "movie", queries[0].text, year)
            if found is not None:
                self._remember(key, found)
        for result in found or []:
            _add(groups, "movie", "tmdb", result)

    # -- details -------------------------------------------------------------------------------------------------

    @staticmethod
    def _has_runtime_evidence(ev: DiscEvidence) -> bool:
        return ev.runtime is not None and bool(ev.runtime.feature_minutes or ev.runtime.episode_minutes)

    def _detail_target(self, cfg: Config, group: _Group) -> tuple[OnlineSource, str] | None:
        """Where to ask for a group's runtime: TMDb by its id, else OMDb by IMDb id, else TVDB. TVmaze needs none."""
        enabled = {s.id for s in sources_for(cfg, group.kind, self._sources)}
        ids = group.ids()
        for source_id, key in (("tmdb", "tmdb"), ("omdb", "imdb"), ("tvdb", "tvdb")):
            source = self._sources.get(source_id)
            if source is not None and source_id in enabled and source_id in group.members and key in ids:
                return source, ids[key]
        return None

    def _group_candidate(self, group: _Group, ranks: Mapping[str, int]) -> Candidate:
        ordered = sorted(group.members.items(), key=lambda m: ranks.get(m[0], len(ranks)))
        best_id, best = ordered[0]
        tmdb = group.members.get("tmdb")
        runtime = next(
            (
                r
                for sid, m in ([("tmdb", tmdb)] if tmdb else []) + ordered
                if (r := runtime_of(sid, group.kind, m.payload))
            ),
            None,
        )
        original = None
        for sid, m in ordered:
            raw = m.payload.get("original_title") or m.payload.get("original_name")
            if sid == "tmdb" and isinstance(raw, str) and raw and raw != best.title:
                original = raw
        return Candidate(
            title=best.title,
            kind=MediaType(group.kind),
            year=best.year,
            original_title=original,
            runtime_minutes=runtime,
            providers=tuple(sid for sid, _ in ordered),
            provider_rank=ranks.get(best_id, len(ranks)),
            ids=group.ids(),
        )

    def _retrieved(self, group: _Group, ranks: Mapping[str, int]) -> Retrieved:
        candidate = self._group_candidate(group, ranks)
        best = min(group.members, key=lambda sid: ranks.get(sid, len(ranks)))
        return Retrieved(candidate, group.members[best])

    def _to_enrich(self, cfg: Config, ev: DiscEvidence, budget: Budget, groups: list[_Group]) -> list[_Group]:
        """The top groups, best pre-score first, that lack a runtime and are worth a detail call."""
        if not self._has_runtime_evidence(ev) or budget.detail_left <= 0:
            return []
        scored = []
        for group in groups:
            ranks = {s.id: i for i, s in enumerate(sources_for(cfg, group.kind, self._sources))}
            candidate = self._group_candidate(group, ranks)
            if candidate.runtime_minutes is not None or self._detail_target(cfg, group) is None:
                continue
            scored.append((score_candidate(ev, replace(candidate, runtime_minutes=None)), group))
        keep = [(s, g) for s, g in scored if s.score >= DETAIL_PRESCORE_MIN]
        order = {id(s.candidate): i for i, s in enumerate(rank_candidates(ev, [s.candidate for s, _ in keep]))}
        keep.sort(key=lambda sg: order[id(sg[0].candidate)])
        return [g for _, g in keep[: budget.detail_left]]

    async def _detail_call(
        self, source: OnlineSource, cfg: Config, kind: Kind, provider_id: str
    ) -> MetadataResult | None:
        key = ("detail", source.id, kind, provider_id)
        details = capability(source, "details")
        if details is None:
            return None
        found: MetadataResult | None = await self._guarded(
            source.id, kind, "detail", provider_id, details(cfg, kind, provider_id)
        )
        if found is not None:
            self._remember(key, found)
        return found

    async def _detail_step(self, cfg: Config, ev: DiscEvidence, budget: Budget, groups: list[_Group]) -> list[_Group]:
        targets = self._to_enrich(cfg, ev, budget, groups)
        calls: list[tuple[_Group, str, MetadataResult | None, Coroutine[Any, Any, MetadataResult | None] | None]] = []
        for group in targets:
            target = self._detail_target(cfg, group)
            assert target is not None
            source, provider_id = target
            cached = self._cached(("detail", source.id, group.kind, provider_id), budget)
            if cached is not None:
                calls.append((group, source.id, cached, None))
            elif budget.take_detail():
                calls.append((group, source.id, None, self._detail_call(source, cfg, group.kind, provider_id)))
        answers = iter(await asyncio.gather(*(c[3] for c in calls if c[3] is not None)))
        for group, source_id, cached, pending in calls:
            found = next(answers) if pending is not None else cached
            if found is not None:
                found.provider = source_id
                group.members[source_id] = found
        return _remerge(groups)
