"""TmdbEpisodes provider: resolve_show_id, seasons, season (design spec 6.2)."""

import httpx
import pytest
import respx
from arm_common import Config
from arm_common.schemas import ExternalIds

from arm_backend.identity.episodes.providers.base import EpisodeListProvider
from arm_backend.identity.episodes.providers.tmdb import TmdbEpisodes
from arm_backend.identity.http import SourceError, SourceHttp, SourceMiss, SourcePolicy

BASE = "https://api.themoviedb.org/3"


async def _noop_sleep(_seconds: float) -> None:
    return None


@pytest.fixture
async def http_client():
    async with httpx.AsyncClient(timeout=5.0) as client:
        yield client


@pytest.fixture
def source_http(http_client):
    return SourceHttp(http_client, SourcePolicy(min_interval_s=0), sleep=_noop_sleep)


@pytest.fixture
def provider(source_http):
    return TmdbEpisodes(source_http, "the-key")


# ---------------------------------------------------------------------------
# configured
# ---------------------------------------------------------------------------


def test_configured_without_key_returns_reason(source_http):
    p = TmdbEpisodes(source_http, None)
    assert p.configured(Config(id=1)) == "no TMDb key"


def test_configured_with_empty_string_key_returns_reason(source_http):
    p = TmdbEpisodes(source_http, "")
    assert p.configured(Config(id=1)) == "no TMDb key"


def test_configured_with_key_is_none(provider):
    assert provider.configured(Config(id=1)) is None


def test_provider_identity(provider):
    assert provider.source_id == "episodes_tmdb"
    assert provider.id_field == "tmdb"
    assert provider.http is not None


def test_provider_satisfies_protocol_shape(provider):
    """TmdbEpisodes structurally implements EpisodeListProvider: same
    attribute/method names the Protocol declares."""
    assert set(EpisodeListProvider.__annotations__) == {"source_id", "id_field", "http"}
    for name in ("configured", "resolve_show_id", "seasons", "season"):
        assert hasattr(EpisodeListProvider, name)
        assert hasattr(provider, name)


# ---------------------------------------------------------------------------
# resolve_show_id
# ---------------------------------------------------------------------------


@respx.mock
async def test_resolve_show_id_via_tmdb_ids_makes_no_request(provider):
    ids = ExternalIds(tmdb="1399")
    result = await provider.resolve_show_id(ids)
    assert result == "1399"
    assert len(respx.calls) == 0


@respx.mock
async def test_resolve_show_id_via_imdb_hit(provider):
    route = respx.get(f"{BASE}/find/tt0944947").mock(
        return_value=httpx.Response(200, json={"tv_results": [{"id": 1399}], "movie_results": []})
    )
    ids = ExternalIds(imdb="tt0944947")
    result = await provider.resolve_show_id(ids)
    assert result == "1399"
    assert route.calls.last.request.url.params["external_source"] == "imdb_id"


@respx.mock
async def test_resolve_show_id_via_imdb_miss_returns_none(provider):
    respx.get(f"{BASE}/find/tt0000000").mock(
        return_value=httpx.Response(200, json={"tv_results": [], "movie_results": []})
    )
    ids = ExternalIds(imdb="tt0000000")
    assert await provider.resolve_show_id(ids) is None


@respx.mock
async def test_resolve_show_id_via_tvdb(provider):
    route = respx.get(f"{BASE}/find/121361").mock(
        return_value=httpx.Response(200, json={"tv_results": [{"id": 1399}], "movie_results": []})
    )
    ids = ExternalIds(tvdb="121361")
    result = await provider.resolve_show_id(ids)
    assert result == "1399"
    assert route.calls.last.request.url.params["external_source"] == "tvdb_id"


@respx.mock
async def test_resolve_show_id_with_no_ids_returns_none(provider):
    assert await provider.resolve_show_id(ExternalIds()) is None
    assert len(respx.calls) == 0


# ---------------------------------------------------------------------------
# seasons
# ---------------------------------------------------------------------------


@respx.mock
async def test_seasons_excludes_season_zero_and_sorts(provider):
    respx.get(f"{BASE}/tv/1399").mock(
        return_value=httpx.Response(
            200,
            json={
                "seasons": [
                    {"season_number": 0},
                    {"season_number": 2},
                    {"season_number": 1},
                ]
            },
        )
    )
    assert await provider.seasons("1399") == [1, 2]


# ---------------------------------------------------------------------------
# season
# ---------------------------------------------------------------------------


@respx.mock
async def test_season_maps_runtime_minutes_to_seconds(provider):
    respx.get(f"{BASE}/tv/1399/season/1").mock(
        return_value=httpx.Response(
            200,
            json={
                "episodes": [
                    {"episode_number": 1, "name": "Winter Is Coming", "runtime": 62},
                ]
            },
        )
    )
    episodes = await provider.season("1399", 1)
    assert episodes[0].runtime_s == 62 * 60
    assert episodes[0].name == "Winter Is Coming"
    assert episodes[0].season == 1
    assert episodes[0].special is False


@respx.mock
async def test_season_null_runtime_maps_to_none(provider):
    respx.get(f"{BASE}/tv/1399/season/1").mock(
        return_value=httpx.Response(
            200,
            json={"episodes": [{"episode_number": 1, "name": "X", "runtime": None}]},
        )
    )
    episodes = await provider.season("1399", 1)
    assert episodes[0].runtime_s is None


@respx.mock
async def test_season_missing_name_maps_to_none(provider):
    respx.get(f"{BASE}/tv/1399/season/1").mock(
        return_value=httpx.Response(200, json={"episodes": [{"episode_number": 1, "runtime": 30}]})
    )
    episodes = await provider.season("1399", 1)
    assert episodes[0].name is None


@respx.mock
async def test_season_sorted_by_episode_number(provider):
    respx.get(f"{BASE}/tv/1399/season/1").mock(
        return_value=httpx.Response(
            200,
            json={
                "episodes": [
                    {"episode_number": 2, "name": "Two", "runtime": 30},
                    {"episode_number": 1, "name": "One", "runtime": 30},
                ]
            },
        )
    )
    episodes = await provider.season("1399", 1)
    assert [e.number for e in episodes] == [1, 2]


@respx.mock
async def test_season_zero_marks_special(provider):
    respx.get(f"{BASE}/tv/1399/season/0").mock(
        return_value=httpx.Response(200, json={"episodes": [{"episode_number": 1, "name": "Special", "runtime": 20}]})
    )
    episodes = await provider.season("1399", 0)
    assert episodes[0].special is True


@respx.mock
async def test_season_404_raises_source_miss(provider):
    respx.get(f"{BASE}/tv/1399/season/99").mock(return_value=httpx.Response(404))
    with pytest.raises(SourceMiss):
        await provider.season("1399", 99)


@respx.mock
async def test_season_empty_episodes_raises_source_error(provider):
    respx.get(f"{BASE}/tv/1399/season/1").mock(return_value=httpx.Response(200, json={"episodes": []}))
    with pytest.raises(SourceError):
        await provider.season("1399", 1)


# ---------------------------------------------------------------------------
# Auth: bearer header present, key never in the URL
# ---------------------------------------------------------------------------


@respx.mock
async def test_bearer_header_present_key_absent_from_url(provider):
    route = respx.get(f"{BASE}/tv/1399").mock(return_value=httpx.Response(200, json={"seasons": []}))
    await provider.seasons("1399")
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer the-key"
    assert "the-key" not in str(request.url)
