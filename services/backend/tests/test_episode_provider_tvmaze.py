"""TvmazeEpisodes provider: resolve_show_id, seasons, season (design spec 6.2)."""

import httpx
import pytest
import respx
from arm_common import Config
from arm_common.schemas import ExternalIds

from arm_backend.identity.episodes.providers.base import EpisodeListProvider
from arm_backend.identity.episodes.providers.tvmaze import TvmazeEpisodes
from arm_backend.identity.http import SourceError, SourceHttp, SourceMiss, SourcePolicy

BASE = "https://api.tvmaze.com"


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
    return TvmazeEpisodes(source_http)


# ---------------------------------------------------------------------------
# configured / identity
# ---------------------------------------------------------------------------


def test_configured_is_always_none(provider):
    assert provider.configured(Config(id=1)) is None


def test_provider_identity(provider):
    assert provider.source_id == "episodes_tvmaze"
    assert provider.id_field == "tvmaze"
    assert provider.http is not None


def test_provider_satisfies_protocol_shape(provider):
    """TvmazeEpisodes structurally implements EpisodeListProvider: same
    attribute/method names the Protocol declares."""
    assert set(EpisodeListProvider.__annotations__) == {"source_id", "id_field", "http"}
    for name in ("configured", "resolve_show_id", "seasons", "season"):
        assert hasattr(EpisodeListProvider, name)
        assert hasattr(provider, name)


# ---------------------------------------------------------------------------
# resolve_show_id
# ---------------------------------------------------------------------------


@respx.mock
async def test_resolve_show_id_via_tvmaze_ids_makes_no_request(provider):
    ids = ExternalIds(tvmaze="169")
    result = await provider.resolve_show_id(ids)
    assert result == "169"
    assert len(respx.calls) == 0


@respx.mock
async def test_resolve_show_id_via_imdb_hit(provider):
    route = respx.get(f"{BASE}/lookup/shows").mock(return_value=httpx.Response(200, json={"id": 169}))
    ids = ExternalIds(imdb="tt0944947")
    result = await provider.resolve_show_id(ids)
    assert result == "169"
    assert route.calls.last.request.url.params["imdb"] == "tt0944947"


@respx.mock
async def test_resolve_show_id_via_tvdb(provider):
    route = respx.get(f"{BASE}/lookup/shows").mock(return_value=httpx.Response(200, json={"id": 169}))
    ids = ExternalIds(tvdb="121361")
    result = await provider.resolve_show_id(ids)
    assert result == "169"
    assert route.calls.last.request.url.params["thetvdb"] == "121361"


@respx.mock
async def test_resolve_show_id_via_imdb_miss_returns_none(provider):
    respx.get(f"{BASE}/lookup/shows").mock(return_value=httpx.Response(404))
    ids = ExternalIds(imdb="tt0000000")
    assert await provider.resolve_show_id(ids) is None


@respx.mock
async def test_resolve_show_id_with_no_ids_returns_none(provider):
    assert await provider.resolve_show_id(ExternalIds()) is None
    assert len(respx.calls) == 0


@respx.mock
async def test_lookup_result_without_id_raises_source_error(provider):
    """A lookup hit missing the "id" key is malformed, not a miss — KeyError
    must be wrapped as SourceError, never leak past the provider."""
    respx.get(f"{BASE}/lookup/shows").mock(return_value=httpx.Response(200, json={"name": "No Id"}))
    with pytest.raises(SourceError):
        await provider.resolve_show_id(ExternalIds(imdb="tt0000009"))


@respx.mock
async def test_lookup_requests_follow_redirects(provider, monkeypatch):
    """The lookup call must ask `SourceHttp` to follow redirects (TVmaze's
    `/lookup/shows` may redirect to the show document) — assert the flag
    actually reaches `get_json`, not just that the request happened."""
    respx.get(f"{BASE}/lookup/shows").mock(return_value=httpx.Response(200, json={"id": 169}))
    captured: dict[str, object] = {}
    original = SourceHttp.get_json

    async def _spy(self, url, **kwargs):
        captured.update(kwargs)
        return await original(self, url, **kwargs)

    monkeypatch.setattr(SourceHttp, "get_json", _spy)
    await provider.resolve_show_id(ExternalIds(imdb="tt0944947"))
    assert captured["follow_redirects"] is True


# ---------------------------------------------------------------------------
# seasons / season: single request per show
# ---------------------------------------------------------------------------

EPISODES_BODY = [
    {"season": 1, "number": 1, "name": "Winter Is Coming", "runtime": 62},
    {"season": 1, "number": 2, "name": "The Kingsroad", "runtime": 56},
    {"season": 2, "number": 1, "name": "The North Remembers", "runtime": 53},
    {"season": 0, "number": None, "name": "Special", "runtime": 30},
]


@respx.mock
async def test_episodes_fetched_once_for_seasons_and_season_calls(provider):
    route = respx.get(f"{BASE}/shows/169/episodes").mock(return_value=httpx.Response(200, json=EPISODES_BODY))
    assert await provider.seasons("169") == [1, 2]
    await provider.season("169", 1)
    await provider.season("169", 2)
    assert route.call_count == 1
    assert route.calls.last.request.url.params["specials"] == "1"


@respx.mock
async def test_seasons_sorted_and_specials_excluded(provider):
    respx.get(f"{BASE}/shows/169/episodes").mock(return_value=httpx.Response(200, json=EPISODES_BODY))
    assert await provider.seasons("169") == [1, 2]


@respx.mock
async def test_season_maps_runtime_minutes_to_seconds_and_sorts(provider):
    respx.get(f"{BASE}/shows/169/episodes").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"season": 1, "number": 2, "name": "The Kingsroad", "runtime": 56},
                {"season": 1, "number": 1, "name": "Winter Is Coming", "runtime": 62},
            ],
        )
    )
    episodes = await provider.season("169", 1)
    assert [e.number for e in episodes] == [1, 2]
    assert episodes[0].runtime_s == 62 * 60
    assert episodes[0].name == "Winter Is Coming"
    assert episodes[0].season == 1


@respx.mock
async def test_season_excludes_specials_with_null_number(provider):
    """Season 0's only entry has a null `number` (a special) — no usable
    entries for season 0 means SourceMiss, not an empty/degenerate list."""
    respx.get(f"{BASE}/shows/169/episodes").mock(return_value=httpx.Response(200, json=EPISODES_BODY))
    with pytest.raises(SourceMiss):
        await provider.season("169", 0)


@respx.mock
async def test_season_null_runtime_maps_to_none(provider):
    respx.get(f"{BASE}/shows/169/episodes").mock(
        return_value=httpx.Response(200, json=[{"season": 1, "number": 1, "name": "X", "runtime": None}])
    )
    episodes = await provider.season("169", 1)
    assert episodes[0].runtime_s is None


@respx.mock
async def test_season_string_runtime_maps_to_none(provider):
    """A malformed (string) runtime must not crash the mapping — it degrades
    to None rather than raising or silently becoming a bogus runtime_s."""
    respx.get(f"{BASE}/shows/169/episodes").mock(
        return_value=httpx.Response(200, json=[{"season": 1, "number": 1, "name": "X", "runtime": "sixty"}])
    )
    episodes = await provider.season("169", 1)
    assert episodes[0].runtime_s is None


@respx.mock
async def test_season_zero_runtime_maps_to_none(provider):
    respx.get(f"{BASE}/shows/169/episodes").mock(
        return_value=httpx.Response(200, json=[{"season": 1, "number": 1, "name": "X", "runtime": 0}])
    )
    episodes = await provider.season("169", 1)
    assert episodes[0].runtime_s is None


@respx.mock
async def test_season_missing_name_maps_to_none(provider):
    respx.get(f"{BASE}/shows/169/episodes").mock(
        return_value=httpx.Response(200, json=[{"season": 1, "number": 1, "runtime": 30}])
    )
    episodes = await provider.season("169", 1)
    assert episodes[0].name is None


@respx.mock
async def test_season_entry_without_number_is_skipped(provider):
    respx.get(f"{BASE}/shows/169/episodes").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"season": 1, "number": None, "name": "Special-ish", "runtime": 30},
                {"season": 1, "number": 1, "name": "One", "runtime": 30},
            ],
        )
    )
    episodes = await provider.season("169", 1)
    assert [e.number for e in episodes] == [1]


@respx.mock
async def test_season_entry_with_bool_number_is_skipped(provider):
    """`bool` is an `int` subclass in Python but is never a valid episode
    number — must be treated as missing, not as season/episode 1/0."""
    respx.get(f"{BASE}/shows/169/episodes").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"season": 1, "number": True, "name": "Bool Number", "runtime": 30},
                {"season": 1, "number": 1, "name": "One", "runtime": 30},
            ],
        )
    )
    episodes = await provider.season("169", 1)
    assert [e.number for e in episodes] == [1]


@respx.mock
async def test_seasons_entry_with_bool_season_is_skipped(provider):
    respx.get(f"{BASE}/shows/169/episodes").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"season": True, "number": 1, "name": "Bool Season", "runtime": 30},
                {"season": 1, "number": 1, "name": "One", "runtime": 30},
            ],
        )
    )
    assert await provider.seasons("169") == [1]


@respx.mock
async def test_unknown_season_raises_source_miss(provider):
    respx.get(f"{BASE}/shows/169/episodes").mock(return_value=httpx.Response(200, json=EPISODES_BODY))
    with pytest.raises(SourceMiss):
        await provider.season("169", 99)


@respx.mock
async def test_episodes_non_list_body_raises_source_error(provider):
    respx.get(f"{BASE}/shows/169/episodes").mock(return_value=httpx.Response(200, json={"episodes": "nope"}))
    with pytest.raises(SourceError):
        await provider.seasons("169")


@respx.mock
async def test_season_non_list_body_raises_source_error(provider):
    respx.get(f"{BASE}/shows/169/episodes").mock(return_value=httpx.Response(200, json={"episodes": "nope"}))
    with pytest.raises(SourceError):
        await provider.season("169", 1)


@respx.mock
async def test_episodes_503_raises_source_error(provider):
    respx.get(f"{BASE}/shows/169/episodes").mock(return_value=httpx.Response(503))
    with pytest.raises(SourceError):
        await provider.seasons("169")


@respx.mock
async def test_seasons_empty_episodes_raises_source_error(provider):
    """An existing show whose episodes endpoint returns `200 []` is a
    degenerate/transient response (C7), not a definitive miss — must not
    read as "this show has no seasons"."""
    respx.get(f"{BASE}/shows/169/episodes").mock(return_value=httpx.Response(200, json=[]))
    with pytest.raises(SourceError):
        await provider.seasons("169")


@respx.mock
async def test_season_empty_episodes_raises_source_error(provider):
    respx.get(f"{BASE}/shows/169/episodes").mock(return_value=httpx.Response(200, json=[]))
    with pytest.raises(SourceError):
        await provider.season("169", 1)


# ---------------------------------------------------------------------------
# M1: bounded runtimes and names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("raw", ["Infinity", "-Infinity", "NaN", "1e308", "1440", "99999"])
@respx.mock
async def test_season_out_of_range_runtime_maps_to_none(provider, raw):
    body = b'[{"season": 1, "number": 1, "name": "X", "runtime": ' + raw.encode() + b"}]"
    respx.get(f"{BASE}/shows/169/episodes").mock(
        return_value=httpx.Response(200, content=body, headers={"content-type": "application/json"})
    )
    episodes = await provider.season("169", 1)
    assert episodes[0].runtime_s is None


@pytest.mark.parametrize("name", [123, ["a"], {"x": 1}, True])
@respx.mock
async def test_season_non_str_name_maps_to_none(provider, name):
    respx.get(f"{BASE}/shows/169/episodes").mock(
        return_value=httpx.Response(200, json=[{"season": 1, "number": 1, "name": name, "runtime": 30}])
    )
    episodes = await provider.season("169", 1)
    assert episodes[0].name is None
