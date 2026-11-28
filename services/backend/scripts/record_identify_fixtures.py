"""Record real provider responses for the weighted identify tests (a developer tool, run by hand).

Runs the retriever for each disc below against the live providers and stores every response BODY under
tests/fixtures/providers/<provider>/<case>[.detail-<id>].json. Only bodies are written: no URL, header or key.
Keys come from the environment (TMDB_API_KEY, OMDB_API_KEY, TVDB_API_KEY); a missing key skips that provider.

    TMDB_API_KEY=... OMDB_API_KEY=... TVDB_API_KEY=... uv run python scripts/record_identify_fixtures.py [case ...]

While recording, check the facts the spec lists as unverified: TVmaze and TVDB runtime fields, TMDb TV
`episode_run_time`, and whether OMDb `s=` returns the 1982 Blade Runner for the 2049 query.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx
from arm_common import Config
from arm_common.schemas import ScanTitle

from arm_backend.metadata.match.evidence import build_evidence
from arm_backend.metadata.match.queries import build_queries
from arm_backend.metadata.match.retrieve import Budget, Retriever, plan_kinds
from arm_backend.metadata.sources import build_online_sources

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "providers"
HOSTS = {
    "api.themoviedb.org": "tmdb",
    "www.omdbapi.com": "omdb",
    "api.tvmaze.com": "tvmaze",
    "api4.thetvdb.com": "tvdb",
}
_TMDB_DETAIL = re.compile(r"^/3/(?:movie|tv)/(\d+)$")
_TVDB_DETAIL = re.compile(r"^/v4/series/(\d+)/extended$")
_TVMAZE_DETAIL = re.compile(r"^/shows/(\d+)$")


@dataclass(frozen=True)
class Case:
    slug: str
    label: str | None = None
    bd_title: str | None = None
    iso_name: str | None = None
    # Feature minutes, or episode minutes with `episodes` > 0.
    minutes: float | None = None
    episodes: int = 0


CASES = (
    Case(
        "blade-runner-2049-3d",
        bd_title="Blade Runner 2049 - 3D Blu-ray™",
        iso_name="Blade_Runner_2049_(2017)_[3D].iso",
        minutes=163,
    ),
    Case("wonder-woman-1984", bd_title="Wonder Woman 1984", minutes=151),
    Case("1917", label="1917", minutes=119),
    Case(
        "kolchak",
        label="KOLCHAK_THE_NIGHT_STALKER_DISC_1",
        iso_name="Kolchak The Night Stalker - Disc 1 of 4.iso",
        minutes=51,
        episodes=5,
    ),
    Case(
        "last-crusade", bd_title="Indiana Jones and the Last Crusade", label="INDIANA_JONES_LAST_CRUSADE", minutes=127
    ),
    Case("the-matrix", label="THE_MATRIX_NTSC", minutes=136),
    Case("total-recall", label="TOTAL_RECALL", minutes=113),
)


def _detail_id(host: str, request: httpx.Request) -> str | None:
    path = request.url.path
    patterns = {"tmdb": _TMDB_DETAIL, "tvdb": _TVDB_DETAIL, "tvmaze": _TVMAZE_DETAIL}
    if host == "omdb":
        return request.url.params.get("i")
    match = patterns[host].match(path) if host in patterns else None
    return match.group(1) if match else None


class Recorder(httpx.AsyncBaseTransport):
    """Forwards every request and writes the response body for the case being recorded."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self._inner = inner
        self.case = ""
        self._listed: set[tuple[str, str]] = set()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        await response.aread()
        provider = HOSTS.get(request.url.host)
        if provider and response.status_code == 200 and not request.url.path.endswith("/login"):
            self._write(provider, request, response)
        return response

    def _write(self, provider: str, request: httpx.Request, response: httpx.Response) -> None:
        detail = _detail_id(provider, request)
        name = f"{self.case}.detail-{detail}.json" if detail else f"{self.case}.json"
        if not detail:
            # Several list calls per case (one per query and kind) share a name: number the later ones.
            n = sum(1 for p, c in self._listed if p == provider and c.startswith(self.case))
            self._listed.add((provider, f"{self.case}{n}"))
            name = f"{self.case}.json" if n == 0 else f"{self.case}.{n}.json"
        target = OUT / provider / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(response.json(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


async def record(case: Case, retriever: Retriever, recorder: Recorder, cfg: Config) -> None:
    recorder.case = case.slug
    titles = (
        [ScanTitle(index=i, duration_seconds=round(case.minutes * 60)) for i in range(case.episodes)]
        if case.episodes
        else [
            ScanTitle(
                index=0, duration_seconds=round((case.minutes or 0) * 60), segment_map=[1], source_file="00800.mpls"
            )
        ]
    )
    ev = build_evidence(
        bd_title=case.bd_title,
        iso_name=case.iso_name,
        label=case.label,
        titles=titles,
        structured=not case.episodes,
        set_number=None,
        num_sets=None,
        now=datetime.now(UTC),
    )
    await retriever.search(cfg, ev, build_queries(ev), plan_kinds(ev.p_tv), Budget())


async def main(wanted: list[str]) -> None:
    cfg = Config(
        id=1,
        tmdb_api_key=os.environ.get("TMDB_API_KEY"),
        omdb_api_key=os.environ.get("OMDB_API_KEY"),
        tvdb_api_key=os.environ.get("TVDB_API_KEY"),
    )
    recorder = Recorder(httpx.AsyncHTTPTransport())
    async with httpx.AsyncClient(transport=recorder, timeout=15.0) as http:
        retriever = Retriever(build_online_sources(http), timeout=15.0)
        for case in CASES:
            if wanted and case.slug not in wanted:
                continue
            await record(case, retriever, recorder, cfg)
            print(f"recorded {case.slug}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
