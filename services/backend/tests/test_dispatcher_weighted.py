"""MetadataDispatcher.identify end to end for the spec's example discs: mocked provider responses (through
httpx.MockTransport), the weighted search and its decision, the call budget and the cache."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import pytest
from arm_common import DiscType
from arm_common.schemas import BdDiscMeta, ScanResult, ScanTitle

from arm_backend.metadata.dispatcher import Identification, MetadataDispatcher
from arm_backend.metadata.match.retrieve import MAX_DETAIL_CALLS, MAX_LIST_CALLS, MAX_YEAR_RETRIES
from tests._provider_fakes import (
    OMDB,
    TMDB,
    TVDB,
    TVMAZE,
    Fake,
    cfg,
    omdb_row,
    tmdb_movie,
    tmdb_movie_detail,
    tmdb_tv,
    tvdb_row,
    tvmaze_show,
)
from tests.bd_structure_scans import br3d_structure_scan

ALL_HINTS = ("bd_title", "iso_name", "label")
BUDGET = MAX_LIST_CALLS + MAX_DETAIL_CALLS + MAX_YEAR_RETRIES


@dataclass(frozen=True)
class Film:
    tmdb_id: int
    title: str
    year: int
    minutes: int
    imdb: str


def add_film(fake: Fake, queries: list[str], film: Film, *, omdb: bool = True) -> None:
    """The film as TMDb lists it (and details it) and as OMDb lists it, for each of the queries."""
    for query in queries:
        rows = fake.tmdb_search.setdefault(("movie", query), [])
        rows.append(tmdb_movie(film.tmdb_id, film.title, f"{film.year}-06-01"))
        if omdb:
            fake.omdb_search.setdefault(("movie", query), []).append(omdb_row(film.title, str(film.year), film.imdb))
    fake.tmdb_detail[("movie", film.tmdb_id)] = tmdb_movie_detail(
        film.tmdb_id, film.title, f"{film.year}-06-01", film.minutes, film.imdb
    )


def dispatcher(fake: Fake) -> MetadataDispatcher:
    return MetadataDispatcher(httpx.AsyncClient(transport=httpx.MockTransport(fake)))


async def identify(fake: Fake, scan: ScanResult, **kw: Any) -> tuple[Identification, MetadataDispatcher]:
    d = dispatcher(fake)
    kw.setdefault("hint_ids", ALL_HINTS)
    return await d.identify(scan, cfg(), **kw), d


def dvd(label: str, minutes: float | None = None, **kw: Any) -> ScanResult:
    titles = [ScanTitle(index=0, duration_seconds=round(minutes * 60))] if minutes else []
    return ScanResult(disc_type=DiscType.DVD, volume_label=label, titles=titles, **kw)


def calls(fake: Fake) -> int:
    return len(fake.requests)


def titles_of(found: Identification) -> list[str]:
    assert found.match is not None
    return [f"{c.title} ({c.year})" for c in found.match.candidates]


# --- Blade Runner 2049 3D (#752) ----------------------------------------------------------------------------------------


def br2049_provider_responses() -> Fake:
    fake = Fake()
    films = [
        Film(335984, "Blade Runner 2049", 2017, 164, "tt1856101"),
        Film(78, "Blade Runner", 1982, 117, "tt0083658"),
    ]
    for film in films:
        add_film(fake, ["Blade Runner 2049"], film, omdb=film.tmdb_id == 335984)
    fake.tmdb_search[("movie", "Blade Runner 2049")].append(
        tmdb_movie(500, "Blade Runner Black Out 2022", "2017-09-26")
    )
    # A TV source that would happily answer "Blade Runner 2099" if anyone asked it.
    fake.tmdb_search[("tv", "Blade Runner 2049")] = [tmdb_tv(7, "Blade Runner 2099", "2026-01-01")]
    fake.tvmaze_search["Blade Runner 2049"] = [tvmaze_show(70, "Blade Runner 2099", "2026-01-01", 45, "tt9999999", 900)]
    return fake


def br2049_3d_scan() -> ScanResult:
    return br3d_structure_scan().model_copy(
        update={"volume_label": None, "bd_meta": BdDiscMeta(name="Blade Runner 2049 - 3D Blu-ray™")}
    )


async def test_blade_runner_2049_3d_accepts_the_film_not_the_2099_show() -> None:
    fake = br2049_provider_responses()
    found, d = await identify(fake, br2049_3d_scan(), iso_name="Blade_Runner_2049_(2017)_[3D]")
    assert found.result is not None
    assert (found.result.title, found.result.year, found.result.kind) == ("Blade Runner 2049", 2017, "movie")
    assert found.result.provider == "tmdb"
    match = found.match
    assert match is not None and match.decision == "accept"
    assert [q.text for q in match.queries] == ["Blade Runner 2049"]
    assert match.queries[0].kinds == ["movie"]
    assert match.evidence.numbers == ["2049"]
    assert [y.year for y in match.evidence.years] == [2017]
    top = match.candidates[0]
    assert (top.title, top.year, top.runtime, top.providers) == ("Blade Runner 2049", 2017, 164, ["tmdb", "omdb"])
    assert top.score > 85 and top.flags == []
    assert match.runner_up is not None and match.runner_up < 30
    # One list call per movie source and one detail call; nothing asked a TV source.
    assert (match.calls.list, match.calls.detail, match.calls.cached) == (2, 1, 0)
    assert fake.calls(TVMAZE) == [] and fake.calls(TVDB) == []
    assert not any(r.url.path == "/3/search/tv" for r in fake.calls(TMDB))
    # The winner already carries its ids, so no external-ids call follows.
    assert not any(r.url.path.endswith("/external_ids") for r in fake.calls(TMDB))
    assert found.result.payload["imdb_id"] == "tt1856101"
    await d.aclose()


async def test_a_second_identify_of_the_same_disc_is_served_from_the_cache() -> None:
    fake = br2049_provider_responses()
    d = dispatcher(fake)
    first = await d.identify(br2049_3d_scan(), cfg(), hint_ids=ALL_HINTS, iso_name="Blade_Runner_2049_(2017)_[3D]")
    seen = calls(fake)
    second = await d.identify(br2049_3d_scan(), cfg(), hint_ids=ALL_HINTS, iso_name="Blade_Runner_2049_(2017)_[3D]")
    assert calls(fake) == seen
    assert second.result is not None and first.result is not None
    assert second.result.title == first.result.title
    assert second.match is not None and second.match.calls.cached == 3


async def test_a_disc_text_only_disabled_hint_is_not_searched() -> None:
    fake = br2049_provider_responses()
    found, _ = await identify(fake, br2049_3d_scan(), iso_name=None, hint_ids=("iso_name",))
    # With the BDMT name switched off and no ISO name, the disc has no text at all.
    assert found.result is None
    assert found.match is not None and found.match.decision == "no_match"
    assert found.match.queries == []
    assert fake.requests == []


async def test_a_label_only_disc_never_applies_a_tv_fallback() -> None:
    """With no runtime to separate them the film is offered, and the show that shares most of its words scores far
    below the floor (the number rule, the kind term and the title square), so it is not even offered."""
    fake = br2049_provider_responses()
    found, _ = await identify(fake, dvd("BLADE_RUNNER_2049"))
    assert found.result is None
    assert found.match is not None and found.match.decision == "shortlist"
    offered = titles_of(found)[: found.match.shortlist]
    assert offered[0] == "Blade Runner 2049 (2017)"
    assert all("2099" not in t for t in offered)
    both = next(c for c in found.match.candidates if c.title == "Blade Runner 2099")
    assert both.score < 40 and "numbers_differ" in both.flags


async def test_a_miss_in_one_kind_searches_the_other_with_the_first_queries_only() -> None:
    fake = Fake()
    fake.tmdb_search[("tv", "Heat 1995")] = [tmdb_tv(1, "Heat", "1995-01-01")]
    found, _ = await identify(fake, dvd("HEAT_1995", 170), hint_ids=("label",))
    assert found.match is not None
    # A 170-minute feature is a movie; nothing matched, so the first query (only) was tried as TV.
    assert [(q.text, q.kinds) for q in found.match.queries] == [
        ("HEAT 1995", ["movie", "tv"]),
        ("HEAT", ["movie"]),
    ]
    tv_asked = [r.url.params["query"] for r in fake.calls(TMDB) if r.url.path == "/3/search/tv"]
    assert tv_asked == ["HEAT 1995"]
    assert [c.kind for c in found.match.candidates] == ["tv"]


# --- the other worked examples --------------------------------------------------------------------------------------


async def test_wonder_woman_1984_keeps_the_year_in_its_title() -> None:
    fake = Fake()
    queries = ["Wonder Woman 1984", "Wonder Woman"]
    add_film(fake, queries, Film(464052, "Wonder Woman 1984", 2020, 151, "tt7126948"))
    add_film(fake, queries, Film(297762, "Wonder Woman", 2017, 141, "tt0451279"))
    add_film(fake, queries, Film(13001, "Wonder Woman", 2009, 74, "tt1121931"))
    scan = br3d_structure_scan().model_copy(
        update={"volume_label": None, "bd_meta": BdDiscMeta(name="Wonder Woman 1984")}
    )
    # 151 minutes of feature: stretch the structure scan's main clip to that length.
    scan.playlists[0].clip_seconds = [9060.0]
    scan.playlists[0].duration_seconds = 9060
    scan.playlists[2].clip_seconds = [109.0, 9060.0]
    scan.playlists[2].duration_seconds = 9169
    found, _ = await identify(fake, scan)
    assert found.result is not None
    assert (found.result.title, found.result.year) == ("Wonder Woman 1984", 2020)
    assert found.match is not None
    assert found.match.calls.list + found.match.calls.detail <= BUDGET
    assert found.match.calls.detail == MAX_DETAIL_CALLS


async def test_1917_is_a_title_not_a_year() -> None:
    fake = Fake()
    add_film(fake, ["1917"], Film(530915, "1917", 2019, 119, "tt8579674"))
    add_film(fake, ["1917"], Film(1, "1917 Documentary", 2014, 95, "tt1"), omdb=False)
    found, _ = await identify(fake, dvd("1917", 119))
    assert found.result is not None and found.result.year == 2019
    assert found.match is not None and found.match.evidence.years == []


async def test_a_tv_season_disc_searches_only_tv_and_accepts_the_series() -> None:
    fake = Fake()
    q = "Kolchak The Night Stalker"
    fake.tmdb_search[("tv", q)] = [
        tmdb_tv(1, "Kolchak: The Night Stalker", "1974-09-13"),
        tmdb_tv(2, "Night Stalker", "2005-09-29"),
    ]
    fake.tvmaze_search[q] = [
        tvmaze_show(10, "Kolchak: The Night Stalker", "1974-09-13", 60, "tt0071054", 74000),
        tvmaze_show(11, "Night Stalker", "2005-09-29", 60, "tt0436992", 75000),
    ]
    fake.tvdb_search[q] = [
        tvdb_row(74000, "Kolchak: The Night Stalker", "1974", "tt0071054"),
        tvdb_row(75000, "Night Stalker", "2005", "tt0436992"),
    ]
    scan = ScanResult(
        disc_type=DiscType.DVD,
        volume_label="KOLCHAK_THE_NIGHT_STALKER_DISC_1",
        titles=[ScanTitle(index=i, duration_seconds=51 * 60) for i in range(5)],
    )
    found, _ = await identify(fake, scan, iso_name="Kolchak The Night Stalker - Disc 1 of 4")
    assert found.result is not None
    assert (found.result.title, found.result.year, found.result.kind) == ("Kolchak: The Night Stalker", 1974, "tv")
    assert found.match is not None and found.match.decision == "accept"
    assert found.match.candidates[0].providers == ["tmdb", "tvmaze", "tvdb"]
    assert fake.calls(OMDB) == []
    assert not any(r.url.path == "/3/search/movie" for r in fake.calls(TMDB))


async def test_indiana_jones_siblings_lose_half_the_disc_words() -> None:
    fake = Fake()
    queries = ["Indiana Jones and the Last Crusade"]
    add_film(fake, queries, Film(89, "Indiana Jones and the Last Crusade", 1989, 127, "tt0097576"))
    add_film(fake, queries, Film(87, "Indiana Jones and the Temple of Doom", 1984, 118, "tt0087469"))
    add_film(fake, queries, Film(217, "Indiana Jones and the Kingdom of the Crystal Skull", 2008, 122, "tt0367882"))
    scan = br3d_structure_scan().model_copy(
        update={"volume_label": "INDIANA_JONES_LAST_CRUSADE", "bd_meta": BdDiscMeta(name=queries[0])}
    )
    scan.playlists[0].clip_seconds = [127 * 60.0 - 109.0]
    scan.playlists[0].duration_seconds = round(127 * 60 - 109)
    scan.playlists[2].clip_seconds = [109.0, 127 * 60.0 - 109.0]
    scan.playlists[2].duration_seconds = 127 * 60
    found, _ = await identify(fake, scan)
    assert found.result is not None and found.result.year == 1989
    assert found.match is not None
    # The BDMT name and the label share one query.
    assert len(found.match.queries) == 1


async def test_the_matrix_ntsc_takes_the_film_over_its_sequels_on_a_thin_margin() -> None:
    fake = Fake()
    q = ["THE MATRIX"]
    add_film(fake, q, Film(603, "The Matrix", 1999, 136, "tt0133093"))
    add_film(fake, q, Film(604, "The Matrix Reloaded", 2003, 138, "tt0234215"))
    add_film(fake, q, Film(624860, "The Matrix Resurrections", 2021, 148, "tt10838180"))
    add_film(fake, q, Film(605, "The Matrix Revolutions", 2003, 129, "tt0242653"))
    found, _ = await identify(fake, dvd("THE_MATRIX_NTSC", 136))
    assert found.result is not None and found.result.year == 1999
    assert found.match is not None
    assert found.match.calls.detail == MAX_DETAIL_CALLS
    # The film's own runtime (136) is the one runtime trusted at 0.7; the sequels are far enough down.
    assert found.match.candidates[0].score - found.match.candidates[1].score >= 10


async def test_a_remake_shortlists_both_films() -> None:
    fake = Fake()
    q = ["TOTAL RECALL"]
    add_film(fake, q, Film(861, "Total Recall", 1990, 113, "tt0100802"))
    add_film(fake, q, Film(64635, "Total Recall", 2012, 118, "tt1386703"))
    found, _ = await identify(fake, dvd("TOTAL_RECALL", 113))
    assert found.result is None
    assert found.match is not None and found.match.decision == "shortlist"
    assert titles_of(found)[: found.match.shortlist] == ["Total Recall (1990)", "Total Recall (2012)"]
    # The shortlist carries what is needed to apply a pick later.
    assert [c.provider for c in found.match.candidates] == ["tmdb", "tmdb"]
    assert found.match.candidates[0].ids["imdb"] == "tt0100802"


# --- exact hits and failures ----------------------------------------------------------------------------------------


async def test_a_crc64_hit_wins_with_its_text_score_stored() -> None:
    from arm_backend.metadata.base import MetadataResult

    class FakeArm:
        id = "arm_server"
        media_types = frozenset[str]()
        requires_key = None

        def configured(self, _cfg: object) -> None:
            return None

        async def lookup_fingerprint(self, _cfg: object, _algo: str, _value: str) -> MetadataResult:
            return MetadataResult(title="Iron Man", year=2008, kind="movie", payload={"imdb_id": "tt0371746"})

    d = MetadataDispatcher(httpx.AsyncClient(), sources={"arm_server": FakeArm()})  # type: ignore[dict-item]
    scan = dvd("IRON_MAN", fingerprints=[{"algo": "crc64", "value": "abc"}])  # type: ignore[arg-type]
    found = await d.identify(scan, cfg(), hint_ids=ALL_HINTS)
    assert found.result is not None and found.result.title == "Iron Man"
    assert found.match is not None and found.match.decision == "exact" and found.match.exact == "fingerprint"
    assert not found.match.text_disagrees and found.match.candidates[0].score > 20


async def test_an_exact_hit_the_disc_text_does_not_support_is_flagged_not_vetoed() -> None:
    from arm_backend.metadata.base import MetadataResult

    d = MetadataDispatcher(httpx.AsyncClient(), sources={})
    scan = dvd("BLADE_RUNNER_2049", 163)
    hit = MetadataResult(title="Cats", year=2019, kind="tv", payload={}, provider="tmdb")
    found = d.explain_exact(scan, hit, how="thediscdb", hint_ids=ALL_HINTS)
    assert found.result is hit
    assert found.match is not None and found.match.exact == "thediscdb"
    assert found.match.text_disagrees and "text_disagrees" in found.match.candidates[0].flags


async def test_one_provider_timing_out_leaves_the_rest_scored_and_the_attempt_logged() -> None:
    fake = br2049_provider_responses()
    fake.fail[OMDB] = "timeout"
    found, d = await identify(fake, br2049_3d_scan(), iso_name="Blade_Runner_2049_(2017)_[3D]")
    assert found.match is not None
    assert found.match.decision in ("accept", "shortlist")
    assert found.match.candidates[0].title == "Blade Runner 2049"
    assert {
        "source": "omdb",
        "step": "title",
        "kind": "movie",
        "outcome": "timeout",
        "detail": "Blade Runner 2049",
    } in (d.last_attempts)


async def test_every_provider_failing_is_a_no_match_with_the_attempts_kept() -> None:
    fake = br2049_provider_responses()
    fake.fail[TMDB] = 500
    fake.fail[OMDB] = 401
    found, d = await identify(fake, br2049_3d_scan(), iso_name="Blade_Runner_2049_(2017)_[3D]")
    assert found.result is None
    assert found.match is not None and found.match.decision == "no_match"
    # Only the TV pass's show is left, and it is far below the floor.
    assert [c.title for c in found.match.candidates] == ["Blade Runner 2099"]
    assert found.match.candidates[0].score < 40
    errors = {a["source"] for a in d.last_attempts if a["outcome"] == "error"}
    assert errors == {"tmdb", "omdb"}


@pytest.mark.parametrize("disc_type", [DiscType.DATA, DiscType.UNKNOWN])
async def test_a_data_disc_has_no_match_section(disc_type: DiscType) -> None:
    found, _ = await identify(Fake(), ScanResult(disc_type=disc_type, volume_label="X"))
    assert found.result is None and found.match is None


async def test_the_search_stays_inside_the_call_budget() -> None:
    fake = Fake()
    for n in range(10):
        add_film(fake, ["Heat", "Heat 1995"], Film(n, f"Heat {n}", 1990 + n, 120, f"tt{n}"))
    found, _ = await identify(fake, dvd("HEAT_1995", 120), hint_ids=("label",))
    assert found.match is not None
    assert found.match.calls.list + found.match.calls.detail <= BUDGET
    assert calls(fake) <= BUDGET
