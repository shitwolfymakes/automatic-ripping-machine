"""TVDB v4 title-search methods (PR 2b). respx-mocked; no network."""

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import httpx  # noqa: E402
import pytest  # noqa: E402
import respx  # noqa: E402

from arm_backend.metadata.base import LookupError, LookupTimeout  # noqa: E402
from arm_backend.metadata.tvdb import TVDBClient, series_to_result  # noqa: E402

_BASE = "https://api4.thetvdb.com/v4"
_LOGIN = {"status": "success", "data": {"token": "tok-1"}}
_ENTRY = {
    "tvdb_id": "73739",
    "name": "Lost",
    "year": "2004",
    "image_url": "https://artworks.thetvdb.com/banners/posters/73739-1.jpg",
    "remote_ids": [{"id": "tt0411008", "type": 2, "sourceName": "IMDB"}],
}


@pytest.fixture
async def http_client():
    async with httpx.AsyncClient(timeout=5.0) as client:
        yield client


def test_series_to_result_maps_ids_year_and_poster():
    result = series_to_result(_ENTRY)
    assert result is not None
    assert (result.title, result.year, result.kind) == ("Lost", 2004, "tv")
    assert result.payload["tvdb_id"] == "73739"
    assert result.payload["imdb_id"] == "tt0411008"
    assert result.payload["poster_url"].startswith("https://artworks.thetvdb.com/")
    assert series_to_result({"tvdb_id": "1"}) is None  # no name
    # The remoteid shape nests the series under "series" with "id" and "image".
    nested = series_to_result({"id": 73739, "name": "Lost", "year": "2004", "image": "https://x/y.jpg"})
    assert (
        nested is not None
        and nested.payload["tvdb_id"] == "73739"
        and nested.payload["poster_url"] == "https://x/y.jpg"
    )


@respx.mock
async def test_search_series_logs_in_then_searches(http_client):
    login = respx.post(f"{_BASE}/login").mock(return_value=httpx.Response(200, json=_LOGIN))
    search = respx.get(f"{_BASE}/search").mock(return_value=httpx.Response(200, json={"data": [_ENTRY]}))
    client = TVDBClient("key", http_client)
    result = await client.search_series("lost")
    assert result.title == "Lost"
    assert login.call_count == 1
    assert search.calls.last.request.headers["Authorization"] == "Bearer tok-1"
    assert search.calls.last.request.url.params["type"] == "series"
    # A second call on the same client reuses the token.
    await client.search_series("lost again")
    assert login.call_count == 1


@respx.mock
async def test_search_series_relogs_in_once_on_401(http_client):
    respx.post(f"{_BASE}/login").mock(
        side_effect=[httpx.Response(200, json=_LOGIN), httpx.Response(200, json={"data": {"token": "tok-2"}})]
    )
    search = respx.get(f"{_BASE}/search").mock(
        side_effect=[httpx.Response(401), httpx.Response(200, json={"data": [_ENTRY]})]
    )
    result = await TVDBClient("key", http_client).search_series("lost")
    assert result.title == "Lost"
    assert search.calls[1].request.headers["Authorization"] == "Bearer tok-2"


@respx.mock
async def test_search_series_second_401_is_a_lookup_error(http_client):
    respx.post(f"{_BASE}/login").mock(return_value=httpx.Response(200, json=_LOGIN))
    respx.get(f"{_BASE}/search").mock(return_value=httpx.Response(401))
    with pytest.raises(LookupError, match="after re-login"):
        await TVDBClient("key", http_client).search_series("lost")


@respx.mock
async def test_search_series_empty_data_is_a_miss(http_client):
    respx.post(f"{_BASE}/login").mock(return_value=httpx.Response(200, json=_LOGIN))
    respx.get(f"{_BASE}/search").mock(return_value=httpx.Response(200, json={"data": []}))
    with pytest.raises(LookupError):
        await TVDBClient("key", http_client).search_series("nothing")


@respx.mock
async def test_search_candidates_and_limit(http_client):
    respx.post(f"{_BASE}/login").mock(return_value=httpx.Response(200, json=_LOGIN))
    respx.get(f"{_BASE}/search").mock(
        return_value=httpx.Response(200, json={"data": [_ENTRY, {**_ENTRY, "name": "Lost 2"}]})
    )
    results = await TVDBClient("key", http_client).search_candidates("lost", limit=1)
    assert [r.title for r in results] == ["Lost"]


@respx.mock
async def test_lookup_by_imdb_id_uses_remoteid(http_client):
    respx.post(f"{_BASE}/login").mock(return_value=httpx.Response(200, json=_LOGIN))
    respx.get(f"{_BASE}/search/remoteid/tt0411008").mock(
        return_value=httpx.Response(200, json={"data": [{"series": {"id": 73739, "name": "Lost", "year": "2004"}}]})
    )
    result = await TVDBClient("key", http_client).lookup_by_imdb_id("tt0411008")
    assert result.payload["tvdb_id"] == "73739" and result.payload["imdb_id"] == "tt0411008"


@respx.mock
async def test_login_failure_and_timeout(http_client):
    respx.post(f"{_BASE}/login").mock(return_value=httpx.Response(401))
    with pytest.raises(LookupError):
        await TVDBClient("bad", http_client).search_series("lost")
    respx.post(f"{_BASE}/login").mock(side_effect=httpx.ReadTimeout("slow"))
    with pytest.raises(LookupTimeout):
        await TVDBClient("key", http_client).search_series("lost")


@respx.mock
async def test_lookup_by_imdb_id_empty_data_is_a_miss(http_client):
    respx.post(f"{_BASE}/login").mock(return_value=httpx.Response(200, json=_LOGIN))
    respx.get(f"{_BASE}/search/remoteid/tt1").mock(return_value=httpx.Response(200, json={"data": []}))
    with pytest.raises(LookupError):
        await TVDBClient("key", http_client).lookup_by_imdb_id("tt1")


@respx.mock
async def test_lookup_by_imdb_id_nameless_series_is_a_miss(http_client):
    respx.post(f"{_BASE}/login").mock(return_value=httpx.Response(200, json=_LOGIN))
    respx.get(f"{_BASE}/search/remoteid/tt1").mock(return_value=httpx.Response(200, json={"data": [{"series": {}}]}))
    with pytest.raises(LookupError):
        await TVDBClient("key", http_client).lookup_by_imdb_id("tt1")


@respx.mock
async def test_malformed_login_body_is_a_lookup_error(http_client):
    respx.post(f"{_BASE}/login").mock(return_value=httpx.Response(200, json={"data": {}}))
    with pytest.raises(LookupError):
        await TVDBClient("key", http_client).search_series("lost")
    with pytest.raises(LookupError):
        await TVDBClient("key", http_client).validate_key()


@respx.mock
async def test_series_details_reads_extended_with_translations(http_client):
    respx.post(f"{_BASE}/login").mock(return_value=httpx.Response(200, json=_LOGIN))
    route = respx.get(f"{_BASE}/series/77170/extended").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "id": 77170,
                    "name": "Kolchak: The Night Stalker",
                    "year": "1974",
                    "image": "https://artworks.thetvdb.com/banners/posters/77170-1.jpg",
                    "remoteIds": [
                        "junk",
                        {"id": "5", "sourceName": "TheMovieDB.com"},
                        {"id": "tt0071003", "sourceName": "IMDB"},
                    ],
                    "characters": [{"personName": "Darren McGavin", "peopleType": "Actor", "sort": 0}],
                }
            },
        )
    )
    result = await TVDBClient("k", http_client).series_details("77170")
    assert route.calls.last.request.url.params["meta"] == "translations"
    assert "short" not in route.calls.last.request.url.params
    assert (result.title, result.year) == ("Kolchak: The Night Stalker", 1974)
    assert result.payload["tvdb_id"] == "77170" and result.payload["imdb_id"] == "tt0071003"
    assert result.payload["poster_url"].startswith("https://artworks.thetvdb.com/")


@respx.mock
async def test_series_details_without_imdb_remote_id_skips_it(http_client):
    respx.post(f"{_BASE}/login").mock(return_value=httpx.Response(200, json=_LOGIN))
    respx.get(f"{_BASE}/series/2/extended").mock(
        return_value=httpx.Response(
            200, json={"data": {"id": 2, "name": "X", "remoteIds": [{"id": "1", "sourceName": "Other"}]}}
        )
    )
    result = await TVDBClient("k", http_client).series_details("2")
    assert result.payload.get("imdb_id") in (None, "")


@respx.mock
async def test_series_details_malformed_is_a_lookup_error(http_client):
    respx.post(f"{_BASE}/login").mock(return_value=httpx.Response(200, json=_LOGIN))
    respx.get(f"{_BASE}/series/1/extended").mock(return_value=httpx.Response(200, json={"data": []}))
    with pytest.raises(LookupError):
        await TVDBClient("k", http_client).series_details("1")


@respx.mock
async def test_series_details_missing_name_is_a_lookup_error(http_client):
    respx.post(f"{_BASE}/login").mock(return_value=httpx.Response(200, json=_LOGIN))
    respx.get(f"{_BASE}/series/1/extended").mock(return_value=httpx.Response(200, json={"data": {"id": 1}}))
    with pytest.raises(LookupError):
        await TVDBClient("k", http_client).series_details("1")
