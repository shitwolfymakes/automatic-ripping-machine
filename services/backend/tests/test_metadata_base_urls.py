"""Tier-3: metadata base URLs are env-overridable, defaulting to current literals."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "x")

import httpx  # noqa: E402
import pytest  # noqa: E402
import respx  # noqa: E402

from arm_backend.config import Settings  # noqa: E402
from arm_backend.metadata.arm_server import ArmServerClient  # noqa: E402
from arm_backend.metadata.musicbrainz import MusicBrainzClient  # noqa: E402
from arm_backend.metadata.omdb import OMDBClient  # noqa: E402
from arm_backend.metadata.tmdb import TMDBClient  # noqa: E402
from arm_backend.metadata.tvdb import TVDBClient  # noqa: E402


@pytest.fixture
async def http_client():  # type: ignore[no-untyped-def]
    async with httpx.AsyncClient(timeout=5.0) as client:
        yield client


def test_base_url_defaults_match_current_literals():
    s = Settings()  # type: ignore[call-arg]
    assert s.ARM_TMDB_BASE_URL == "https://api.themoviedb.org/3"
    assert s.ARM_OMDB_BASE_URL == "https://www.omdbapi.com/"
    assert s.ARM_TVDB_BASE_URL == "https://api4.thetvdb.com/v4"
    assert s.ARM_MUSICBRAINZ_BASE_URL == "https://musicbrainz.org/ws/2"
    assert s.ARM_ARMSERVER_BASE_URL == "https://1337server.pythonanywhere.com/api/v1/"


def test_base_url_overridable_via_env(monkeypatch):
    monkeypatch.setenv("ARM_TMDB_BASE_URL", "http://tmdb-mirror.lan/3")
    assert Settings().ARM_TMDB_BASE_URL == "http://tmdb-mirror.lan/3"  # type: ignore[call-arg]


# --- Clients read the (overridable) base URL from settings -------------------


@respx.mock
async def test_tmdb_uses_overridden_base_url(monkeypatch, http_client) -> None:
    monkeypatch.setattr("arm_backend.metadata.tmdb._base_url", lambda: "http://tmdb.lan/3")
    route = respx.get("http://tmdb.lan/3/search/movie").mock(
        return_value=httpx.Response(200, json={"results": [{"title": "Movie", "release_date": "2010-01-01"}]})
    )
    await TMDBClient("k", http_client).search_movie("x")
    assert route.called


@respx.mock
async def test_omdb_uses_overridden_base_url(monkeypatch, http_client) -> None:
    monkeypatch.setattr("arm_backend.metadata.omdb._base_url", lambda: "http://omdb.lan/")
    route = respx.get("http://omdb.lan/").mock(
        return_value=httpx.Response(200, json={"Response": "True", "Title": "Movie", "Year": "2010"})
    )
    await OMDBClient("k", http_client).lookup_by_title("x")
    assert route.called


@respx.mock
async def test_tvdb_uses_overridden_base_url(monkeypatch, http_client) -> None:
    monkeypatch.setattr("arm_backend.metadata.tvdb._base_url", lambda: "http://tvdb.lan/v4")
    route = respx.post("http://tvdb.lan/v4/login").mock(return_value=httpx.Response(200, json={}))
    await TVDBClient("k", http_client).validate_key()
    assert route.called


@respx.mock
async def test_musicbrainz_uses_overridden_base_url(monkeypatch, http_client) -> None:
    monkeypatch.setattr("arm_backend.metadata.musicbrainz._base_url", lambda: "http://mb.lan/ws/2")
    route = respx.get("http://mb.lan/ws/2/discid/d1").mock(
        return_value=httpx.Response(200, json={"releases": [{"title": "Album", "date": "2001-05-01"}]})
    )
    await MusicBrainzClient("ua/1.0", http_client).lookup_disc_id("d1")
    assert route.called


@respx.mock
async def test_arm_server_uses_overridden_base_url(monkeypatch, http_client) -> None:
    monkeypatch.setattr("arm_backend.metadata.arm_server._base_url", lambda: "http://arm.lan/api/v1/")
    route = respx.get("http://arm.lan/api/v1/").mock(
        return_value=httpx.Response(200, json={"success": True, "results": {"0": {"title": "Sintel", "year": 2010}}})
    )
    await ArmServerClient(http_client).lookup_by_crc64("c1")
    assert route.called
