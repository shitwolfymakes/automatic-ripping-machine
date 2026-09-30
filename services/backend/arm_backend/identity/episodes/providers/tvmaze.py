"""TVmaze episode-list provider (design spec 6.2, source `episodes_tvmaze`).

TVmaze needs no API key (`configured` is always usable). Show ids come from
`ExternalIds.tvmaze` when already known, else are resolved via TVmaze's
`/lookup/shows` endpoint from an IMDb or TVDB id.

One `GET /shows/{id}/episodes?specials=1` request per show serves both
`seasons` and every `season` call — cached under `tvmaze:episodes:{id}` (via
`SourceHttp`'s `cache_key`) so the per-show episode list is fetched once
regardless of how many seasons the episode-match stage asks for.
"""

from __future__ import annotations

from arm_common import Config
from arm_common.schemas import ExternalIds

from arm_backend.config import settings
from arm_backend.identity.episodes.model import Episode
from arm_backend.identity.episodes.providers.base import episode_name, is_int, runtime_s
from arm_backend.identity.http import SourceError, SourceHttp, SourceMiss


class TvmazeEpisodes:
    source_id = "episodes_tvmaze"
    id_field = "tvmaze"

    def __init__(self, http: SourceHttp) -> None:
        self.http = http

    def configured(self, cfg: Config) -> str | None:
        # TVmaze needs no API key; `cfg` is accepted only to satisfy
        # EpisodeListProvider's shape.
        del cfg
        return None

    async def resolve_show_id(self, ids: ExternalIds) -> str | None:
        if ids.tvmaze:
            return ids.tvmaze
        if ids.imdb:
            return await self._lookup("imdb", ids.imdb)
        if ids.tvdb:
            return await self._lookup("thetvdb", ids.tvdb)
        return None

    async def _lookup(self, param: str, value: str) -> str | None:
        try:
            body = await self.http.get_json(
                f"{settings.ARM_TVMAZE_BASE_URL}/lookup/shows",
                params={param: value},
                follow_redirects=True,
            )
        except SourceMiss:
            return None
        try:
            return str(body["id"])
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise SourceError("tvmaze malformed response") from e

    async def _episodes(self, show_id: str) -> list[object]:
        body = await self.http.get_json(
            f"{settings.ARM_TVMAZE_BASE_URL}/shows/{show_id}/episodes",
            params={"specials": "1"},
            cache_key=f"tvmaze:episodes:{show_id}",
        )
        if not isinstance(body, list):
            raise SourceError("tvmaze malformed response")
        if not body:
            # An existing show with a genuinely empty episode list is a
            # degenerate/transient response (C7, mirroring TMDb's empty-season
            # rule), not a definitive miss.
            raise SourceError(f"tvmaze show {show_id} returned no episodes")
        return body

    async def seasons(self, show_id: str) -> list[int]:
        episodes = await self._episodes(show_id)
        numbers = {
            e["season"]
            for e in episodes
            if isinstance(e, dict) and is_int(e.get("season")) and e["season"] > 0 and is_int(e.get("number"))
        }
        return sorted(numbers)

    async def season(self, show_id: str, number: int) -> list[Episode]:
        episodes = await self._episodes(show_id)
        result = [
            Episode(
                season=number,
                number=e["number"],
                name=episode_name(e.get("name")),
                runtime_s=runtime_s(e.get("runtime")),
            )
            for e in episodes
            if isinstance(e, dict) and e.get("season") == number and is_int(e.get("number"))
        ]
        if not result:
            raise SourceMiss(f"tvmaze season {number} for show {show_id} not found")
        result.sort(key=lambda ep: ep.number)
        return result
