"""Retrieval: kind plan, call budget, merge, cache, details. Providers are answered by hand-built bodies shaped
like each provider's real response, through httpx.MockTransport."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from arm_common import Config
from arm_common.schemas import ScanTitle

from arm_backend.metadata.details_cache import TtlCache
from arm_backend.metadata.match.evidence import DiscEvidence, build_evidence
from arm_backend.metadata.match.queries import Query, build_queries
from arm_backend.metadata.match.retrieve import (
    Budget,
    Retriever,
    ids_of,
    other_kind,
    plan_kinds,
    runtime_of,
)
from arm_backend.metadata.sources import build_online_sources

NOW = datetime(2026, 11, 27, tzinfo=UTC)

TMDB = "api.themoviedb.org"
OMDB = "www.omdbapi.com"
TVMAZE = "api.tvmaze.com"
TVDB = "api4.thetvdb.com"


# --- hand-built provider bodies -------------------------------------------------------------------------------------


def tmdb_movie(tmdb_id: int, title: str, date: str) -> dict[str, Any]:
    return {
        "id": tmdb_id,
        "title": title,
        "original_title": title,
        "release_date": date,
        "overview": "x",
        "poster_path": "/p.jpg",
        "popularity": 1.0,
    }


def tmdb_tv(tmdb_id: int, name: str, date: str) -> dict[str, Any]:
    return {"id": tmdb_id, "name": name, "original_name": name, "first_air_date": date, "poster_path": "/p.jpg"}


def tmdb_movie_detail(tmdb_id: int, title: str, date: str, runtime: int, imdb: str) -> dict[str, Any]:
    return {
        **tmdb_movie(tmdb_id, title, date),
        "runtime": runtime,
        "external_ids": {"imdb_id": imdb, "tvdb_id": None},
        "credits": {"cast": [], "crew": []},
    }


def omdb_row(title: str, year: str, imdb: str, kind: str = "movie") -> dict[str, str]:
    return {"Title": title, "Year": year, "imdbID": imdb, "Type": kind, "Poster": "https://img.example/p.jpg"}


def omdb_detail(title: str, year: str, imdb: str, runtime: str) -> dict[str, str]:
    return {**omdb_row(title, year, imdb), "Runtime": runtime, "Response": "True"}


def tvmaze_show(show_id: int, name: str, premiered: str, runtime: int | None, imdb: str, tvdb: int) -> dict[str, Any]:
    return {
        "score": 1.0,
        "show": {
            "id": show_id,
            "name": name,
            "premiered": premiered,
            "runtime": runtime,
            "averageRuntime": runtime,
            "externals": {"imdb": imdb, "thetvdb": tvdb, "tvrage": None},
            "image": {"medium": "https://img.example/m.jpg"},
        },
    }


def tvdb_row(tvdb_id: int, name: str, year: str, imdb: str) -> dict[str, Any]:
    return {
        "id": f"series-{tvdb_id}",
        "tvdb_id": str(tvdb_id),
        "name": name,
        "year": year,
        "type": "series",
        "remote_ids": [{"id": imdb, "type": 2, "sourceName": "IMDB"}],
        "image_url": "https://img.example/t.jpg",
    }


def _find(table: dict[tuple[str, str], Any], kind: str, query: str) -> Any:
    """The table row for (kind, query), ignoring case: a label's query is upper case."""
    wanted = (kind, query.casefold())
    return next((rows for (k, q), rows in table.items() if (k, q.casefold()) == wanted), None)


def _find_one(table: dict[str, Any], query: str) -> Any:
    return next((rows for q, rows in table.items() if q.casefold() == query.casefold()), None)


class Fake:
    """Answers each provider by host and path from tables the test fills in, and records every request."""

    def __init__(self) -> None:
        self.tmdb_search: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.tmdb_detail: dict[tuple[str, int], dict[str, Any]] = {}
        self.omdb_search: dict[tuple[str, str], list[dict[str, str]]] = {}
        self.omdb_detail: dict[str, dict[str, str]] = {}
        self.tvmaze_search: dict[str, list[dict[str, Any]]] = {}
        self.tvdb_search: dict[str, list[dict[str, Any]]] = {}
        self.fail: dict[str, int | str] = {}
        self.requests: list[httpx.Request] = []
        self.delay = 0.0
        self.in_flight: dict[str, int] = {}
        self.peak: dict[str, int] = {}

    def calls(self, host: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.host == host]

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        self.requests.append(request)
        self.in_flight[host] = self.in_flight.get(host, 0) + 1
        self.peak[host] = max(self.peak.get(host, 0), self.in_flight[host])
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            return self._answer(request)
        finally:
            self.in_flight[host] -= 1

    def _answer(self, request: httpx.Request) -> httpx.Response:
        host = request.url.host
        failure = self.fail.get(host)
        if failure == "timeout":
            raise httpx.ReadTimeout("slow", request=request)
        if isinstance(failure, int):
            return httpx.Response(failure, json={})
        handler: dict[str, Callable[[httpx.Request], httpx.Response]] = {
            TMDB: self._tmdb,
            OMDB: self._omdb,
            TVMAZE: self._tvmaze,
            TVDB: self._tvdb,
        }
        return handler[host](request)

    def _tmdb(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/3")
        query = request.url.params.get("query", "")
        if path.startswith("/search/"):
            kind = path.rsplit("/", 1)[1]
            year = request.url.params.get("year", "")
            rows = _find(self.tmdb_search, kind, f"{query}|{year}") or _find(self.tmdb_search, kind, query) or []
            return httpx.Response(200, json={"page": 1, "results": rows, "total_results": len(rows)})
        _, kind, raw_id = path.split("/")
        body = self.tmdb_detail.get((kind, int(raw_id)))
        return httpx.Response(200, json=body) if body is not None else httpx.Response(404, json={})

    def _omdb(self, request: httpx.Request) -> httpx.Response:
        params = request.url.params
        if "s" in params:
            kind = "series" if params.get("type") == "series" else "movie"
            rows = _find(self.omdb_search, kind, params["s"])
            if rows is None:
                return httpx.Response(200, json={"Response": "False", "Error": "Movie not found!"})
            return httpx.Response(200, json={"Search": rows, "totalResults": str(len(rows)), "Response": "True"})
        body = self.omdb_detail.get(params.get("i", ""))
        return httpx.Response(200, json=body or {"Response": "False", "Error": "Incorrect IMDb ID."})

    def _tvmaze(self, request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_find_one(self.tvmaze_search, request.url.params.get("q", "")) or [])

    def _tvdb(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/login"):
            return httpx.Response(200, json={"data": {"token": "t"}})
        rows = _find_one(self.tvdb_search, request.url.params.get("query", "")) or []
        return httpx.Response(200, json={"status": "success", "data": rows})


def cfg(**kw: Any) -> Config:
    base: dict[str, Any] = {"id": 1, "tmdb_api_key": "tmdb-k", "omdb_api_key": "omdb-k", "tvdb_api_key": "tvdb-k"}
    base.update(kw)
    return Config(**base)


def make(fake: Fake, **kw: Any) -> tuple[Retriever, list[tuple[str, str, str, str, str]]]:
    attempts: list[tuple[str, str, str, str, str]] = []
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake))
    retriever = Retriever(
        build_online_sources(http),
        on_attempt=lambda *a: attempts.append(a),
        **kw,  # type: ignore[arg-type]
    )
    return retriever, attempts


def feature_titles(minutes: float = 163) -> list[ScanTitle]:
    return [ScanTitle(index=0, duration_seconds=round(minutes * 60), segment_map=[1, 2], source_file="00800.mpls")]


def br2049_evidence() -> DiscEvidence:
    return build_evidence(
        bd_title="Blade Runner 2049 - 3D Blu-ray™",
        iso_name="Blade_Runner_2049_(2017)_[3D].iso",
        label=None,
        titles=feature_titles(163),
        structured=True,
        set_number=None,
        num_sets=None,
        now=NOW,
    )


def evidence(label: str, minutes: float | None = None, **kw: Any) -> DiscEvidence:
    titles = feature_titles(minutes) if minutes else []
    return build_evidence(
        bd_title=kw.get("bd_title"),
        iso_name=kw.get("iso_name"),
        label=label,
        titles=titles,
        structured=False,
        set_number=None,
        num_sets=None,
        now=NOW,
    )


def br2049_fake() -> Fake:
    fake = Fake()
    fake.tmdb_search[("movie", "Blade Runner 2049")] = [
        tmdb_movie(335984, "Blade Runner 2049", "2017-10-04"),
        tmdb_movie(78, "Blade Runner", "1982-06-25"),
        tmdb_movie(500, "Blade Runner Black Out 2022", "2017-09-26"),
    ]
    fake.tmdb_detail[("movie", 335984)] = tmdb_movie_detail(335984, "Blade Runner 2049", "2017-10-04", 164, "tt1856101")
    fake.omdb_search[("movie", "Blade Runner 2049")] = [omdb_row("Blade Runner 2049", "2017", "tt1856101")]
    return fake


# --- kind plan --------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("p_tv", "kinds"),
    [
        (0.9, ("tv",)),
        (0.75, ("tv",)),
        (0.8, ("tv",)),
        (0.6, ("movie", "tv")),
        (0.4, ("movie", "tv")),
        (0.25, ("movie",)),
        (0.15, ("movie",)),
    ],
)
def test_plan_kinds(p_tv: float, kinds: tuple[str, ...]) -> None:
    assert plan_kinds(p_tv) == kinds


def test_other_kind_is_the_one_not_searched() -> None:
    assert other_kind(("movie",)) == "tv"
    assert other_kind(("tv",)) == "movie"
    assert other_kind(("movie", "tv")) is None


# --- one movie disc ---------------------------------------------------------------------------------------------------


async def test_blade_runner_merges_across_providers_and_fills_the_runtime() -> None:
    fake = br2049_fake()
    retriever, _ = make(fake)
    ev = br2049_evidence()
    budget = Budget()

    found = await retriever.search(cfg(), ev, build_queries(ev), ("movie",), budget)

    by_title = {r.candidate.title: r.candidate for r in found}
    winner = by_title["Blade Runner 2049"]
    assert winner.providers == ("tmdb", "omdb")
    assert winner.provider_rank == 0
    assert winner.runtime_minutes == 164
    assert winner.year == 2017
    assert dict(winner.ids) == {"tmdb": "335984", "imdb": "tt1856101"}
    # The list rows carry no runtime, and only the promising row was detailed.
    assert by_title["Blade Runner"].runtime_minutes is None
    assert by_title["Blade Runner Black Out 2022"].runtime_minutes is None
    assert (budget.list_calls, budget.detail_calls, budget.cached) == (2, 1, 0)
    assert [r.url.path for r in fake.calls(TMDB)] == ["/3/search/movie", "/3/movie/335984"]
    assert [r.result.provider for r in found if r.candidate.title == "Blade Runner 2049"] == ["tmdb"]


async def test_the_list_search_skips_the_per_row_detail_calls() -> None:
    fake = br2049_fake()
    retriever, _ = make(fake)
    ev = evidence("BLADE_RUNNER_2049")  # no runtime evidence: no details at all
    await retriever.search(cfg(), ev, build_queries(ev), ("movie",), Budget())
    assert [r.url.path for r in fake.calls(TMDB)] == ["/3/search/movie"]


async def test_no_detail_call_without_runtime_evidence() -> None:
    fake = br2049_fake()
    retriever, _ = make(fake)
    ev = evidence("BLADE_RUNNER_2049")
    budget = Budget()
    found = await retriever.search(cfg(), ev, build_queries(ev), ("movie",), budget)
    assert budget.detail_calls == 0
    assert all(r.candidate.runtime_minutes is None for r in found)


async def test_only_three_details_and_only_promising_candidates() -> None:
    fake = Fake()
    titles = [f"Matrix {n}" for n in range(1, 6)]
    fake.tmdb_search[("movie", "Matrix")] = [
        tmdb_movie(100 + n, t, f"{2000 + n}-01-01") for n, t in enumerate(titles, 1)
    ]
    for n in range(1, 6):
        fake.tmdb_detail[("movie", 100 + n)] = tmdb_movie_detail(
            100 + n, f"Matrix {n}", f"{2000 + n}-01-01", 120, f"tt{n}"
        )
    retriever, _ = make(fake)
    ev = evidence("MATRIX", minutes=120)
    budget = Budget()
    found = await retriever.search(cfg(movie_sources=["tmdb"]), ev, build_queries(ev), ("movie",), budget)
    assert budget.detail_calls == 3
    assert sum(r.candidate.runtime_minutes is not None for r in found) == 3
    assert len([r for r in fake.calls(TMDB) if "/movie/" in r.url.path]) == 3


async def test_a_candidate_below_the_pre_score_floor_is_not_detailed() -> None:
    fake = Fake()
    fake.tmdb_search[("movie", "Heat")] = [tmdb_movie(1, "Totally Different Words", "1995-12-15")]
    retriever, _ = make(fake)
    ev = evidence("HEAT", minutes=170)
    budget = Budget()
    await retriever.search(cfg(movie_sources=["tmdb"]), ev, build_queries(ev), ("movie",), budget)
    assert budget.detail_calls == 0


async def test_details_of_one_title_found_by_tmdb_alone_merge_with_omdb_by_imdb_id() -> None:
    """The two providers spell the title differently, so the list merge misses; the IMDb id joins them."""
    fake = Fake()
    fake.tmdb_search[("movie", "Blade Runner 2049")] = [tmdb_movie(335984, "Blade Runner 2049", "2017-10-04")]
    fake.omdb_search[("movie", "Blade Runner 2049")] = [omdb_row("Blade Runner 2049 - Extended", "2017", "tt1856101")]
    fake.tmdb_detail[("movie", 335984)] = tmdb_movie_detail(335984, "Blade Runner 2049", "2017-10-04", 164, "tt1856101")
    retriever, _ = make(fake)
    ev = br2049_evidence()
    found = await retriever.search(cfg(), ev, build_queries(ev), ("movie",), Budget())
    assert len(found) == 1
    assert found[0].candidate.providers == ("tmdb", "omdb")
    assert found[0].candidate.runtime_minutes == 164


async def test_two_films_with_one_title_stay_two_candidates() -> None:
    fake = Fake()
    fake.tmdb_search[("movie", "Total Recall")] = [
        tmdb_movie(861, "Total Recall", "1990-06-01"),
        tmdb_movie(64635, "Total Recall", "2012-08-02"),
    ]
    fake.omdb_search[("movie", "Total Recall")] = [
        omdb_row("Total Recall", "1990", "tt0100802"),
        omdb_row("Total Recall", "2012", "tt1386703"),
    ]
    retriever, _ = make(fake)
    ev = evidence("TOTAL_RECALL")
    found = await retriever.search(cfg(), ev, build_queries(ev), ("movie",), Budget())
    assert sorted((r.candidate.year, r.candidate.providers) for r in found) == [
        (1990, ("tmdb", "omdb")),
        (2012, ("tmdb", "omdb")),
    ]


async def test_the_best_ranked_providers_result_is_the_one_kept_for_apply() -> None:
    fake = br2049_fake()
    retriever, _ = make(fake)
    ev = evidence("BLADE_RUNNER_2049")
    found = await retriever.search(cfg(movie_sources=["omdb", "tmdb"]), ev, build_queries(ev), ("movie",), Budget())
    top = next(r for r in found if r.candidate.title == "Blade Runner 2049")
    assert top.result.provider == "omdb"
    assert top.candidate.provider_rank == 0
    assert top.candidate.providers == ("omdb", "tmdb")


# --- cache ------------------------------------------------------------------------------------------------------------


async def test_a_second_identify_of_the_same_disc_makes_no_provider_call() -> None:
    fake = br2049_fake()
    retriever, _ = make(fake)
    ev = br2049_evidence()
    first = await retriever.search(cfg(), ev, build_queries(ev), ("movie",), Budget())
    seen = len(fake.requests)
    second_budget = Budget()
    second = await retriever.search(cfg(), ev, build_queries(ev), ("movie",), second_budget)
    assert len(fake.requests) == seen
    assert (second_budget.list_calls, second_budget.detail_calls, second_budget.cached) == (0, 0, 3)
    assert [r.candidate for r in second] == [r.candidate for r in first]


async def test_a_cached_result_is_a_copy_the_caller_may_edit() -> None:
    fake = br2049_fake()
    retriever, _ = make(fake)
    ev = evidence("BLADE_RUNNER_2049")
    first = await retriever.search(cfg(), ev, build_queries(ev), ("movie",), Budget())
    first[0].result.payload["imdb_id"] = "edited"
    again = await retriever.search(cfg(), ev, build_queries(ev), ("movie",), Budget())
    assert again[0].result.payload.get("imdb_id") != "edited"


async def test_errors_are_never_cached() -> None:
    fake = br2049_fake()
    fake.fail[TMDB] = 500
    retriever, _ = make(fake)
    ev = evidence("BLADE_RUNNER_2049")
    await retriever.search(cfg(movie_sources=["tmdb"]), ev, build_queries(ev), ("movie",), Budget())
    fake.fail.clear()
    budget = Budget()
    found = await retriever.search(cfg(movie_sources=["tmdb"]), ev, build_queries(ev), ("movie",), budget)
    assert budget.list_calls == 1
    assert found


async def test_cache_entries_expire() -> None:
    now = [0.0]
    fake = br2049_fake()
    retriever, _ = make(fake, cache=TtlCache(3600.0, 512, clock=lambda: now[0]))
    ev = evidence("BLADE_RUNNER_2049")
    await retriever.search(cfg(), ev, build_queries(ev), ("movie",), Budget())
    now[0] = 3601.0
    budget = Budget()
    await retriever.search(cfg(), ev, build_queries(ev), ("movie",), budget)
    assert budget.list_calls == 2


# --- budget -----------------------------------------------------------------------------------------------------------


async def test_list_calls_are_capped_at_twelve_in_query_order() -> None:
    fake = Fake()
    retriever, _ = make(fake)
    queries = [Query(f"Title {n}", "label", "v1") for n in "abcd"]  # 4 queries
    ev = evidence("X")
    budget = Budget()
    # both kinds, tmdb + omdb for movies and tmdb + tvmaze + tvdb for tv: 5 per query, 20 wanted
    await retriever.search(cfg(), ev, queries, ("movie", "tv"), budget)
    assert budget.list_calls == 12
    asked = [r.url.params.get("query") or r.url.params.get("s") or r.url.params.get("q") for r in fake.requests]
    assert "Title d" not in asked
    assert "Title a" in asked and "Title c" in asked


async def test_the_budget_carries_across_passes() -> None:
    fake = Fake()
    retriever, _ = make(fake)
    ev = evidence("X")
    budget = Budget()
    first = [Query(f"Title {n}", "label", "v1") for n in "abcd"]
    await retriever.search(cfg(), ev, first, ("movie",), budget)  # 8 calls
    await retriever.search(cfg(), ev, first, ("tv",), budget)  # 12 wanted, 4 left
    assert budget.list_calls == 12


async def test_budget_counts_mirror_the_spec_worst_case() -> None:
    assert Budget().list_left + Budget().detail_left + Budget().retry_left == 16


# --- year retry (D70) -------------------------------------------------------------------------------------------------


async def test_a_trusted_year_that_no_result_carries_triggers_one_filtered_tmdb_retry() -> None:
    fake = Fake()
    fake.tmdb_search[("movie", "Blade Runner 2049")] = [tmdb_movie(78, "Blade Runner", "1982-06-25")]
    fake.tmdb_search[("movie", "Blade Runner 2049|2017")] = [tmdb_movie(335984, "Blade Runner 2049", "2017-10-04")]
    retriever, _ = make(fake)
    ev = br2049_evidence()
    budget = Budget()
    found = await retriever.search(cfg(movie_sources=["tmdb"]), ev, build_queries(ev), ("movie",), budget)
    assert {r.candidate.title for r in found} == {"Blade Runner", "Blade Runner 2049"}
    searches = [r for r in fake.calls(TMDB) if r.url.path == "/3/search/movie"]
    assert [r.url.params.get("year") for r in searches] == [None, "2017"]
    assert budget.list_calls == 2


async def test_no_year_retry_when_a_result_already_has_the_year() -> None:
    fake = br2049_fake()
    retriever, _ = make(fake)
    ev = br2049_evidence()
    await retriever.search(cfg(), ev, build_queries(ev), ("movie",), Budget())
    assert all(r.url.params.get("year") is None for r in fake.calls(TMDB))


async def test_no_year_retry_for_a_weak_year() -> None:
    fake = Fake()
    fake.tmdb_search[("movie", "Alien")] = [tmdb_movie(1, "Aliens", "1986-07-18")]
    retriever, _ = make(fake)
    ev = evidence("ALIEN_1979")  # a bare label year: reliability 0.3
    budget = Budget()
    await retriever.search(cfg(movie_sources=["tmdb"]), ev, build_queries(ev), ("movie",), budget)
    assert all(r.url.params.get("year") is None for r in fake.calls(TMDB))


async def test_no_year_retry_for_a_tv_pass_or_without_tmdb() -> None:
    fake = Fake()
    retriever, _ = make(fake)
    ev = br2049_evidence()
    await retriever.search(cfg(), ev, build_queries(ev), ("tv",), Budget())
    await retriever.search(cfg(movie_sources=["omdb"]), ev, build_queries(ev), ("movie",), Budget())
    assert all(r.url.params.get("year") is None for r in fake.calls(TMDB))


# --- failures ---------------------------------------------------------------------------------------------------------


async def test_a_provider_that_times_out_drops_out_and_the_rest_are_still_merged() -> None:
    fake = br2049_fake()
    fake.fail[OMDB] = "timeout"
    retriever, attempts = make(fake)
    ev = br2049_evidence()
    found = await retriever.search(cfg(), ev, build_queries(ev), ("movie",), Budget())
    assert {r.candidate.title for r in found} >= {"Blade Runner 2049"}
    assert ("omdb", "movie", "list", "timeout", "Blade Runner 2049") in attempts
    assert ("tmdb", "movie", "list", "hit", "Blade Runner 2049") in attempts


async def test_a_slow_call_is_cut_at_the_provider_timeout() -> None:
    fake = br2049_fake()
    fake.delay = 0.2
    retriever, attempts = make(fake, timeout=0.01)
    ev = evidence("BLADE_RUNNER_2049")
    found = await retriever.search(cfg(), ev, build_queries(ev), ("movie",), Budget())
    assert found == []
    assert {a[3] for a in attempts} == {"timeout"}


async def test_every_provider_failing_gives_no_candidates() -> None:
    fake = br2049_fake()
    fake.fail[TMDB] = 500
    fake.fail[OMDB] = 401
    retriever, attempts = make(fake)
    ev = evidence("BLADE_RUNNER_2049")
    assert await retriever.search(cfg(), ev, build_queries(ev), ("movie",), Budget()) == []
    assert {a[3] for a in attempts} == {"error"}


async def test_a_failed_detail_keeps_the_candidate_without_a_runtime() -> None:
    fake = br2049_fake()
    del fake.tmdb_detail[("movie", 335984)]
    retriever, attempts = make(fake)
    ev = br2049_evidence()
    found = await retriever.search(cfg(), ev, build_queries(ev), ("movie",), Budget())
    top = next(r for r in found if r.candidate.title == "Blade Runner 2049")
    assert top.candidate.runtime_minutes is None
    assert ("tmdb", "movie", "detail", "error", "335984") in attempts


async def test_a_source_without_a_key_is_not_called() -> None:
    fake = br2049_fake()
    retriever, _ = make(fake)
    ev = evidence("BLADE_RUNNER_2049")
    await retriever.search(cfg(omdb_api_key=None), ev, build_queries(ev), ("movie",), Budget())
    assert fake.calls(OMDB) == []


# --- semaphores -------------------------------------------------------------------------------------------------------


async def test_calls_run_in_parallel_within_each_sources_limit() -> None:
    fake = Fake()
    fake.delay = 0.02
    retriever, _ = make(fake)
    queries = [Query(f"Title {n}", "label", "v1") for n in "abcdef"]
    await retriever.search(cfg(movie_sources=["tmdb"]), evidence("X"), queries, ("movie",), Budget())
    assert 1 < fake.peak[TMDB] <= 4


async def test_omdb_and_tvmaze_are_limited_to_two_at_once() -> None:
    fake = Fake()
    fake.delay = 0.02
    retriever, _ = make(fake)
    queries = [Query(f"Title {n}", "label", "v1") for n in "abcd"]
    await retriever.search(
        cfg(movie_sources=["omdb"], episode_sources=["tvmaze"]), evidence("X"), queries, ("movie", "tv"), Budget()
    )
    assert fake.peak[OMDB] == 2
    assert fake.peak[TVMAZE] == 2


# --- tv ---------------------------------------------------------------------------------------------------------------


async def test_a_season_disc_merges_three_tv_sources_and_takes_the_episode_runtime_from_tvmaze() -> None:
    fake = Fake()
    fake.tmdb_search[("tv", "Kolchak The Night Stalker")] = [
        tmdb_tv(1, "Kolchak: The Night Stalker", "1974-09-13"),
        tmdb_tv(2, "Night Stalker", "2005-09-29"),
    ]
    fake.tvmaze_search["Kolchak The Night Stalker"] = [
        tvmaze_show(10, "Kolchak: The Night Stalker", "1974-09-13", 60, "tt0071054", 74000),
        tvmaze_show(11, "Night Stalker", "2005-09-29", 60, "tt0436992", 75000),
    ]
    fake.tvdb_search["Kolchak The Night Stalker"] = [tvdb_row(74000, "Kolchak: The Night Stalker", "1974", "tt0071054")]
    retriever, _ = make(fake)
    titles = [ScanTitle(index=i, duration_seconds=51 * 60) for i in range(5)]
    ev = build_evidence(
        bd_title=None,
        iso_name="Kolchak The Night Stalker - Disc 1 of 4.iso",
        label="KOLCHAK_THE_NIGHT_STALKER_DISC_1",
        titles=titles,
        structured=False,
        set_number=None,
        num_sets=None,
        now=NOW,
    )
    queries = build_queries(ev)
    assert len(queries) == 1
    budget = Budget()
    found = await retriever.search(cfg(), ev, queries, plan_kinds(ev.p_tv), budget)
    by_year = {r.candidate.year: r.candidate for r in found}
    assert set(by_year) == {1974, 2005}
    assert by_year[1974].providers == ("tmdb", "tvmaze", "tvdb")
    assert by_year[1974].runtime_minutes == 60
    assert dict(by_year[1974].ids) == {"tmdb": "1", "tvmaze": "10", "imdb": "tt0071054", "tvdb": "74000"}
    assert by_year[2005].providers == ("tmdb", "tvmaze")
    assert (budget.list_calls, budget.detail_calls) == (3, 0)
    assert fake.calls(OMDB) == []


# --- field readers ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "kind", "payload", "minutes"),
    [
        ("tmdb", "movie", {"runtime": 164}, 164.0),
        ("tmdb", "movie", {"runtime": 0}, None),
        ("tmdb", "movie", {}, None),
        ("tmdb", "tv", {"episode_run_time": [45, 50]}, 45.0),
        ("tmdb", "tv", {"episode_run_time": [], "last_episode_to_air": {"runtime": 42}}, 42.0),
        ("tmdb", "tv", {"episode_run_time": []}, None),
        ("omdb", "movie", {"Runtime": "164 min"}, 164.0),
        ("omdb", "movie", {"Runtime": "2 h 44 min"}, 164.0),
        ("omdb", "movie", {"Runtime": "N/A"}, None),
        ("omdb", "movie", {}, None),
        ("tvmaze", "tv", {"runtime": 60, "averageRuntime": 58}, 58.0),
        ("tvmaze", "tv", {"runtime": 60, "averageRuntime": None}, 60.0),
        ("tvmaze", "tv", {"runtime": None, "averageRuntime": None}, None),
        ("tvdb", "tv", {"averageRuntime": 45}, 45.0),
        ("tvdb", "tv", {}, None),
    ],
)
def test_runtime_of(source: str, kind: str, payload: dict[str, Any], minutes: float | None) -> None:
    assert runtime_of(source, kind, payload) == minutes  # type: ignore[arg-type]


def test_ids_of_reads_each_providers_own_keys() -> None:
    assert ids_of("tmdb", {"id": 5, "imdb_id": "tt1", "tvdb_id": "9"}) == {"tmdb": "5", "imdb": "tt1", "tvdb": "9"}
    assert ids_of("tmdb", {"id": 5, "imdb_id": None, "tvdb_id": None}) == {"tmdb": "5"}
    assert ids_of("omdb", {"imdbID": "tt2"}) == {"imdb": "tt2"}
    assert ids_of("omdb", {"imdbID": "N/A"}) == {}
    assert ids_of("tvmaze", {"tvmaze_id": "3", "imdb_id": "tt3", "tvdb_id": "4"}) == {
        "imdb": "tt3",
        "tvdb": "4",
        "tvmaze": "3",
    }
    assert ids_of("tvdb", {"id": "series-7", "tvdb_id": "7"}) == {"tvdb": "7"}
