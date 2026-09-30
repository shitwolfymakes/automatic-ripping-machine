"""SourceHttp: a rate-limited, TTL-cached, backoff-aware async HTTP helper.

Shared by the episode-list providers (TMDb, TVmaze, TVDB): each provider gets
its own `SourceHttp` instance (state is per-instance, never shared across
providers) built from one of the `POLICIES` below.

Never logs headers or params — those may carry API keys.
"""

import asyncio
import copy
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger("arm_backend.identity.http")


class SourceError(Exception):
    """Transient failure: timeout, transport error, a second 429, a 5xx, or
    an invalid JSON body. Callers may retry later."""


class SourceMiss(Exception):
    """Definitive miss: 404, or another "no such record" response."""


@dataclass(frozen=True)
class SourcePolicy:
    min_interval_s: float
    timeout_s: float = 8.0
    cache_ttl_s: float = 86400
    cache_max: int = 512
    backoff_after: int = 3
    backoff_s: float = 600


POLICIES: dict[str, SourcePolicy] = {
    "episodes_tmdb": SourcePolicy(min_interval_s=0.05),
    "episodes_tvmaze": SourcePolicy(min_interval_s=0.5),
    "episodes_tvdb": SourcePolicy(min_interval_s=0.1),
}

_DEFAULT_RETRY_AFTER = 5
_MAX_RETRY_AFTER = 30


class SourceHttp:
    """Per-provider async HTTP helper: rate limit, TTL cache, 429 retry-once,
    status-code error mapping, and consecutive-error backoff.

    A single `asyncio.Lock` guards both the rate-limit wait and the cache, so
    at most one request (and one cache read/write) happens at a time per
    instance.
    """

    def __init__(
        self,
        http: httpx.AsyncClient,
        policy: SourcePolicy,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._http = http
        self._policy = policy
        self._clock = clock
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._last_request_at: float | None = None
        self._cache: dict[str, tuple[float, Any]] = {}
        self._consecutive_errors = 0
        self._backing_off_since: float | None = None

    def backing_off(self) -> bool:
        # Side effect is intentional: once `backoff_s` has elapsed, this call
        # clears the backoff state AND resets the error streak, so the very
        # next request gets a clean slate rather than tripping backoff again
        # after a single new error.
        if self._backing_off_since is None:
            return False
        if self._clock() - self._backing_off_since >= self._policy.backoff_s:
            self._backing_off_since = None
            self._consecutive_errors = 0
            return False
        return True

    async def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
        cache_key: str | None = None,
        follow_redirects: bool = False,
    ) -> Any:
        key = cache_key or self._make_cache_key(url, params)
        async with self._lock:
            cached = self._cache_get(key)
            if cached is not _MISSING:
                return cached
            if self.backing_off():
                raise SourceError("backing off")
            await self._wait_for_rate_limit()
            result = await self._request("GET", url, params=params, headers=headers, follow_redirects=follow_redirects)
            self._cache_put(key, result)
            return result

    async def post_json(
        self,
        url: str,
        *,
        json: dict[str, Any],
        headers: dict[str, Any] | None = None,
    ) -> Any:
        async with self._lock:
            if self.backing_off():
                raise SourceError("backing off")
            await self._wait_for_rate_limit()
            return await self._request("POST", url, json=json, headers=headers)

    async def _wait_for_rate_limit(self) -> None:
        now = self._clock()
        if self._last_request_at is not None:
            elapsed = now - self._last_request_at
            remaining = self._policy.min_interval_s - elapsed
            if remaining > 0:
                await self._sleep(remaining)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, Any] | None = None,
        follow_redirects: bool = False,
    ) -> Any:
        try:
            response = await self._send(
                method, url, params=params, json=json, headers=headers, follow_redirects=follow_redirects
            )
        except httpx.TimeoutException as e:
            self._record_error()
            raise SourceError(f"{method} timeout") from e
        except httpx.HTTPError as e:
            self._record_error()
            raise SourceError(f"{method} transport error: {e}") from e

        self._last_request_at = self._clock()

        if response.status_code == 429:
            response = await self._retry_after_429(method, response, url, params, json, headers, follow_redirects)

        return self._handle_response(method, response)

    async def _send(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None,
        json: dict[str, Any] | None,
        headers: dict[str, Any] | None,
        follow_redirects: bool,
    ) -> httpx.Response:
        return await self._http.request(
            method,
            url,
            params=params,
            json=json,
            headers=headers,
            follow_redirects=follow_redirects,
            timeout=self._policy.timeout_s,
        )

    async def _retry_after_429(
        self,
        method: str,
        response: httpx.Response,
        url: str,
        params: dict[str, Any] | None,
        json: dict[str, Any] | None,
        headers: dict[str, Any] | None,
        follow_redirects: bool,
    ) -> httpx.Response:
        retry_after = _parse_retry_after(response.headers.get("Retry-After"))
        await self._sleep(retry_after)
        try:
            retried = await self._send(
                method, url, params=params, json=json, headers=headers, follow_redirects=follow_redirects
            )
        except httpx.TimeoutException as e:
            self._record_error()
            raise SourceError(f"{method} timeout") from e
        except httpx.HTTPError as e:
            self._record_error()
            raise SourceError(f"{method} transport error: {e}") from e
        self._last_request_at = self._clock()
        if retried.status_code == 429:
            self._record_error()
            raise SourceError("rate limited (429) twice")
        return retried

    def _handle_response(self, method: str, response: httpx.Response) -> Any:
        status = response.status_code
        if status == 404:
            self._record_miss()
            raise SourceMiss(f"{method} 404 not found")
        if status in (401, 403):
            logger.warning("auth_failed method=%s status=%d", method, status)
            self._record_error()
            raise SourceError("auth")
        if status < 200 or status >= 300:
            self._record_error()
            raise SourceError(f"{method} status={status}")
        try:
            body = response.json()
        except ValueError as e:
            self._record_error()
            raise SourceError(f"{method} returned invalid JSON") from e
        self._record_success()
        return body

    def _record_error(self) -> None:
        self._consecutive_errors += 1
        if self._consecutive_errors >= self._policy.backoff_after and self._backing_off_since is None:
            self._backing_off_since = self._clock()
            logger.warning("backing_off consecutive_errors=%d", self._consecutive_errors)

    def _record_success(self) -> None:
        self._consecutive_errors = 0
        self._backing_off_since = None

    def _record_miss(self) -> None:
        self._consecutive_errors = 0
        self._backing_off_since = None

    @staticmethod
    def _make_cache_key(url: str, params: dict[str, Any] | None) -> str:
        if not params:
            return url
        return url + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))

    def _cache_get(self, key: str) -> Any:
        entry = self._cache.get(key)
        if entry is None:
            return _MISSING
        stored_at, value = entry
        if self._clock() - stored_at >= self._policy.cache_ttl_s:
            del self._cache[key]
            return _MISSING
        # Deep-copy out: callers (providers/stage) may mutate the returned
        # JSON in place (sort/pop/append). Handing out the stored reference
        # would let that mutation corrupt the cached value for every other
        # caller sharing this SourceHttp, for up to cache_ttl_s.
        return copy.deepcopy(value)

    def _cache_put(self, key: str, value: Any) -> None:
        # Drop any existing entry for this key first so a re-put moves it to
        # the end of the dict — eviction order (oldest-first) then reflects
        # the latest write, not the key's original insertion position.
        self._cache.pop(key, None)
        # Deep-copy in: store our own copy so a caller mutating `value` after
        # this call can't corrupt what's cached (see the mirror comment in
        # _cache_get).
        self._cache[key] = (self._clock(), copy.deepcopy(value))
        while len(self._cache) > self._policy.cache_max:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]


class _Missing:
    """Sentinel distinct from a cached `None`/falsy JSON value."""


_MISSING = _Missing()


def _parse_retry_after(raw: str | None) -> float:
    if raw is None:
        return _DEFAULT_RETRY_AFTER
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_RETRY_AFTER
    return max(0, min(value, _MAX_RETRY_AFTER))
