"""SourceHttp: rate limit, TTL cache, 429 retry, error mapping, backoff."""

import httpx
import pytest
import respx

from arm_backend.identity.http import SourceError, SourceHttp, SourceMiss, SourcePolicy

URL = "https://example.test/x"


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    async def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.t += s


@pytest.fixture
async def http_client():
    async with httpx.AsyncClient(timeout=5.0) as client:
        yield client


def make(http_client, clock, **kw) -> SourceHttp:
    return SourceHttp(http_client, SourcePolicy(min_interval_s=0.5, **kw), clock=clock.now, sleep=clock.sleep)


@respx.mock
async def test_second_call_is_cached(http_client) -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, json={"a": 1}))
    c = Clock()
    s = make(http_client, c)
    assert await s.get_json(URL) == {"a": 1}
    assert await s.get_json(URL) == {"a": 1}
    assert route.call_count == 1


@respx.mock
async def test_cache_expires(http_client) -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(200, json={"a": 1}))
    c = Clock()
    s = make(http_client, c, cache_ttl_s=10)
    await s.get_json(URL)
    c.t += 11
    await s.get_json(URL)
    assert route.call_count == 2


@respx.mock
async def test_rate_limit_waits_between_requests(http_client) -> None:
    respx.get(URL, params={"n": "1"}).mock(return_value=httpx.Response(200, json=1))
    respx.get(URL, params={"n": "2"}).mock(return_value=httpx.Response(200, json=2))
    c = Clock()
    s = make(http_client, c)
    await s.get_json(URL, params={"n": "1"})
    await s.get_json(URL, params={"n": "2"})
    assert c.slept and abs(sum(c.slept) - 0.5) < 1e-9


@respx.mock
async def test_404_is_miss_and_5xx_is_error(http_client) -> None:
    respx.get(URL + "/missing").mock(return_value=httpx.Response(404))
    respx.get(URL + "/broken").mock(return_value=httpx.Response(503))
    s = make(http_client, Clock())
    with pytest.raises(SourceMiss):
        await s.get_json(URL + "/missing")
    with pytest.raises(SourceError):
        await s.get_json(URL + "/broken")


@respx.mock
async def test_429_retries_once_after_retry_after(http_client) -> None:
    respx.get(URL).mock(side_effect=[httpx.Response(429, headers={"Retry-After": "2"}), httpx.Response(200, json=7)])
    c = Clock()
    s = make(http_client, c)
    assert await s.get_json(URL) == 7
    assert 2 in c.slept


@respx.mock
async def test_backoff_after_three_errors(http_client) -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(500))
    c = Clock()
    s = make(http_client, c, backoff_after=3, backoff_s=600)
    for _ in range(3):
        with pytest.raises(SourceError):
            await s.get_json(URL)
    assert s.backing_off()
    with pytest.raises(SourceError, match="backing off"):
        await s.get_json(URL)
    assert route.call_count == 3
    c.t += 601
    assert not s.backing_off()


@respx.mock
async def test_timeout_and_bad_json_are_errors(http_client) -> None:
    respx.get(URL + "/slow").mock(side_effect=httpx.ReadTimeout("slow"))
    respx.get(URL + "/html").mock(return_value=httpx.Response(200, text="<html>"))
    s = make(http_client, Clock())
    with pytest.raises(SourceError):
        await s.get_json(URL + "/slow")
    with pytest.raises(SourceError):
        await s.get_json(URL + "/html")


@respx.mock
async def test_post_json_success(http_client) -> None:
    respx.post(URL).mock(return_value=httpx.Response(200, json={"ok": True}))
    s = make(http_client, Clock())
    assert await s.post_json(URL, json={"q": "x"}) == {"ok": True}


@respx.mock
async def test_post_json_error_mapping(http_client) -> None:
    respx.post(URL + "/missing").mock(return_value=httpx.Response(404))
    respx.post(URL + "/broken").mock(return_value=httpx.Response(503))
    s = make(http_client, Clock())
    with pytest.raises(SourceMiss):
        await s.post_json(URL + "/missing", json={})
    with pytest.raises(SourceError):
        await s.post_json(URL + "/broken", json={})


@respx.mock
async def test_401_is_auth_error(http_client) -> None:
    respx.get(URL).mock(return_value=httpx.Response(401))
    s = make(http_client, Clock())
    with pytest.raises(SourceError, match="auth"):
        await s.get_json(URL)


@respx.mock
async def test_403_is_auth_error(http_client) -> None:
    respx.get(URL).mock(return_value=httpx.Response(403))
    s = make(http_client, Clock())
    with pytest.raises(SourceError, match="auth"):
        await s.get_json(URL)


@respx.mock
async def test_second_429_raises_source_error(http_client) -> None:
    respx.get(URL).mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "1"}),
            httpx.Response(429, headers={"Retry-After": "1"}),
        ]
    )
    c = Clock()
    s = make(http_client, c)
    with pytest.raises(SourceError):
        await s.get_json(URL)


@respx.mock
async def test_cache_evicts_oldest_beyond_cache_max(http_client) -> None:
    respx.get(URL + "/1").mock(return_value=httpx.Response(200, json=1))
    respx.get(URL + "/2").mock(return_value=httpx.Response(200, json=2))
    respx.get(URL + "/3").mock(return_value=httpx.Response(200, json=3))
    c = Clock()
    s = make(http_client, c, cache_max=2)
    await s.get_json(URL + "/1")
    await s.get_json(URL + "/2")
    await s.get_json(URL + "/3")  # evicts URL + "/1"
    route1 = respx.get(URL + "/1").mock(return_value=httpx.Response(200, json="again"))
    # /1 was evicted, so this must be a fresh request (a still-cached value
    # would still be `1`, not the newly mocked "again").
    assert await s.get_json(URL + "/1") == "again"
    assert route1.call_count == 2


@respx.mock
async def test_transport_error_is_source_error(http_client) -> None:
    respx.get(URL).mock(side_effect=httpx.ConnectError("refused"))
    s = make(http_client, Clock())
    with pytest.raises(SourceError):
        await s.get_json(URL)


@respx.mock
async def test_transport_error_during_429_retry_is_source_error(http_client) -> None:
    respx.get(URL).mock(side_effect=[httpx.Response(429, headers={"Retry-After": "1"}), httpx.ConnectError("refused")])
    c = Clock()
    s = make(http_client, c)
    with pytest.raises(SourceError):
        await s.get_json(URL)


@respx.mock
async def test_timeout_during_429_retry_is_source_error(http_client) -> None:
    respx.get(URL).mock(side_effect=[httpx.Response(429, headers={"Retry-After": "1"}), httpx.ReadTimeout("slow")])
    c = Clock()
    s = make(http_client, c)
    with pytest.raises(SourceError):
        await s.get_json(URL)


@respx.mock
async def test_429_missing_retry_after_uses_default(http_client) -> None:
    respx.get(URL).mock(side_effect=[httpx.Response(429), httpx.Response(200, json=1)])
    c = Clock()
    s = make(http_client, c)
    assert await s.get_json(URL) == 1
    assert 5 in c.slept


@respx.mock
async def test_429_non_integer_retry_after_uses_default(http_client) -> None:
    respx.get(URL).mock(side_effect=[httpx.Response(429, headers={"Retry-After": "soon"}), httpx.Response(200, json=1)])
    c = Clock()
    s = make(http_client, c)
    assert await s.get_json(URL) == 1
    assert 5 in c.slept


@respx.mock
async def test_post_json_while_backing_off_raises_without_request(http_client) -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(500))
    c = Clock()
    s = make(http_client, c, backoff_after=3, backoff_s=600)
    for _ in range(3):
        with pytest.raises(SourceError):
            await s.get_json(URL)
    assert s.backing_off()
    with pytest.raises(SourceError, match="backing off"):
        await s.post_json(URL, json={})
    assert route.call_count == 3


@respx.mock
async def test_source_miss_resets_error_counter(http_client) -> None:
    respx.get(URL + "/err").mock(return_value=httpx.Response(500))
    respx.get(URL + "/miss").mock(return_value=httpx.Response(404))
    c = Clock()
    s = make(http_client, c, backoff_after=3, backoff_s=600)
    with pytest.raises(SourceError):
        await s.get_json(URL + "/err")
    with pytest.raises(SourceError):
        await s.get_json(URL + "/err")
    with pytest.raises(SourceMiss):
        await s.get_json(URL + "/miss")
    with pytest.raises(SourceError):
        await s.get_json(URL + "/err")
    with pytest.raises(SourceError):
        await s.get_json(URL + "/err")
    # Only 4 consecutive errors total but a miss reset the streak after the
    # first 2, so backing_off should still be False (need 3 in a row).
    assert not s.backing_off()
