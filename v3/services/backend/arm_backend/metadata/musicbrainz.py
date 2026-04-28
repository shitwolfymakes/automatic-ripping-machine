import asyncio
import logging
import time
from typing import Any

import httpx

from arm_backend.metadata.base import LookupError, LookupTimeout, MetadataResult

logger = logging.getLogger("arm_backend.metadata.musicbrainz")

_BASE_URL = "https://musicbrainz.org/ws/2"
_MIN_INTERVAL_SECONDS = 1.0

_lock = asyncio.Lock()
_last_call_at: float = 0.0


async def _rate_limit() -> None:
    """Hold the global MB semaphore + enforce 1 req/s minimum spacing.

    MusicBrainz blocks clients that exceed 1 req/s; the lock + min-interval
    guard keeps us compliant even if multiple identify handlers hit the
    dispatcher concurrently.
    """
    global _last_call_at
    async with _lock:
        delta = time.monotonic() - _last_call_at
        if delta < _MIN_INTERVAL_SECONDS:
            await asyncio.sleep(_MIN_INTERVAL_SECONDS - delta)
        _last_call_at = time.monotonic()


class MusicBrainzClient:
    def __init__(self, user_agent: str, http: httpx.AsyncClient) -> None:
        if not user_agent:
            raise ValueError("MusicBrainz requires a non-empty user-agent string")
        self._user_agent = user_agent
        self._http = http

    async def lookup_disc_id(self, disc_id: str) -> MetadataResult:
        await _rate_limit()

        try:
            r = await self._http.get(
                f"{_BASE_URL}/discid/{disc_id}",
                params={"inc": "artists+recordings", "fmt": "json"},
                headers={"User-Agent": self._user_agent, "Accept": "application/json"},
            )
        except httpx.TimeoutException as e:
            raise LookupTimeout("musicbrainz timeout") from e
        except httpx.HTTPError as e:
            raise LookupError(f"musicbrainz transport error: {e}") from e

        if r.status_code == 404:
            raise LookupError("musicbrainz disc_id not found")
        if r.status_code >= 500:
            raise LookupError(f"musicbrainz 5xx status={r.status_code}")
        if r.status_code != 200:
            raise LookupError(f"musicbrainz status={r.status_code}")

        body: dict[str, Any] = r.json()
        releases = body.get("releases") or []
        if not releases:
            raise LookupError("musicbrainz disc_id has no releases")

        top = releases[0]
        title_val = top.get("title")
        date = top.get("date") or ""
        year_val = int(date[:4]) if date[:4].isdigit() else None
        if not title_val:
            raise LookupError("musicbrainz top release missing title")

        return MetadataResult(title=title_val, year=year_val, kind="music", payload=top)
