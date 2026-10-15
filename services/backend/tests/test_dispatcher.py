"""Dispatcher routing rules — uses respx to mock all three providers."""

import httpx
import pytest
import respx

from arm_backend.metadata.dispatcher import MetadataDispatcher, _normalize_volume_label
from arm_common import Config, DiscType
from arm_common.schemas import ScanResult


def _config(**overrides) -> Config:
    base = dict(
        id=1,
        tmdb_api_key="tmdb-k",
        omdb_api_key="omdb-k",
        musicbrainz_user_agent="arm-test/0.0 (t@example.com)",
    )
    base.update(overrides)
    return Config(**base)


def test_normalize_underscores_and_year():
    title, year = _normalize_volume_label("THE_MATRIX_1999")
    assert title == "THE MATRIX"
    assert year == 1999


def test_normalize_no_year():
    title, year = _normalize_volume_label("DVD_VIDEO")
    assert title == "DVD VIDEO"
    assert year is None


def test_normalize_strips_ntsc_token():
    # `_NTSC` at end, before a year, and case-insensitively — all should drop out.
    assert _normalize_volume_label("THE_MATRIX_NTSC") == ("THE MATRIX", None)
    assert _normalize_volume_label("THE_MATRIX_NTSC_1999") == ("THE MATRIX", 1999)
    assert _normalize_volume_label("the_matrix_ntsc") == ("the matrix", None)
    # But not when it's a substring of a larger word.
    assert _normalize_volume_label("MR_NTSCH") == ("MR NTSCH", None)


def test_normalize_strips_bluray_branding():
    # Underscore-, hyphen-, and space-delimited forms, with/without the
    # trademark glyph, case-insensitively — all should drop out.
    assert _normalize_volume_label("THE_MATRIX_BLU_RAY") == ("THE MATRIX", None)
    assert _normalize_volume_label("THE_MATRIX_BLU_RAY_1999") == ("THE MATRIX", 1999)
    assert _normalize_volume_label("Movie - Blu-rayTM") == ("Movie", None)
    assert _normalize_volume_label("Movie - BLU-RAY") == ("Movie", None)
    assert _normalize_volume_label("Movie Blu-ray™") == ("Movie", None)
    assert _normalize_volume_label("MOVIE_BLURAY") == ("MOVIE", None)
    # But a title that merely starts with "Blu" is left intact.
    assert _normalize_volume_label("BLUE_VELVET") == ("BLUE VELVET", None)


def test_normalize_strips_bd_token():
    # `_BD` at end and before a year drops out; substrings don't.
    assert _normalize_volume_label("THE_MATRIX_BD") == ("THE MATRIX", None)
    assert _normalize_volume_label("THE_MATRIX_BD_1999") == ("THE MATRIX", 1999)
    assert _normalize_volume_label("the_matrix_bd") == ("the matrix", None)
    # Not when it's a substring of a larger token (e.g. a BDRIP marker).
    assert _normalize_volume_label("MOVIE_BDRIP") == ("MOVIE BDRIP", None)


def test_normalize_preserves_unicode_titles():
    # NFKC keeps accents and non-Latin scripts intact so worldwide titles
    # still reach the providers (year still extracted where present).
    assert _normalize_volume_label("Amélie_2001") == ("Amélie", 2001)
    assert _normalize_volume_label("Café") == ("Café", None)
    assert _normalize_volume_label("Война_и_мир") == ("Война и мир", None)
    assert _normalize_volume_label("君の名は_2016") == ("君の名は", 2016)
    # But compatibility glyphs still fold: ™ → "TM", full-width → half-width.
    assert _normalize_volume_label("Movie Blu-ray™") == ("Movie", None)
    assert _normalize_volume_label("ＴＨＥ_ＭＡＴＲＩＸ_1999") == ("THE MATRIX", 1999)


@respx.mock
async def test_dispatcher_dvd_tmdb_movie_hit():
    respx.get("https://api.themoviedb.org/3/search/movie").mock(
        return_value=httpx.Response(200, json={"results": [{"title": "The Matrix", "release_date": "1999-03-31"}]})
    )
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="THE_MATRIX_1999")
        result = await dispatcher.identify(scan, _config())
    assert result is not None
    assert result.title == "The Matrix"
    assert result.kind == "movie"


@respx.mock
async def test_dispatcher_falls_back_through_providers():
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=httpx.Response(200, json={"results": []}))
    respx.get("https://api.themoviedb.org/3/search/tv").mock(return_value=httpx.Response(200, json={"results": []}))
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200,
            json={"Response": "True", "Title": "Found Via OMDB", "Year": "1995"},
        )
    )
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="OBSCURE_TITLE")
        result = await dispatcher.identify(scan, _config())
    assert result is not None
    assert result.title == "Found Via OMDB"


@respx.mock
async def test_dispatcher_all_miss_returns_none():
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=httpx.Response(200, json={"results": []}))
    respx.get("https://api.themoviedb.org/3/search/tv").mock(return_value=httpx.Response(200, json={"results": []}))
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(200, json={"Response": "False", "Error": "no"})
    )
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="NOPE")
        result = await dispatcher.identify(scan, _config())
    assert result is None


async def test_dispatcher_data_short_circuits():
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DATA, volume_label="WHATEVER")
        result = await dispatcher.identify(scan, _config())
    assert result is None


async def test_dispatcher_unknown_short_circuits():
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.UNKNOWN)
        result = await dispatcher.identify(scan, _config())
    assert result is None


@respx.mock
async def test_dispatcher_cd_uses_only_musicbrainz():
    respx.get("https://musicbrainz.org/ws/2/discid/some-disc").mock(
        return_value=httpx.Response(200, json={"releases": [{"title": "Album", "date": "1990-05-01"}]})
    )
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.CD, musicbrainz_disc_id="some-disc")
        result = await dispatcher.identify(scan, _config())
    assert result is not None
    assert result.kind == "music"


async def test_dispatcher_cd_without_disc_id_misses():
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.CD)
        result = await dispatcher.identify(scan, _config())
    assert result is None


@respx.mock
async def test_omdb_config_key_used_by_dispatcher():
    """OMDb key is read directly from cfg.omdb_api_key — no env override."""
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=httpx.Response(200, json={"results": []}))
    respx.get("https://api.themoviedb.org/3/search/tv").mock(return_value=httpx.Response(200, json={"results": []}))
    omdb_route = respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200,
            json={"Response": "True", "Title": "Config Hit", "Year": "2001"},
        )
    )

    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="OBSCURE")
        result = await dispatcher.identify(scan, _config(omdb_api_key="from-config"))
    assert result is not None
    assert result.title == "Config Hit"
    assert omdb_route.calls.last.request.url.params["apikey"] == "from-config"


async def test_identify_tries_title_hint_before_volume_label(monkeypatch):
    """The dispatcher searches the hint title first; a hit there must not
    reach the label-derived title at all."""
    from arm_backend.metadata import sources as sources_mod
    from arm_backend.metadata.base import MetadataResult

    searched_titles: list[str] = []

    class FakeTMDB:
        def __init__(self, api_key, http):  # matches TMDBClient signature
            pass

        async def search_movie(self, title, year):
            searched_titles.append(title)
            return None

        async def search_tv(self, title):
            searched_titles.append(title)
            if title == "the west wing":
                return MetadataResult(title="The West Wing", year=1999, kind="tv")
            return None

    monkeypatch.setattr(sources_mod, "TMDBClient", FakeTMDB)
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="WW_S3D2")
        result = await dispatcher.identify(scan, _config(), title_hint="the west wing")
    assert result is not None and result.title == "The West Wing"
    assert searched_titles[0] == "the west wing"
    # The label-derived title ("WW S3D2") must never have been searched.
    assert "WW S3D2" not in searched_titles


async def test_identify_falls_back_to_label_when_hint_misses(monkeypatch):
    """A hint that misses on every provider falls back to the normalized
    volume-label title as the next candidate."""
    from arm_backend.metadata import sources as sources_mod
    from arm_backend.metadata.base import MetadataResult

    searched_titles: list[str] = []

    class FakeTMDB:
        def __init__(self, api_key, http):
            pass

        async def search_movie(self, title, year):
            searched_titles.append(title)
            return None

        async def search_tv(self, title):
            searched_titles.append(title)
            if title == "WW S3D2":
                return MetadataResult(title="The West Wing", year=1999, kind="tv")
            return None

    monkeypatch.setattr(sources_mod, "TMDBClient", FakeTMDB)
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="WW_S3D2")
        result = await dispatcher.identify(scan, _config(), title_hint="wrong hint")
    assert result is not None and result.title == "The West Wing"
    assert searched_titles[0] == "wrong hint"
    assert searched_titles[-1] == "WW S3D2"


async def test_identify_dedupes_hint_equal_to_label(monkeypatch):
    """Realistic pairing: a BD title hint ("arrival", from bd_meta name
    "Arrival") equal to the normalised label title (volume_label "ARRIVAL",
    case-insensitive) is searched only once per provider call, not once per
    candidate."""
    from arm_backend.metadata import sources as sources_mod

    call_counts: dict[str, int] = {}

    class FakeTMDB:
        def __init__(self, api_key, http):
            pass

        async def search_movie(self, title, year):
            call_counts[title] = call_counts.get(title, 0) + 1
            return None

        async def search_tv(self, title):
            call_counts[title] = call_counts.get(title, 0) + 1
            return None

    monkeypatch.setattr(sources_mod, "TMDBClient", FakeTMDB)
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="ARRIVAL")
        result = await dispatcher.identify(scan, _config(omdb_api_key=None), title_hint="arrival")
    assert result is None
    # movie + tv called once each, for the hint's own casing — the label
    # candidate ("ARRIVAL") was deduped away (same casefold key).
    assert call_counts == {"arrival": 2}


async def test_identify_hint_is_tv_searches_tv_before_movie(monkeypatch):
    """A season-shaped hint (title_hint_is_tv=True) searches TMDb TV first for
    that candidate, so a TV-shaped label like `LOST_S2D3` doesn't mismatch to
    TMDb's top movie hit."""
    from arm_backend.metadata import sources as sources_mod
    from arm_backend.metadata.base import MetadataResult

    call_order: list[str] = []

    class FakeTMDB:
        def __init__(self, api_key, http):
            pass

        async def search_movie(self, title, year):
            call_order.append("movie")
            return None

        async def search_tv(self, title):
            call_order.append("tv")
            return MetadataResult(title="Lost", year=2004, kind="tv")

    monkeypatch.setattr(sources_mod, "TMDBClient", FakeTMDB)
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="LOST_S2D3")
        result = await dispatcher.identify(scan, _config(), title_hint="lost", title_hint_is_tv=True)
    assert result is not None and result.title == "Lost"
    assert call_order[0] == "tv"


async def test_identify_hint_not_tv_keeps_movie_first_order(monkeypatch):
    """title_hint_is_tv=False (the default) keeps the existing movie-first
    order for the hint candidate."""
    from arm_backend.metadata import sources as sources_mod
    from arm_backend.metadata.base import MetadataResult

    call_order: list[str] = []

    class FakeTMDB:
        def __init__(self, api_key, http):
            pass

        async def search_movie(self, title, year):
            call_order.append("movie")
            return MetadataResult(title="Arrival", year=2016, kind="movie")

        async def search_tv(self, title):
            call_order.append("tv")
            return None

    monkeypatch.setattr(sources_mod, "TMDBClient", FakeTMDB)
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="ARRIVAL")
        result = await dispatcher.identify(scan, _config(), title_hint="arrival", title_hint_is_tv=False)
    assert result is not None and result.title == "Arrival"
    assert call_order[0] == "movie"


async def test_identify_tv_first_falls_back_to_movie_when_tv_misses(monkeypatch):
    """When title_hint_is_tv=True, the TV search runs first; if it misses,
    the movie search is tried as a fallback, and returns if it hits."""
    from arm_backend.metadata import sources as sources_mod
    from arm_backend.metadata.base import MetadataResult

    call_order: list[str] = []

    class FakeTMDB:
        def __init__(self, api_key, http):
            pass

        async def search_movie(self, title, year):
            call_order.append("movie")
            # Return a movie hit when TV missed
            return MetadataResult(title="Tron", year=1982, kind="movie")

        async def search_tv(self, title):
            call_order.append("tv")
            # TV search misses
            return None

    monkeypatch.setattr(sources_mod, "TMDBClient", FakeTMDB)
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="TRON")
        result = await dispatcher.identify(scan, _config(), title_hint="tron", title_hint_is_tv=True)
    assert result is not None and result.title == "Tron"
    # TV was searched first due to tv_first=True, then movie fallback found it
    assert call_order[0] == "tv"
    assert call_order[1] == "movie"


@respx.mock
async def test_identify_hint_is_tv_without_a_tv_source_falls_to_the_movie_walk():
    """No TMDb key and OMDb is not a TV source: the TV walk is empty, so a
    TV-shaped hint falls to the movie walk (OMDb `type=movie`). TVmaze (PR 2b)
    fills the TV walk for keyless installs."""
    omdb_route = respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200,
            json={"Response": "True", "Title": "Lost", "Year": "2004"},
        )
    )
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="LOST_S2D3")
        result = await dispatcher.identify(scan, _config(tmdb_api_key=None), title_hint="lost", title_hint_is_tv=True)
    assert result is not None and result.title == "Lost" and result.kind == "movie"
    assert omdb_route.call_count == 1
    assert omdb_route.calls.last.request.url.params["type"] == "movie"


@respx.mock
async def test_identify_hint_is_tv_tmdb_tv_miss_then_movie_walk():
    """With both keys: the TV walk is TMDb TV (miss); the movie walk is TMDb
    movie (miss) then OMDb `type=movie`."""
    respx.get("https://api.themoviedb.org/3/search/tv").mock(return_value=httpx.Response(200, json={"results": []}))
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=httpx.Response(200, json={"results": []}))
    omdb_route = respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200,
            json={"Response": "True", "Title": "Lost", "Year": "2004"},
        )
    )
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="LOST_S2D3")
        result = await dispatcher.identify(scan, _config(), title_hint="lost", title_hint_is_tv=True)
    assert result is not None and result.title == "Lost"
    assert omdb_route.call_count == 1
    assert omdb_route.calls.last.request.url.params["type"] == "movie"


@respx.mock
async def test_identify_hint_not_tv_uses_omdb_movie_when_no_tmdb_key():
    """title_hint_is_tv=False keeps the OMDb `type=movie` param (the
    pre-existing behaviour)."""
    omdb_route = respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200,
            json={"Response": "True", "Title": "Arrival", "Year": "2016"},
        )
    )
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="ARRIVAL")
        result = await dispatcher.identify(
            scan, _config(tmdb_api_key=None), title_hint="arrival", title_hint_is_tv=False
        )
    assert result is not None and result.title == "Arrival"
    assert omdb_route.calls.last.request.url.params["type"] == "movie"


async def test_identify_hint_candidate_reuses_label_year(monkeypatch):
    """The hint candidate has no year of its own; it must be searched with
    the same year the label candidate parsed (e.g. `ALIEN_1979` narrows
    the hint "alien" to 1979 too), not an unfiltered search."""
    from arm_backend.metadata import sources as sources_mod

    seen_years: dict[str, int | None] = {}

    class FakeTMDB:
        def __init__(self, api_key, http):
            pass

        async def search_movie(self, title, year):
            seen_years[title] = year
            return None

        async def search_tv(self, title):
            return None

    monkeypatch.setattr(sources_mod, "TMDBClient", FakeTMDB)
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="ALIEN_1979")
        result = await dispatcher.identify(scan, _config(omdb_api_key=None), title_hint="alien")
    assert result is None
    assert seen_years["alien"] == 1979


async def test_identify_retries_hint_without_trailing_year(monkeypatch):
    """A hint ending in a year is searched as given first (WONDER_WOMAN_1984),
    then without the year (THE_OFFICE_2005), before the label title."""
    from arm_backend.metadata import sources as sources_mod
    from arm_backend.metadata.base import MetadataResult

    searched_titles: list[str] = []

    class FakeTMDB:
        def __init__(self, api_key, http):
            pass

        async def search_movie(self, title, year):
            searched_titles.append(title)
            return None

        async def search_tv(self, title):
            searched_titles.append(title)
            if title == "the office":
                return MetadataResult(title="The Office", year=2005, kind="tv")
            return None

    monkeypatch.setattr(sources_mod, "TMDBClient", FakeTMDB)
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="THE_OFFICE_2005_S1_D2")
        result = await dispatcher.identify(
            scan, _config(omdb_api_key=None), title_hint="the office 2005", title_hint_is_tv=True
        )
    assert result is not None and result.title == "The Office"
    assert searched_titles == ["the office 2005", "the office 2005", "the office"]


async def test_identify_keeps_a_hint_that_is_only_a_year(monkeypatch):
    """A hint that is all year ("1917") is searched once, never as an empty title."""
    from arm_backend.metadata import sources as sources_mod

    searched_titles: list[str] = []

    class FakeTMDB:
        def __init__(self, api_key, http):
            pass

        async def search_movie(self, title, year):
            searched_titles.append(title)
            return None

        async def search_tv(self, title):
            searched_titles.append(title)
            return None

    monkeypatch.setattr(sources_mod, "TMDBClient", FakeTMDB)
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="1917_D1")
        result = await dispatcher.identify(scan, _config(omdb_api_key=None), title_hint="1917")
    assert result is None
    assert "" not in searched_titles
    assert searched_titles.count("1917") == 2  # movie then TV, one candidate


async def test_identify_from_imdb_walks_the_ranked_sources():
    """D-1: the exact-id lookup asks the enabled sources for the kind in rank
    order; an unconfigured source is skipped and the hit carries its source id."""
    from arm_backend.metadata.base import MetadataResult

    calls: list[str] = []

    def _source(sid: str, reason: str | None, hit: MetadataResult | None):
        class S:
            id = sid
            media_types = frozenset({"movie", "tv"})
            requires_key = None

            def configured(self, cfg):
                return reason

            async def lookup_imdb(self, cfg, imdb_id):
                calls.append(f"{sid}:{imdb_id}")
                return hit

        return S()

    reg = {
        "tmdb": _source("tmdb", "no tmdb key", MetadataResult(title="T", year=None, kind="movie")),
        "omdb": _source("omdb", None, MetadataResult(title="Round Midnight", year=1986, kind="movie")),
    }
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources=reg)
        hit = await dispatcher.identify_from_imdb("tt0090557", _config(movie_sources=["tmdb", "omdb"]))
        assert hit is not None and hit.title == "Round Midnight" and hit.provider == "omdb"
        assert hit.payload["imdb_id"] == "tt0090557"
        assert calls == ["omdb:tt0090557"]
        assert await dispatcher.identify_from_imdb("", _config()) is None
        assert await dispatcher.identify_from_imdb("tt1", _config(movie_sources=[])) is None
        assert dispatcher.has_imdb_lookup(_config(movie_sources=["tmdb", "omdb"]), "movie") is True
        assert dispatcher.has_imdb_lookup(_config(movie_sources=["tmdb"]), "movie") is False  # tmdb unkeyed
        assert dispatcher.has_imdb_lookup(_config(movie_sources=[]), "movie") is False


async def test_identify_from_imdb_falls_through_a_miss_to_the_next_source():
    from arm_backend.metadata.base import MetadataResult

    calls: list[str] = []

    def _source(sid: str, hit: MetadataResult | None):
        class S:
            id = sid
            media_types = frozenset({"movie", "tv"})
            requires_key = None

            def configured(self, cfg):
                return None

            async def lookup_imdb(self, cfg, imdb_id):
                calls.append(f"{sid}:{imdb_id}")
                return hit

        return S()

    reg = {"tmdb": _source("tmdb", None), "omdb": _source("omdb", MetadataResult(title="T", year=None, kind="movie"))}
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources=reg)
        hit = await dispatcher.identify_from_imdb("tt1", _config(movie_sources=["tmdb", "omdb"]))
    assert hit is not None and hit.provider == "omdb"
    assert calls == ["tmdb:tt1", "omdb:tt1"]


async def test_identify_from_imdb_uses_the_kind_list():
    from arm_backend.metadata.base import MetadataResult

    kinds: list[str] = []

    class Omdb:
        id = "omdb"
        media_types = frozenset({"movie", "tv"})
        requires_key = None

        def configured(self, cfg):
            return None

        async def lookup_imdb(self, cfg, imdb_id):
            kinds.append("called")
            return MetadataResult(title="Lost", year=2004, kind="tv")

    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources={"omdb": Omdb()})
        cfg = _config(movie_sources=[], episode_sources=["tmdb", "tvmaze"])
        # OMDb is not in the TV list: no TV source offers the lookup.
        assert await dispatcher.identify_from_imdb("tt0411008", cfg, kind="tv") is None
        assert dispatcher.has_imdb_lookup(cfg, "tv") is False
        assert kinds == []
        cfg = _config(movie_sources=["omdb"], episode_sources=[])
        hit = await dispatcher.identify_from_imdb("tt0411008", cfg, kind="movie")
        assert hit is not None and hit.kind == "tv" and kinds == ["called"]


async def test_label_candidate_skipped_when_the_label_hint_is_ignored():
    """D-4: with `label` removed from disc_hint_sources the volume label is not
    searched; only the hint title (and its year-free retry) is."""
    searched: list[str] = []

    class Tmdb:
        id = "tmdb"
        media_types = frozenset({"movie", "tv"})
        requires_key = None

        def configured(self, cfg):
            return None

        async def search_title(self, cfg, kind, title, year):
            searched.append(f"{kind}:{title}:{year}")
            return None

    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources={"tmdb": Tmdb()})
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="HEAT_1995")
        cfg = _config(disc_hint_sources=["bd_title"], movie_sources=["tmdb"], episode_sources=["tmdb"])
        assert await dispatcher.identify(scan, cfg) is None
        assert searched == []
        assert await dispatcher.identify(scan, cfg, title_hint="Heat") is None
    # The label's year still narrows the hint search (D-4 gates the candidate, not the year).
    assert searched == ["movie:Heat:1995", "tv:Heat:1995"]


async def test_label_candidate_searched_when_the_label_hint_is_enabled():
    searched: list[str] = []

    class Tmdb:
        id = "tmdb"
        media_types = frozenset({"movie", "tv"})
        requires_key = None

        def configured(self, cfg):
            return None

        async def search_title(self, cfg, kind, title, year):
            searched.append(f"{kind}:{title}")
            return None

    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources={"tmdb": Tmdb()})
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="HEAT_1995")
        cfg = _config(disc_hint_sources=["bd_title", "label"], movie_sources=["tmdb"], episode_sources=["tmdb"])
        assert await dispatcher.identify(scan, cfg) is None
    assert searched == ["movie:HEAT", "tv:HEAT"]


@respx.mock
async def test_omdb_skipped_when_config_key_empty():
    """When cfg.omdb_api_key is None the OMDb branch is skipped entirely."""
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=httpx.Response(200, json={"results": []}))
    respx.get("https://api.themoviedb.org/3/search/tv").mock(return_value=httpx.Response(200, json={"results": []}))
    # OMDb must NOT be called — any unexpected call will raise via respx strict mode.
    omdb_route = respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200,
            json={"Response": "True", "Title": "Should Not Appear", "Year": "1999"},
        )
    )

    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="OBSCURE")
        result = await dispatcher.identify(scan, _config(omdb_api_key=None))
    assert result is None
    assert omdb_route.call_count == 0


@pytest.mark.asyncio
async def test_call_stamps_the_source_id_as_provider() -> None:
    """_call is the one place that knows which source produced a hit; it
    stamps MetadataResult.provider with the source id so identity and
    provider_raw key on it, overwriting anything the client set."""
    from arm_backend.metadata.base import MetadataResult

    dispatcher = MetadataDispatcher(httpx.AsyncClient())

    async def _hit() -> MetadataResult:
        return MetadataResult(title="X", year=None, kind="movie", payload={}, provider="spoofed")

    for sid in ("tmdb", "omdb", "arm_server", "musicbrainz"):
        result = await dispatcher._call(sid, _hit())
        assert result is not None and result.provider == sid, sid

    async def _miss() -> None:
        return None

    assert await dispatcher._call("tmdb", _miss()) is None
    await dispatcher.aclose()


async def test_identify_prefer_tv_searches_tv_first_for_every_candidate(monkeypatch):
    """An episodic disc (prefer_tv) searches TMDb TV before movie for the hint
    AND the label candidate. Kolchak: TMDb's movie search returns a placeholder
    "Kolchak: The Night Stalker Collection" entry; TV finds the 1974 series."""
    from arm_backend.metadata import dispatcher as dispatcher_mod
    from arm_backend.metadata import sources as sources_mod
    from arm_backend.metadata.base import MetadataResult

    calls: list[str] = []

    class FakeTMDB:
        def __init__(self, api_key, http):
            pass

        async def search_movie(self, title, year):
            calls.append(f"movie:{title}")
            return MetadataResult(title="Kolchak: The Night Stalker Collection", year=None, kind="movie", payload={})

        async def search_tv(self, title):
            calls.append(f"tv:{title}")
            if title == "kolchak the night stalker":
                return None  # the hint misses on TV; the label candidate must still try TV first
            return MetadataResult(title="Kolchak: The Night Stalker", year=1974, kind="tv", payload={"id": 5084})

        async def get_external_id_map(self, tmdb_id, kind):
            return {}

    monkeypatch.setattr(sources_mod, "TMDBClient", FakeTMDB)
    monkeypatch.setattr(dispatcher_mod, "TMDBClient", FakeTMDB)  # the id enrichment in _with_tmdb_ids
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.BLURAY, volume_label="KOLCHAK_NIGHT_STALKER")
        result = await dispatcher.identify(
            scan, _config(omdb_api_key=None), title_hint="kolchak the night stalker", prefer_tv=True
        )
    assert result is not None and result.kind == "tv" and result.year == 1974
    # TV across every candidate before any movie search: the hint's movie
    # fallback (the placeholder) must never be reached while TV can still hit.
    assert calls[0] == "tv:kolchak the night stalker"
    assert len(calls) == 2 and calls[1].startswith("tv:")


async def test_two_candidates_walk_kind_major_per_candidate(monkeypatch):
    """Per candidate, each kind asks every source before the next kind; the
    second candidate starts only after the first is exhausted."""
    from arm_backend.metadata import dispatcher as dispatcher_mod
    from arm_backend.metadata import sources as sources_mod
    from arm_backend.metadata.base import MetadataResult

    calls: list[str] = []

    class FakeTMDB:
        def __init__(self, api_key, http):
            pass

        async def search_movie(self, title, year):
            calls.append(f"tmdb:movie:{title}")

        async def search_tv(self, title):
            calls.append(f"tmdb:tv:{title}")
            if title == "BETA":
                return MetadataResult(title="Hit", year=None, kind="tv")

    class FakeOMDB:
        def __init__(self, api_key, http):
            pass

        async def lookup_by_title(self, title, year, kind):
            calls.append(f"omdb:{kind}:{title}")

    monkeypatch.setattr(sources_mod, "TMDBClient", FakeTMDB)
    monkeypatch.setattr(dispatcher_mod, "TMDBClient", FakeTMDB)
    monkeypatch.setattr(sources_mod, "OMDBClient", FakeOMDB)
    async with httpx.AsyncClient() as client:
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="BETA")
        result = await MetadataDispatcher(client).identify(scan, _config(), title_hint="alpha")
    assert calls == [
        "tmdb:movie:alpha", "omdb:movie:alpha", "tmdb:tv:alpha",
        "tmdb:movie:BETA", "omdb:movie:BETA", "tmdb:tv:BETA",
    ]  # fmt: skip
    assert result is not None and result.title == "Hit" and result.provider == "tmdb"


async def test_identify_prefer_tv_omdb_only_has_no_tv_source_and_searches_movie(monkeypatch):
    """No TMDb key: OMDb is not a TV source, so an episodic disc only asks OMDb for a movie."""
    from arm_backend.metadata import sources as sources_mod

    kinds: list[str] = []

    class FakeOMDB:
        def __init__(self, api_key, http):
            pass

        async def lookup_by_title(self, title, year, kind):
            kinds.append(kind)
            return None

    monkeypatch.setattr(sources_mod, "OMDBClient", FakeOMDB)
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="SHOW_DISC_1")
        result = await dispatcher.identify(scan, _config(tmdb_api_key=None, omdb_api_key="k"), prefer_tv=True)
    assert result is None
    assert kinds == ["movie"]


async def test_identify_prefer_tv_with_no_provider_finds_nothing(monkeypatch):
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="SHOW_DISC_1")
        assert await dispatcher.identify(scan, _config(tmdb_api_key=None, omdb_api_key=None), prefer_tv=True) is None


@respx.mock
async def test_identify_enriches_the_tmdb_tv_hit_with_imdb_and_tvdb():
    respx.get("https://api.themoviedb.org/3/search/tv").mock(
        return_value=httpx.Response(
            200, json={"results": [{"id": 5084, "name": "Kolchak: The Night Stalker", "first_air_date": "1974-09-13"}]}
        )
    )
    respx.get("https://api.themoviedb.org/3/tv/5084/external_ids").mock(
        return_value=httpx.Response(200, json={"imdb_id": "tt0071003", "tvdb_id": 77170})
    )
    async with httpx.AsyncClient() as client:
        scan = ScanResult(disc_type=DiscType.BLURAY, volume_label="KOLCHAK")
        hit = await MetadataDispatcher(client).identify(
            scan, _config(omdb_api_key=None), title_hint="kolchak", title_hint_is_tv=True
        )
    assert hit is not None and hit.provider == "tmdb"
    assert (hit.payload["imdb_id"], hit.payload["tvdb_id"]) == ("tt0071003", "77170")


@respx.mock
async def test_identify_keeps_the_hit_when_enrichment_fails():
    respx.get("https://api.themoviedb.org/3/search/movie").mock(
        return_value=httpx.Response(
            200, json={"results": [{"id": 603, "title": "The Matrix", "release_date": "1999-03-31"}]}
        )
    )
    respx.get("https://api.themoviedb.org/3/movie/603/external_ids").mock(return_value=httpx.Response(500))
    async with httpx.AsyncClient() as client:
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="THE_MATRIX_1999")
        hit = await MetadataDispatcher(client).identify(scan, _config())
    assert hit is not None and hit.title == "The Matrix" and "tvdb_id" not in hit.payload


@respx.mock
async def test_identify_from_imdb_keeps_the_known_imdb_and_adds_tvdb():
    respx.get("https://api.themoviedb.org/3/find/tt0071003").mock(
        return_value=httpx.Response(
            200,
            json={
                "movie_results": [],
                "tv_results": [{"id": 5084, "name": "Kolchak: The Night Stalker", "first_air_date": "1974-09-13"}],
            },
        )
    )
    respx.get("https://api.themoviedb.org/3/tv/5084/external_ids").mock(
        return_value=httpx.Response(200, json={"imdb_id": "tt0071003", "tvdb_id": 77170})
    )
    async with httpx.AsyncClient() as client:
        hit = await MetadataDispatcher(client).identify_from_imdb("tt0071003", _config())
    assert hit is not None and hit.kind == "tv"
    assert (hit.payload["imdb_id"], hit.payload["tvdb_id"]) == ("tt0071003", "77170")


async def test_with_tmdb_ids_skips_non_tmdb_keyless_and_idless_hits():
    from arm_backend.metadata.base import MetadataResult

    async with httpx.AsyncClient() as client:
        d = MetadataDispatcher(client)
        omdb = MetadataResult(provider="omdb", kind="movie", title="X", year=1999, payload={"imdbID": "tt1"})
        assert await d._with_tmdb_ids(None, _config()) is None
        assert await d._with_tmdb_ids(omdb, _config()) is omdb
        tmdb_hit = MetadataResult(provider="tmdb", kind="movie", title="X", year=1999, payload={"id": 1})
        assert await d._with_tmdb_ids(tmdb_hit, _config(tmdb_api_key=None)) is tmdb_hit
        assert "imdb_id" not in tmdb_hit.payload
        idless = MetadataResult(provider="tmdb", kind="movie", title="X", year=1999, payload={})
        assert await d._with_tmdb_ids(idless, _config()) is idless
        assert idless.payload == {}


async def test_with_tmdb_ids_timeout_keeps_the_hit(monkeypatch):
    """A slow `external_ids` call is bounded by PROVIDER_TIMEOUT_SECONDS; on
    timeout the hit is returned unchanged."""
    import asyncio

    from arm_backend.metadata import dispatcher as dispatcher_mod
    from arm_backend.metadata.base import MetadataResult
    from arm_backend.metadata.tmdb import TMDBClient

    async def slow(self, tmdb_id, kind):
        await asyncio.sleep(10)
        return {"imdb_id": "tt9"}

    monkeypatch.setattr(TMDBClient, "get_external_id_map", slow)
    monkeypatch.setattr(dispatcher_mod, "PROVIDER_TIMEOUT_SECONDS", 0.01)
    async with httpx.AsyncClient() as client:
        hit = MetadataResult(provider="tmdb", kind="tv", title="X", year=1999, payload={"id": 1})
        assert await MetadataDispatcher(client)._with_tmdb_ids(hit, _config()) is hit
    assert hit.payload == {"id": 1}


async def test_title_search_is_kind_major(monkeypatch):
    """All movie sources before any TV source for a movie-shaped candidate:
    tmdb movie, omdb movie, tmdb tv (spec D-6). OMDb is a movie source only in
    the automatic order."""
    from arm_backend.metadata import sources as sources_mod

    order: list[str] = []

    class FakeTMDB:
        def __init__(self, api_key, http):
            pass

        async def search_movie(self, title, year):
            order.append("tmdb:movie")
            return None

        async def search_tv(self, title):
            order.append("tmdb:tv")
            return None

    class FakeOMDB:
        def __init__(self, api_key, http):
            pass

        async def lookup_by_title(self, title, year=None, kind="movie"):
            order.append(f"omdb:{kind}")
            return None

    monkeypatch.setattr(sources_mod, "TMDBClient", FakeTMDB)
    monkeypatch.setattr(sources_mod, "OMDBClient", FakeOMDB)
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="SOMETHING")
        assert await dispatcher.identify(scan, _config()) is None
    assert order == ["tmdb:movie", "omdb:movie", "tmdb:tv"]


async def test_dispatcher_accepts_an_injected_registry():
    from arm_backend.metadata.base import MetadataResult

    class OnlyOmdb:
        id = "omdb"
        media_types = frozenset({"movie", "tv"})
        requires_key = "omdb_api_key"

        def configured(self, cfg):
            return None

        async def search_title(self, cfg, kind, title, year):
            return MetadataResult(title=f"{kind}:{title}", year=year, kind=kind)

    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources={"omdb": OnlyOmdb()})
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="BLADE_RUNNER_1982")
        hit = await dispatcher.identify(scan, _config(tmdb_api_key=None, omdb_api_key=None))
    assert hit is not None and hit.title == "movie:BLADE RUNNER" and hit.provider == "omdb"
    assert dispatcher.sources["omdb"].id == "omdb"


def _recording_source(sid, calls, media_types=frozenset({"movie", "tv"})):

    class Fake:
        id = sid
        requires_key = None

        def configured(self, cfg):
            return None

        async def search_title(self, cfg, kind, title, year):
            calls.append(f"{sid}:{kind}")
            return None

    Fake.media_types = media_types
    return Fake()


async def test_movie_order_follows_movie_sources():
    calls: list[str] = []
    reg = {"tmdb": _recording_source("tmdb", calls), "omdb": _recording_source("omdb", calls)}
    scan = ScanResult(disc_type=DiscType.DVD, volume_label="HEAT_1995")
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources=reg)
        await dispatcher.identify(scan, _config(movie_sources=["omdb", "tmdb"]))
        movie_calls = [c for c in calls if c.endswith(":movie")]
        assert movie_calls == ["omdb:movie", "tmdb:movie"]
        calls.clear()
        await dispatcher.identify(scan, _config(movie_sources=[]))
    assert [c for c in calls if c.endswith(":movie")] == []
    assert calls == ["tmdb:tv"]


async def test_tv_order_follows_episode_sources():
    """The TV title walk reads the operator's episode list; ids with no adapter
    yet (tvmaze, tvdb) are skipped and OMDb is not in the list (spec §10)."""
    calls: list[str] = []

    def _source(sid: str):
        class S:
            id = sid
            media_types = frozenset({"movie", "tv"})
            requires_key = None

            def configured(self, cfg):
                return None

            async def search_title(self, cfg, kind, title, year):
                calls.append(f"{sid}:{kind}")
                return None

        return S()

    reg = {"tmdb": _source("tmdb"), "omdb": _source("omdb")}
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources=reg)
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="SHOW_DISC_1")
        cfg = _config(movie_sources=[], episode_sources=["tvmaze", "tmdb", "tvdb"])
        assert await dispatcher.identify(scan, cfg, prefer_tv=True) is None
    assert calls == ["tmdb:tv"]
    calls.clear()
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources=reg)
        cfg = _config(movie_sources=["omdb"], episode_sources=["tvmaze"])
        assert await dispatcher.identify(scan, cfg) is None
    assert calls == ["omdb:movie"]


async def test_crc64_lookup_skipped_when_the_switch_is_off():
    from arm_backend.metadata.base import MetadataResult

    calls: list[str] = []

    class FakeArmServer:
        id = "arm_server"
        media_types = frozenset({"movie"})
        requires_key = None

        def configured(self, cfg):
            return None

        async def lookup_fingerprint(self, cfg, algo, value):
            calls.append(value)
            return MetadataResult(title="Iron Man", year=2008, kind="movie")

    reg = {"arm_server": FakeArmServer(), "tmdb": _recording_source("tmdb", [])}
    scan = ScanResult(disc_type=DiscType.DVD, volume_label="X", fingerprints=[{"algo": "crc64", "value": "abc"}])
    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, sources=reg)
        await dispatcher.identify(scan, _config(crc64service_enabled=False))
        assert calls == []
        hit = await dispatcher.identify(scan, _config())
    assert calls == ["abc"] and hit is not None and hit.title == "Iron Man"
