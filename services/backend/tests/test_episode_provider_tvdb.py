"""TvdbEpisodes provider: login/token caching, resolve_show_id, seasons, season
(design spec 6.2)."""

import httpx
import pytest
import respx
from arm_common import Config
from arm_common.schemas import ExternalIds

from arm_backend.identity.episodes.providers.base import EpisodeListProvider
from arm_backend.identity.episodes.providers.tvdb import TvdbEpisodes
from arm_backend.identity.http import SourceError, SourceHttp, SourceMiss, SourcePolicy

BASE = "https://api4.thetvdb.com/v4"


async def _noop_sleep(_seconds: float) -> None:
    return None


class Clock:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def now(self) -> float:
        return self.t


@pytest.fixture
async def http_client():
    async with httpx.AsyncClient(timeout=5.0) as client:
        yield client


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def source_http(http_client, clock):
    return SourceHttp(http_client, SourcePolicy(min_interval_s=0), clock=clock.now, sleep=_noop_sleep)


@pytest.fixture
def provider(source_http, clock):
    return TvdbEpisodes(source_http, "the-key", clock=clock.now)


def _login_route(token: str = "tok-1"):
    return respx.post(f"{BASE}/login").mock(return_value=httpx.Response(200, json={"data": {"token": token}}))


# ---------------------------------------------------------------------------
# configured / identity
# ---------------------------------------------------------------------------


def test_configured_without_key_returns_reason(source_http):
    p = TvdbEpisodes(source_http, None)
    assert p.configured(Config(id=1)) == "no TVDB key"


def test_configured_with_empty_string_key_returns_reason(source_http):
    p = TvdbEpisodes(source_http, "")
    assert p.configured(Config(id=1)) == "no TVDB key"


def test_configured_with_key_is_none(provider):
    assert provider.configured(Config(id=1)) is None


def test_provider_identity(provider):
    assert provider.source_id == "episodes_tvdb"
    assert provider.id_field == "tvdb"
    assert provider.http is not None


def test_provider_satisfies_protocol_shape(provider):
    """TvdbEpisodes structurally implements EpisodeListProvider: same
    attribute/method names the Protocol declares."""
    assert set(EpisodeListProvider.__annotations__) == {"source_id", "id_field", "http"}
    for name in ("configured", "resolve_show_id", "seasons", "season"):
        assert hasattr(EpisodeListProvider, name)
        assert hasattr(provider, name)


# ---------------------------------------------------------------------------
# login / token caching / 401 re-login
# ---------------------------------------------------------------------------


@respx.mock
async def test_login_once_for_several_calls(provider):
    login = _login_route()
    respx.get(f"{BASE}/series/1/extended").mock(return_value=httpx.Response(200, json={"data": {"seasons": []}}))
    await provider.seasons("1")
    await provider.seasons("1")
    await provider.seasons("1")
    assert login.call_count == 1


@respx.mock
async def test_token_refreshed_after_23_hours(provider, clock):
    login = _login_route()
    respx.get(f"{BASE}/series/1/extended").mock(return_value=httpx.Response(200, json={"data": {"seasons": []}}))
    await provider.seasons("1")
    clock.t += 23 * 3600
    await provider.seasons("1")
    assert login.call_count == 2


@respx.mock
async def test_token_not_refreshed_before_23_hours(provider, clock):
    login = _login_route()
    respx.get(f"{BASE}/series/1/extended").mock(return_value=httpx.Response(200, json={"data": {"seasons": []}}))
    await provider.seasons("1")
    clock.t += 23 * 3600 - 1
    await provider.seasons("1")
    assert login.call_count == 1


@respx.mock
async def test_401_triggers_relogin_and_retry_succeeds(provider):
    login = _login_route()
    route = respx.get(f"{BASE}/series/1/extended").mock(
        side_effect=[httpx.Response(401), httpx.Response(200, json={"data": {"seasons": []}})]
    )
    result = await provider.seasons("1")
    assert result == []
    assert login.call_count == 2
    assert route.call_count == 2


@respx.mock
async def test_double_401_raises_source_error(provider):
    login = _login_route()
    route = respx.get(f"{BASE}/series/1/extended").mock(return_value=httpx.Response(401))
    with pytest.raises(SourceError, match="auth"):
        await provider.seasons("1")
    assert login.call_count == 2
    assert route.call_count == 2


@respx.mock
async def test_login_malformed_response_raises_source_error(provider):
    respx.post(f"{BASE}/login").mock(return_value=httpx.Response(200, json={"data": {"nope": "x"}}))
    with pytest.raises(SourceError):
        await provider.seasons("1")


@respx.mock
async def test_login_non_string_token_raises_source_error(provider):
    respx.post(f"{BASE}/login").mock(return_value=httpx.Response(200, json={"data": {"token": ""}}))
    with pytest.raises(SourceError):
        await provider.seasons("1")


@respx.mock
async def test_first_call_non_401_error_propagates_without_relogin(provider):
    """A non-auth error (e.g. a 5xx) on the first attempt must surface as-is
    — no re-login, no retry."""
    login = _login_route()
    route = respx.get(f"{BASE}/series/1/extended").mock(return_value=httpx.Response(503))
    with pytest.raises(SourceError, match="status=503"):
        await provider.seasons("1")
    assert login.call_count == 1
    assert route.call_count == 1


@respx.mock
async def test_retry_after_relogin_non_401_error_propagates(provider):
    """401, then re-login succeeds, but the retried call fails with a
    different error (not another 401) — that error must surface as-is."""
    login = _login_route()
    route = respx.get(f"{BASE}/series/1/extended").mock(side_effect=[httpx.Response(401), httpx.Response(503)])
    with pytest.raises(SourceError, match="status=503"):
        await provider.seasons("1")
    assert login.call_count == 2
    assert route.call_count == 2


@respx.mock
async def test_collect_pages_404_on_first_page_is_treated_as_empty(provider):
    """A season/dvd 404 (no dvd-order episodes for this season) must fall
    back to /default rather than propagate as a miss straight away."""
    _login_route()
    respx.get(f"{BASE}/series/1/episodes/dvd").mock(return_value=httpx.Response(404))
    respx.get(f"{BASE}/series/1/episodes/default").mock(
        return_value=httpx.Response(200, json={"data": {"episodes": [{"number": 1, "name": "One", "runtime": 30}]}})
    )
    episodes = await provider.season("1", 1)
    assert episodes[0].name == "One"


@respx.mock
async def test_login_failure_propagates_without_looping(provider):
    """A bad api key: the login call itself 401s. Must surface immediately,
    not retry login forever."""
    respx.post(f"{BASE}/login").mock(return_value=httpx.Response(401))
    with pytest.raises(SourceError, match="auth"):
        await provider.seasons("1")


@respx.mock
async def test_api_key_never_appears_in_a_url(provider):
    _login_route()
    respx.get(f"{BASE}/series/1/extended").mock(return_value=httpx.Response(200, json={"data": {"seasons": []}}))
    respx.get(f"{BASE}/search/remoteid/tt0944947").mock(
        return_value=httpx.Response(200, json={"data": [{"series": {"id": 121361}}]})
    )
    respx.get(f"{BASE}/series/1/episodes/dvd").mock(
        return_value=httpx.Response(200, json={"data": {"episodes": [{"number": 1, "name": "One", "runtime": 30}]}})
    )
    await provider.seasons("1")
    await provider.resolve_show_id(ExternalIds(imdb="tt0944947"))
    await provider.season("1", 1)
    for call in respx.calls:
        assert "the-key" not in str(call.request.url)


@respx.mock
async def test_bearer_header_sent_on_authed_calls(provider):
    _login_route()
    route = respx.get(f"{BASE}/series/1/extended").mock(
        return_value=httpx.Response(200, json={"data": {"seasons": []}})
    )
    await provider.seasons("1")
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok-1"


# ---------------------------------------------------------------------------
# resolve_show_id
# ---------------------------------------------------------------------------


@respx.mock
async def test_resolve_show_id_via_tvdb_ids_makes_no_request(provider):
    ids = ExternalIds(tvdb="121361")
    result = await provider.resolve_show_id(ids)
    assert result == "121361"
    assert len(respx.calls) == 0


@respx.mock
async def test_resolve_show_id_with_no_ids_returns_none(provider):
    assert await provider.resolve_show_id(ExternalIds()) is None
    assert len(respx.calls) == 0


@respx.mock
async def test_resolve_show_id_picks_series_and_skips_movie(provider):
    _login_route()
    respx.get(f"{BASE}/search/remoteid/tt0944947").mock(
        return_value=httpx.Response(
            200,
            json={"data": [{"movie": {"id": 999}}, {"series": {"id": 121361}}]},
        )
    )
    result = await provider.resolve_show_id(ExternalIds(imdb="tt0944947"))
    assert result == "121361"


@respx.mock
async def test_resolve_show_id_miss_returns_none(provider):
    _login_route()
    respx.get(f"{BASE}/search/remoteid/tt0000000").mock(return_value=httpx.Response(200, json={"data": []}))
    assert await provider.resolve_show_id(ExternalIds(imdb="tt0000000")) is None


@respx.mock
async def test_resolve_show_id_only_movie_results_returns_none(provider):
    _login_route()
    respx.get(f"{BASE}/search/remoteid/tt0000001").mock(
        return_value=httpx.Response(200, json={"data": [{"movie": {"id": 999}}]})
    )
    assert await provider.resolve_show_id(ExternalIds(imdb="tt0000001")) is None


@respx.mock
async def test_resolve_show_id_series_without_id_raises_source_error(provider):
    _login_route()
    respx.get(f"{BASE}/search/remoteid/tt0000009").mock(
        return_value=httpx.Response(200, json={"data": [{"series": {"name": "No Id"}}]})
    )
    with pytest.raises(SourceError):
        await provider.resolve_show_id(ExternalIds(imdb="tt0000009"))


@respx.mock
async def test_resolve_show_id_non_list_data_raises_source_error(provider):
    _login_route()
    respx.get(f"{BASE}/search/remoteid/tt0000009").mock(return_value=httpx.Response(200, json={"data": "nope"}))
    with pytest.raises(SourceError):
        await provider.resolve_show_id(ExternalIds(imdb="tt0000009"))


@respx.mock
async def test_resolve_show_id_top_level_list_body_raises_source_error(provider):
    _login_route()
    respx.get(f"{BASE}/search/remoteid/tt0000009").mock(return_value=httpx.Response(200, json=["unexpected"]))
    with pytest.raises(SourceError):
        await provider.resolve_show_id(ExternalIds(imdb="tt0000009"))


# ---------------------------------------------------------------------------
# seasons
# ---------------------------------------------------------------------------


@respx.mock
async def test_seasons_filters_official_and_sorts(provider):
    _login_route()
    respx.get(f"{BASE}/series/1/extended").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "seasons": [
                        {"number": 0, "type": {"type": "official"}},
                        {"number": 2, "type": {"type": "official"}},
                        {"number": 1, "type": {"type": "official"}},
                        {"number": 1, "type": {"type": "dvd"}},
                    ]
                }
            },
        )
    )
    result = await provider.seasons("1")
    assert result == [1, 2]
    assert respx.calls.last.request.url.params["short"] == "true"


@respx.mock
async def test_seasons_entry_missing_number_is_skipped(provider):
    _login_route()
    respx.get(f"{BASE}/series/1/extended").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"seasons": [{"type": {"type": "official"}}, {"number": 1, "type": {"type": "official"}}]}},
        )
    )
    assert await provider.seasons("1") == [1]


@respx.mock
async def test_seasons_entry_with_bool_number_is_skipped(provider):
    _login_route()
    respx.get(f"{BASE}/series/1/extended").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "seasons": [
                        {"number": True, "type": {"type": "official"}},
                        {"number": 1, "type": {"type": "official"}},
                    ]
                }
            },
        )
    )
    assert await provider.seasons("1") == [1]


@respx.mock
async def test_seasons_non_list_raises_source_error(provider):
    _login_route()
    respx.get(f"{BASE}/series/1/extended").mock(return_value=httpx.Response(200, json={"data": {"seasons": "nope"}}))
    with pytest.raises(SourceError):
        await provider.seasons("1")


@respx.mock
async def test_seasons_top_level_list_body_raises_source_error(provider):
    _login_route()
    respx.get(f"{BASE}/series/1/extended").mock(return_value=httpx.Response(200, json=["unexpected"]))
    with pytest.raises(SourceError):
        await provider.seasons("1")


@respx.mock
async def test_seasons_non_dict_data_raises_source_error(provider):
    _login_route()
    respx.get(f"{BASE}/series/1/extended").mock(return_value=httpx.Response(200, json={"data": "nope"}))
    with pytest.raises(SourceError):
        await provider.seasons("1")


# ---------------------------------------------------------------------------
# season: dvd order, fallback to default, pagination, malformed payloads
# ---------------------------------------------------------------------------


@respx.mock
async def test_dvd_order_preferred_default_not_called(provider):
    _login_route()
    dvd_route = respx.get(f"{BASE}/series/1/episodes/dvd").mock(
        return_value=httpx.Response(200, json={"data": {"episodes": [{"number": 1, "name": "One", "runtime": 30}]}})
    )
    default_route = respx.get(f"{BASE}/series/1/episodes/default").mock(
        return_value=httpx.Response(200, json={"data": {"episodes": [{"number": 1, "name": "Wrong", "runtime": 30}]}})
    )
    episodes = await provider.season("1", 1)
    assert episodes[0].name == "One"
    assert episodes[0].season == 1
    assert dvd_route.call_count == 1
    assert default_route.call_count == 0


@respx.mock
async def test_fallback_to_default_when_dvd_empty(provider):
    _login_route()
    respx.get(f"{BASE}/series/1/episodes/dvd").mock(return_value=httpx.Response(200, json={"data": {"episodes": []}}))
    respx.get(f"{BASE}/series/1/episodes/default").mock(
        return_value=httpx.Response(200, json={"data": {"episodes": [{"number": 1, "name": "One", "runtime": 30}]}})
    )
    episodes = await provider.season("1", 1)
    assert episodes[0].name == "One"


@respx.mock
async def test_empty_dvd_and_default_raises_source_miss(provider):
    _login_route()
    respx.get(f"{BASE}/series/1/episodes/dvd").mock(return_value=httpx.Response(200, json={"data": {"episodes": []}}))
    respx.get(f"{BASE}/series/1/episodes/default").mock(
        return_value=httpx.Response(200, json={"data": {"episodes": []}})
    )
    with pytest.raises(SourceMiss):
        await provider.season("1", 1)


@respx.mock
async def test_pagination_follows_links_next(provider):
    _login_route()
    route = respx.get(f"{BASE}/series/1/episodes/dvd").mock(
        side_effect=[
            httpx.Response(
                200,
                json={
                    "data": {"episodes": [{"number": 1, "name": "One", "runtime": 30}]},
                    "links": {"next": "page2"},
                },
            ),
            httpx.Response(
                200,
                json={"data": {"episodes": [{"number": 2, "name": "Two", "runtime": 30}]}, "links": {"next": None}},
            ),
        ]
    )
    episodes = await provider.season("1", 1)
    assert [e.number for e in episodes] == [1, 2]
    assert route.call_count == 2
    assert route.calls[0].request.url.params["page"] == "0"
    assert route.calls[1].request.url.params["page"] == "1"


@respx.mock
async def test_pagination_caps_at_10_pages(provider):
    _login_route()
    responses = [
        httpx.Response(
            200,
            json={"data": {"episodes": [{"number": i + 1, "name": str(i), "runtime": 30}]}, "links": {"next": "more"}},
        )
        for i in range(15)
    ]
    route = respx.get(f"{BASE}/series/1/episodes/dvd").mock(side_effect=responses)
    episodes = await provider.season("1", 1)
    assert route.call_count == 10
    assert len(episodes) == 10


@respx.mock
async def test_season_non_list_episodes_raises_source_error(provider):
    _login_route()
    respx.get(f"{BASE}/series/1/episodes/dvd").mock(
        return_value=httpx.Response(200, json={"data": {"episodes": "nope"}})
    )
    with pytest.raises(SourceError):
        await provider.season("1", 1)


@respx.mock
async def test_season_top_level_list_body_raises_source_error(provider):
    _login_route()
    respx.get(f"{BASE}/series/1/episodes/dvd").mock(return_value=httpx.Response(200, json=["unexpected"]))
    with pytest.raises(SourceError):
        await provider.season("1", 1)


@respx.mock
async def test_season_non_dict_data_raises_source_error(provider):
    _login_route()
    respx.get(f"{BASE}/series/1/episodes/dvd").mock(return_value=httpx.Response(200, json={"data": "nope"}))
    with pytest.raises(SourceError):
        await provider.season("1", 1)


@respx.mock
async def test_season_entry_without_number_is_skipped(provider):
    _login_route()
    respx.get(f"{BASE}/series/1/episodes/dvd").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "episodes": [
                        {"name": "No Number", "runtime": 30},
                        {"number": 1, "name": "One", "runtime": 30},
                    ]
                }
            },
        )
    )
    episodes = await provider.season("1", 1)
    assert [e.number for e in episodes] == [1]


@respx.mock
async def test_season_entry_with_bool_number_is_skipped(provider):
    _login_route()
    respx.get(f"{BASE}/series/1/episodes/dvd").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "episodes": [
                        {"number": True, "name": "Bool", "runtime": 30},
                        {"number": 1, "name": "One", "runtime": 30},
                    ]
                }
            },
        )
    )
    episodes = await provider.season("1", 1)
    assert [e.number for e in episodes] == [1]


@respx.mock
async def test_season_sorted_by_number(provider):
    _login_route()
    respx.get(f"{BASE}/series/1/episodes/dvd").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "episodes": [
                        {"number": 2, "name": "Two", "runtime": 30},
                        {"number": 1, "name": "One", "runtime": 30},
                    ]
                }
            },
        )
    )
    episodes = await provider.season("1", 1)
    assert [e.number for e in episodes] == [1, 2]


@respx.mock
async def test_season_missing_name_maps_to_none(provider):
    _login_route()
    respx.get(f"{BASE}/series/1/episodes/dvd").mock(
        return_value=httpx.Response(200, json={"data": {"episodes": [{"number": 1, "runtime": 30}]}})
    )
    episodes = await provider.season("1", 1)
    assert episodes[0].name is None


# ---------------------------------------------------------------------------
# season: runtime edge cases (the 1440-minute upper bound guards against an
# OverflowError converting a huge/`inf` value to an int after *60)
# ---------------------------------------------------------------------------


@respx.mock
async def test_season_maps_runtime_minutes_to_seconds(provider):
    _login_route()
    respx.get(f"{BASE}/series/1/episodes/dvd").mock(
        return_value=httpx.Response(200, json={"data": {"episodes": [{"number": 1, "name": "One", "runtime": 42}]}})
    )
    episodes = await provider.season("1", 1)
    assert episodes[0].runtime_s == 42 * 60


@respx.mock
async def test_season_null_runtime_maps_to_none(provider):
    _login_route()
    respx.get(f"{BASE}/series/1/episodes/dvd").mock(
        return_value=httpx.Response(200, json={"data": {"episodes": [{"number": 1, "runtime": None}]}})
    )
    episodes = await provider.season("1", 1)
    assert episodes[0].runtime_s is None


@respx.mock
async def test_season_string_runtime_maps_to_none(provider):
    _login_route()
    respx.get(f"{BASE}/series/1/episodes/dvd").mock(
        return_value=httpx.Response(200, json={"data": {"episodes": [{"number": 1, "runtime": "sixty"}]}})
    )
    episodes = await provider.season("1", 1)
    assert episodes[0].runtime_s is None


@respx.mock
async def test_season_zero_runtime_maps_to_none(provider):
    _login_route()
    respx.get(f"{BASE}/series/1/episodes/dvd").mock(
        return_value=httpx.Response(200, json={"data": {"episodes": [{"number": 1, "runtime": 0}]}})
    )
    episodes = await provider.season("1", 1)
    assert episodes[0].runtime_s is None


@respx.mock
async def test_season_negative_runtime_maps_to_none(provider):
    _login_route()
    respx.get(f"{BASE}/series/1/episodes/dvd").mock(
        return_value=httpx.Response(200, json={"data": {"episodes": [{"number": 1, "runtime": -5}]}})
    )
    episodes = await provider.season("1", 1)
    assert episodes[0].runtime_s is None


@respx.mock
async def test_season_bool_runtime_maps_to_none(provider):
    _login_route()
    respx.get(f"{BASE}/series/1/episodes/dvd").mock(
        return_value=httpx.Response(200, json={"data": {"episodes": [{"number": 1, "runtime": True}]}})
    )
    episodes = await provider.season("1", 1)
    assert episodes[0].runtime_s is None


@respx.mock
async def test_season_runtime_at_1440_maps_to_none(provider):
    """The upper bound is exclusive: exactly 1440 minutes (a day) is out of
    range, not a boundary-included valid runtime."""
    _login_route()
    respx.get(f"{BASE}/series/1/episodes/dvd").mock(
        return_value=httpx.Response(200, json={"data": {"episodes": [{"number": 1, "runtime": 1440}]}})
    )
    episodes = await provider.season("1", 1)
    assert episodes[0].runtime_s is None


@respx.mock
async def test_season_huge_float_runtime_does_not_raise_overflow(provider):
    """A garbage runtime like `inf` must degrade to None, not raise
    OverflowError converting an infinite float to an int after *60 (the bug
    the 1440-minute upper bound was added to prevent). `json.dumps` refuses
    `float("inf")` (not JSON-compliant), so the body is built by hand with
    the `Infinity` token, which `json.loads`/httpx's parser accepts."""
    _login_route()
    body = b'{"data": {"episodes": [{"number": 1, "runtime": Infinity}]}}'
    respx.get(f"{BASE}/series/1/episodes/dvd").mock(
        return_value=httpx.Response(200, content=body, headers={"content-type": "application/json"})
    )
    episodes = await provider.season("1", 1)
    assert episodes[0].runtime_s is None
