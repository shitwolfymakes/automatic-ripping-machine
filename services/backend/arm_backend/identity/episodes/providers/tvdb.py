"""TVDB v4 episode-list provider (design spec 6.2, source `episodes_tvdb`).

TVDB v4 authenticates via a login handshake: `POST /login {"apikey": ...}`
returns a bearer token (see `arm_backend.metadata.tvdb.TVDBClient`, which does
the same handshake for key validation only). This provider caches the token
for 23h (an injected clock, not TVDB's own expiry, drives the refresh) and,
on a 401 from any authenticated call, logs in again once and retries that
call once; a second 401 in a row raises `SourceError` rather than looping.

401 vs. 403 is told apart via `SourceError.status` (not the exception
message, which is the literal string "auth" for both) — see `identity/http.py`.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from arm_common import Config
from arm_common.schemas import ExternalIds

from arm_backend.config import settings
from arm_backend.identity.episodes.model import Episode
from arm_backend.identity.episodes.providers.base import episode_name, is_int, runtime_s
from arm_backend.identity.http import SourceError, SourceHttp, SourceMiss

_TOKEN_TTL_S = 23 * 3600
_MAX_PAGES = 10


class TvdbEpisodes:
    source_id = "episodes_tvdb"
    id_field = "tvdb"

    def __init__(self, http: SourceHttp, api_key: str | None, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.http = http
        self._api_key = api_key
        self._clock = clock
        self._token: str | None = None
        self._token_at: float | None = None

    def configured(self, cfg: Config) -> str | None:
        # `cfg` is accepted to satisfy EpisodeListProvider's shape; the key
        # bound at construction (how this provider is wired) is authoritative,
        # not whatever `cfg.tvdb_api_key` currently holds.
        del cfg
        if not self._api_key:
            return "no TVDB key"
        return None

    # -- auth -----------------------------------------------------------

    async def _login(self) -> str:
        body = await self.http.post_json(f"{settings.ARM_TVDB_BASE_URL}/login", json={"apikey": self._api_key})
        try:
            token = body["data"]["token"]
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise SourceError("tvdb malformed response") from e
        if not isinstance(token, str) or not token:
            raise SourceError("tvdb malformed response")
        self._token = token
        self._token_at = self._clock()
        return token

    async def _ensure_token(self) -> str:
        if self._token is None or self._token_at is None or self._clock() - self._token_at >= _TOKEN_TTL_S:
            return await self._login()
        return self._token

    async def _get_authed(self, url: str, *, params: dict[str, Any] | None = None) -> Any:
        token = await self._ensure_token()
        try:
            return await self.http.get_json(url, params=params, headers={"Authorization": f"Bearer {token}"})
        except SourceError as e:
            if e.status != 401:
                raise
            token = await self._login()
            try:
                return await self.http.get_json(url, params=params, headers={"Authorization": f"Bearer {token}"})
            except SourceError as e2:
                if e2.status == 401:
                    raise SourceError("tvdb auth failed after re-login") from e2
                raise

    # -- EpisodeListProvider ---------------------------------------------

    async def resolve_show_id(self, ids: ExternalIds) -> str | None:
        if ids.tvdb:
            return ids.tvdb
        if not ids.imdb:
            return None
        try:
            body = await self._get_authed(f"{settings.ARM_TVDB_BASE_URL}/search/remoteid/{ids.imdb}")
        except SourceMiss:
            return None
        try:
            results = body["data"]
            if not isinstance(results, list):
                raise SourceError("tvdb malformed response")
            for entry in results:
                if isinstance(entry, dict) and isinstance(entry.get("series"), dict):
                    return str(entry["series"]["id"])
            return None
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise SourceError("tvdb malformed response") from e

    async def seasons(self, show_id: str) -> list[int]:
        body = await self._get_authed(
            f"{settings.ARM_TVDB_BASE_URL}/series/{show_id}/extended", params={"short": "true"}
        )
        try:
            data = body["data"]
            if not isinstance(data, dict):
                raise SourceError("tvdb malformed response")
            raw_seasons = data["seasons"]
            if not isinstance(raw_seasons, list):
                raise SourceError("tvdb malformed response")
            numbers = {
                s["number"]
                for s in raw_seasons
                if isinstance(s, dict)
                and isinstance(s.get("type"), dict)
                and s["type"].get("type") == "official"
                and is_int(s.get("number"))
                and s["number"] > 0
            }
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise SourceError("tvdb malformed response") from e
        return sorted(numbers)

    async def season(self, show_id: str, number: int) -> list[Episode]:
        episodes = self._map_episodes(await self._collect_pages(show_id, number, "dvd"), number)
        if not episodes:
            episodes = self._map_episodes(await self._collect_pages(show_id, number, "default"), number)
        if not episodes:
            raise SourceMiss(f"tvdb season {number} for show {show_id} not found")
        episodes.sort(key=lambda ep: ep.number)
        return episodes

    async def _collect_pages(self, show_id: str, season_number: int, order: str) -> list[Any]:
        episodes: list[Any] = []
        page = 0
        while page < _MAX_PAGES:
            try:
                body = await self._get_authed(
                    f"{settings.ARM_TVDB_BASE_URL}/series/{show_id}/episodes/{order}",
                    params={"season": season_number, "page": page},
                )
            except SourceMiss:
                break
            try:
                data = body["data"]
                if not isinstance(data, dict):
                    raise SourceError("tvdb malformed response")
                page_episodes = data["episodes"]
                if not isinstance(page_episodes, list):
                    raise SourceError("tvdb malformed response")
                episodes.extend(page_episodes)
                links = body.get("links")
                has_next = bool(isinstance(links, dict) and links.get("next"))
            except (KeyError, TypeError, ValueError, AttributeError) as e:
                raise SourceError("tvdb malformed response") from e
            if not has_next:
                break
            page += 1
        return episodes

    @staticmethod
    def _map_episodes(raw: list[Any], number: int) -> list[Episode]:
        return [
            Episode(
                season=number,
                number=e["number"],
                name=episode_name(e.get("name")),
                runtime_s=runtime_s(e.get("runtime")),
            )
            for e in raw
            if isinstance(e, dict) and is_int(e.get("number"))
        ]
