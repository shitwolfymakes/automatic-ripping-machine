"""Hand-built provider bodies and a MockTransport server for the weighted identify tests."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
from arm_common import Config
from arm_common.schemas import ScanTitle

from arm_backend.metadata.match.evidence import DiscEvidence, build_evidence
from arm_backend.metadata.match.retrieve import Retriever
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
        self.tmdb_external_ids: dict[tuple[str, int], dict[str, Any]] = {}
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
        _, kind, raw_id, *tail = path.split("/")
        if tail == ["external_ids"]:
            return httpx.Response(200, json=self.tmdb_external_ids.get((kind, int(raw_id)), {}))
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
