"""Dispatcher routing rules — uses respx to mock all three providers."""

import httpx
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
async def test_omdb_env_override_takes_precedence_over_config():
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=httpx.Response(200, json={"results": []}))
    respx.get("https://api.themoviedb.org/3/search/tv").mock(return_value=httpx.Response(200, json={"results": []}))
    omdb_route = respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200,
            json={"Response": "True", "Title": "Override Hit", "Year": "2001"},
        )
    )

    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, omdb_api_key_override="from-env")
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="OBSCURE")
        result = await dispatcher.identify(scan, _config(omdb_api_key="from-config"))
    assert result is not None
    assert result.title == "Override Hit"
    assert omdb_route.calls.last.request.url.params["apikey"] == "from-env"


@respx.mock
async def test_omdb_env_override_used_when_config_empty():
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=httpx.Response(200, json={"results": []}))
    respx.get("https://api.themoviedb.org/3/search/tv").mock(return_value=httpx.Response(200, json={"results": []}))
    omdb_route = respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200,
            json={"Response": "True", "Title": "Env Hit", "Year": "1999"},
        )
    )

    async with httpx.AsyncClient() as client:
        dispatcher = MetadataDispatcher(client, omdb_api_key_override="from-env")
        scan = ScanResult(disc_type=DiscType.DVD, volume_label="OBSCURE")
        result = await dispatcher.identify(scan, _config(omdb_api_key=None))
    assert result is not None
    assert result.title == "Env Hit"
    assert omdb_route.calls.last.request.url.params["apikey"] == "from-env"
