import httpx
import pytest
import respx

from arm_backend.metadata.base import LookupError
from arm_backend.metadata.musicbrainz import MusicBrainzClient
from arm_backend.metadata.omdb import OMDBClient
from arm_backend.metadata.tmdb import TMDBClient


@pytest.fixture
async def http_client():
    async with httpx.AsyncClient(timeout=5.0) as client:
        yield client


@respx.mock
async def test_tmdb_movie_hit(http_client):
    respx.get("https://api.themoviedb.org/3/search/movie").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{"title": "The Matrix", "release_date": "1999-03-31", "id": 603}]},
        )
    )
    client = TMDBClient("v4-bearer-key", http_client)
    result = await client.search_movie("the matrix", 1999)
    assert result.title == "The Matrix"
    assert result.year == 1999
    assert result.kind == "movie"
    assert result.payload["id"] == 603

    request = respx.calls.last.request
    assert request.headers["Authorization"] == "Bearer v4-bearer-key"
    assert "v4-bearer-key" not in str(request.url)


@respx.mock
async def test_tmdb_movie_miss(http_client):
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=httpx.Response(200, json={"results": []}))
    client = TMDBClient("k", http_client)
    with pytest.raises(LookupError):
        await client.search_movie("nope")


@respx.mock
async def test_tmdb_auth_failed(http_client):
    respx.get("https://api.themoviedb.org/3/search/movie").mock(return_value=httpx.Response(401))
    client = TMDBClient("k", http_client)
    with pytest.raises(LookupError):
        await client.search_movie("x")


@respx.mock
async def test_omdb_hit(http_client):
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(
            200,
            json={"Response": "True", "Title": "Some Movie", "Year": "2010", "imdbID": "tt0000001"},
        )
    )
    client = OMDBClient("k", http_client)
    result = await client.lookup_by_title("Some Movie", 2010)
    assert result.title == "Some Movie"
    assert result.year == 2010


@respx.mock
async def test_omdb_miss(http_client):
    respx.get("https://www.omdbapi.com/").mock(
        return_value=httpx.Response(200, json={"Response": "False", "Error": "not found"})
    )
    client = OMDBClient("k", http_client)
    with pytest.raises(LookupError):
        await client.lookup_by_title("nope")


@respx.mock
async def test_musicbrainz_hit(http_client):
    respx.get("https://musicbrainz.org/ws/2/discid/abc123").mock(
        return_value=httpx.Response(
            200,
            json={
                "releases": [{"title": "Album Name", "date": "2005-04-12"}],
            },
        )
    )
    client = MusicBrainzClient("arm-test/0.0 (test@example.com)", http_client)
    result = await client.lookup_disc_id("abc123")
    assert result.title == "Album Name"
    assert result.year == 2005
    assert result.kind == "music"

    request = respx.calls.last.request
    assert request.headers["User-Agent"].startswith("arm-test/")


async def test_musicbrainz_requires_user_agent(http_client):
    with pytest.raises(ValueError):
        MusicBrainzClient("", http_client)
