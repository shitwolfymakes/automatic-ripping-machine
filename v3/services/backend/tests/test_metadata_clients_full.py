"""Branch coverage for the metadata clients + base helpers.

Complements test_metadata_clients.py (happy paths) with every error path:
timeouts, transport errors, 5xx/non-200, misses, missing-title, year-parse
edges, the ArmServer (1337server) client, the MusicBrainz rate limiter,
and extract_poster_url's provider precedence.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import httpx  # noqa: E402
import pytest  # noqa: E402
import respx  # noqa: E402

from arm_backend.metadata import musicbrainz as mb_mod  # noqa: E402
from arm_backend.metadata.arm_server import ArmServerClient  # noqa: E402
from arm_backend.metadata.base import (  # noqa: E402
    LookupError,
    LookupTimeout,
    MetadataResult,
    extract_poster_url,
)
from arm_backend.metadata.musicbrainz import MusicBrainzClient  # noqa: E402
from arm_backend.metadata.omdb import OMDBClient  # noqa: E402
from arm_backend.metadata.tmdb import TMDBClient  # noqa: E402


@pytest.fixture
async def http_client():  # type: ignore[no-untyped-def]
    async with httpx.AsyncClient(timeout=5.0) as client:
        yield client


# --- extract_poster_url ------------------------------------------------------


def test_poster_tmdb_path() -> None:
    r = MetadataResult(title="T", year=1, kind="movie", payload={"poster_path": "/p.jpg"})
    assert extract_poster_url(r) == "https://image.tmdb.org/t/p/w500/p.jpg"


def test_poster_omdb_full_url() -> None:
    r = MetadataResult(title="T", year=1, kind="movie", payload={"Poster": "http://x/y.jpg"})
    assert extract_poster_url(r) == "http://x/y.jpg"


def test_poster_omdb_na_rejected() -> None:
    r = MetadataResult(title="T", year=1, kind="movie", payload={"Poster": "N/A"})
    assert extract_poster_url(r) is None


def test_poster_musicbrainz_caa() -> None:
    r = MetadataResult(title="T", year=1, kind="music", payload={"id": "mbid-1"})
    assert extract_poster_url(r) == "https://coverartarchive.org/release/mbid-1/front"


def test_poster_music_without_id_none() -> None:
    r = MetadataResult(title="T", year=1, kind="music", payload={})
    assert extract_poster_url(r) is None


def test_poster_none_when_nothing_applies() -> None:
    r = MetadataResult(title="T", year=1, kind="movie", payload={})
    assert extract_poster_url(r) is None


# --- OMDB --------------------------------------------------------------------


@respx.mock
async def test_omdb_timeout(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get("https://www.omdbapi.com/").mock(side_effect=httpx.TimeoutException("t"))
    with pytest.raises(LookupTimeout):
        await OMDBClient("k", http_client).lookup_by_title("x")


@respx.mock
async def test_omdb_transport_error(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get("https://www.omdbapi.com/").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(LookupError):
        await OMDBClient("k", http_client).lookup_by_title("x")


@respx.mock
async def test_omdb_auth_failed(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get("https://www.omdbapi.com/").mock(return_value=httpx.Response(401))
    with pytest.raises(LookupError, match="auth failed"):
        await OMDBClient("k", http_client).lookup_by_title("x")


@respx.mock
async def test_omdb_5xx_and_other(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get("https://www.omdbapi.com/").mock(return_value=httpx.Response(503))
    with pytest.raises(LookupError, match="5xx"):
        await OMDBClient("k", http_client).lookup_by_title("x")
    respx.get("https://www.omdbapi.com/").mock(return_value=httpx.Response(404))
    with pytest.raises(LookupError, match="status=404"):
        await OMDBClient("k", http_client).lookup_by_title("x")


@respx.mock
async def test_omdb_missing_title(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(200, json={"Response": "True", "Year": "2010"})
    )
    with pytest.raises(LookupError, match="missing title"):
        await OMDBClient("k", http_client).lookup_by_title("x")


@respx.mock
async def test_omdb_hit_with_unparseable_year(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(200, json={"Response": "True", "Title": "Movie", "Year": "n/a"})
    )
    result = await OMDBClient("k", http_client).lookup_by_title("Movie")
    assert result.title == "Movie"
    assert result.year is None


# --- TMDB --------------------------------------------------------------------


@respx.mock
async def test_tmdb_timeout(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get("https://api.themoviedb.org/3/search/movie").mock(side_effect=httpx.TimeoutException("t"))
    with pytest.raises(LookupTimeout):
        await TMDBClient("k", http_client).search_movie("x")


@respx.mock
async def test_tmdb_transport_error(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get("https://api.themoviedb.org/3/search/movie").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(LookupError, match="transport error"):
        await TMDBClient("k", http_client).search_movie("x")


@respx.mock
async def test_tmdb_5xx_and_other(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=httpx.Response(500))
    with pytest.raises(LookupError, match="5xx"):
        await TMDBClient("k", http_client).search_movie("x")
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=httpx.Response(403))
    with pytest.raises(LookupError, match="status=403"):
        await TMDBClient("k", http_client).search_movie("x")


@respx.mock
async def test_tmdb_tv_hit(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get("https://api.themoviedb.org/3/search/tv").mock(
        return_value=httpx.Response(200, json={"results": [{"name": "The Wire", "first_air_date": "2002-06-02"}]})
    )
    result = await TMDBClient("k", http_client).search_tv("the wire")
    assert result.title == "The Wire"
    assert result.year == 2002
    assert result.kind == "tv"


@respx.mock
async def test_tmdb_tv_missing_title(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get("https://api.themoviedb.org/3/search/tv").mock(
        return_value=httpx.Response(200, json={"results": [{"first_air_date": "2002"}]})
    )
    with pytest.raises(LookupError, match="missing title"):
        await TMDBClient("k", http_client).search_tv("x")


@respx.mock
async def test_tmdb_movie_original_title_fallback(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get("https://api.themoviedb.org/3/search/movie").mock(
        return_value=httpx.Response(200, json={"results": [{"original_title": "Originale", "release_date": "bad"}]})
    )
    result = await TMDBClient("k", http_client).search_movie("x")
    assert result.title == "Originale"
    assert result.year is None


# --- MusicBrainz -------------------------------------------------------------


@respx.mock
async def test_mb_timeout(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get("https://musicbrainz.org/ws/2/discid/d1").mock(side_effect=httpx.TimeoutException("t"))
    with pytest.raises(LookupTimeout):
        await MusicBrainzClient("ua/1.0", http_client).lookup_disc_id("d1")


@respx.mock
async def test_mb_transport_error(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get("https://musicbrainz.org/ws/2/discid/d1").mock(side_effect=httpx.ConnectError("x"))
    with pytest.raises(LookupError, match="transport error"):
        await MusicBrainzClient("ua/1.0", http_client).lookup_disc_id("d1")


@respx.mock
async def test_mb_404_5xx_other(http_client) -> None:  # type: ignore[no-untyped-def]
    c = MusicBrainzClient("ua/1.0", http_client)
    respx.get("https://musicbrainz.org/ws/2/discid/d1").mock(return_value=httpx.Response(404))
    with pytest.raises(LookupError, match="not found"):
        await c.lookup_disc_id("d1")
    respx.get("https://musicbrainz.org/ws/2/discid/d1").mock(return_value=httpx.Response(502))
    with pytest.raises(LookupError, match="5xx"):
        await c.lookup_disc_id("d1")
    respx.get("https://musicbrainz.org/ws/2/discid/d1").mock(return_value=httpx.Response(418))
    with pytest.raises(LookupError, match="status=418"):
        await c.lookup_disc_id("d1")


@respx.mock
async def test_mb_no_releases_and_missing_title(http_client) -> None:  # type: ignore[no-untyped-def]
    c = MusicBrainzClient("ua/1.0", http_client)
    respx.get("https://musicbrainz.org/ws/2/discid/d1").mock(return_value=httpx.Response(200, json={"releases": []}))
    with pytest.raises(LookupError, match="no releases"):
        await c.lookup_disc_id("d1")
    respx.get("https://musicbrainz.org/ws/2/discid/d1").mock(
        return_value=httpx.Response(200, json={"releases": [{"date": "1999"}]})
    )
    with pytest.raises(LookupError, match="missing title"):
        await c.lookup_disc_id("d1")


@respx.mock
async def test_mb_rate_limit_sleeps(http_client, monkeypatch: pytest.MonkeyPatch) -> None:  # type: ignore[no-untyped-def]
    """Two back-to-back calls within the min interval exercise both the
    sleep and the no-sleep branch of _rate_limit."""
    monkeypatch.setattr(mb_mod, "_MIN_INTERVAL_SECONDS", 0.02)
    monkeypatch.setattr(mb_mod, "_last_call_at", 0.0)
    respx.get("https://musicbrainz.org/ws/2/discid/d1").mock(
        return_value=httpx.Response(200, json={"releases": [{"title": "Album", "date": "2001-05-01"}]})
    )
    c = MusicBrainzClient("ua/1.0", http_client)
    first = await c.lookup_disc_id("d1")
    second = await c.lookup_disc_id("d1")
    assert first.title == second.title == "Album"
    assert first.year == 2001


# --- ArmServer (1337server) --------------------------------------------------

_ARM = "https://1337server.pythonanywhere.com/api/v1/"


@respx.mock
async def test_arm_server_timeout(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get(_ARM).mock(side_effect=httpx.TimeoutException("t"))
    with pytest.raises(LookupTimeout):
        await ArmServerClient(http_client).lookup_by_crc64("c1")


@respx.mock
async def test_arm_server_transport_error(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get(_ARM).mock(side_effect=httpx.ConnectError("x"))
    with pytest.raises(LookupError, match="transport error"):
        await ArmServerClient(http_client).lookup_by_crc64("c1")


@respx.mock
async def test_arm_server_5xx_and_other(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get(_ARM).mock(return_value=httpx.Response(500))
    with pytest.raises(LookupError, match="5xx"):
        await ArmServerClient(http_client).lookup_by_crc64("c1")
    respx.get(_ARM).mock(return_value=httpx.Response(404))
    with pytest.raises(LookupError, match="status=404"):
        await ArmServerClient(http_client).lookup_by_crc64("c1")


@respx.mock
async def test_arm_server_miss(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get(_ARM).mock(return_value=httpx.Response(200, json={"success": False, "error": "no match"}))
    with pytest.raises(LookupError, match="no match"):
        await ArmServerClient(http_client).lookup_by_crc64("c1")


@respx.mock
async def test_arm_server_results_not_dict(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get(_ARM).mock(return_value=httpx.Response(200, json={"success": True, "results": []}))
    with pytest.raises(LookupError, match="missing results.0"):
        await ArmServerClient(http_client).lookup_by_crc64("c1")


@respx.mock
async def test_arm_server_missing_title(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get(_ARM).mock(return_value=httpx.Response(200, json={"success": True, "results": {"0": {"year": 2008}}}))
    with pytest.raises(LookupError, match="missing title"):
        await ArmServerClient(http_client).lookup_by_crc64("c1")


@respx.mock
async def test_arm_server_hit_movie_int_year_and_poster(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get(_ARM).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "results": {"0": {"title": "Iron Man", "year": 2008, "poster_img": "http://img/x.jpg"}},
            },
        )
    )
    result = await ArmServerClient(http_client).lookup_by_crc64("c1")
    assert result.title == "Iron Man"
    assert result.year == 2008
    assert result.kind == "movie"
    assert result.payload["Poster"] == "http://img/x.jpg"


@respx.mock
async def test_arm_server_hit_tv_string_year(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get(_ARM).mock(
        return_value=httpx.Response(
            200,
            json={
                "success": True,
                "results": {"0": {"title": "The Wire", "year": "2002-06", "video_type": "TV"}},
            },
        )
    )
    result = await ArmServerClient(http_client).lookup_by_crc64("c1")
    assert result.kind == "tv"
    assert result.year == 2002
    assert "Poster" not in result.payload


@respx.mock
async def test_arm_server_hit_unparseable_year(http_client) -> None:  # type: ignore[no-untyped-def]
    respx.get(_ARM).mock(
        return_value=httpx.Response(
            200, json={"success": True, "results": {"0": {"title": "Mystery", "year": "unknown"}}}
        )
    )
    result = await ArmServerClient(http_client).lookup_by_crc64("c1")
    assert result.year is None
