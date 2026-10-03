"""TMDb episode-list provider (design spec 6.2, source `episodes_tmdb`).

Show ids come from `ExternalIds.tmdb` when already known, else are resolved
via TMDb's `/find` endpoint from an IMDb or TVDB id. Auth is the v4 bearer
token in the `Authorization` header — never a query param — so the key never
reaches a URL or a log line (see `SourceHttp`, which never logs headers).
"""

from __future__ import annotations

from arm_common import Config
from arm_common.schemas import ExternalIds

from arm_backend.config import settings
from arm_backend.identity.episodes.model import Episode
from arm_backend.identity.episodes.providers.base import episode_name, is_int, runtime_s
from arm_backend.identity.http import SourceError, SourceHttp


class TmdbEpisodes:
    source_id = "episodes_tmdb"
    id_field = "tmdb"

    def __init__(self, http: SourceHttp, api_key: str | None) -> None:
        self.http = http
        self._api_key = api_key

    def configured(self, cfg: Config) -> str | None:
        # `cfg` is accepted to satisfy EpisodeListProvider's shape; the key
        # bound at construction (how this provider is wired) is authoritative,
        # not whatever `cfg.tmdb_api_key` currently holds.
        del cfg
        if not self._api_key:
            return "no TMDb key"
        return None

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}", "Accept": "application/json"}

    async def resolve_show_id(self, ids: ExternalIds) -> str | None:
        if ids.tmdb:
            return ids.tmdb
        if ids.imdb:
            return await self._find(ids.imdb, "imdb_id")
        if ids.tvdb:
            return await self._find(ids.tvdb, "tvdb_id")
        return None

    async def _find(self, external_id: str, external_source: str) -> str | None:
        body = await self.http.get_json(
            f"{settings.ARM_TMDB_BASE_URL}/find/{external_id}",
            params={"external_source": external_source},
            headers=self._headers,
        )
        try:
            results = body.get("tv_results") or []
            if not results:
                return None
            return str(results[0]["id"])
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise SourceError("tmdb malformed response") from e

    async def seasons(self, show_id: str) -> list[int]:
        body = await self.http.get_json(f"{settings.ARM_TMDB_BASE_URL}/tv/{show_id}", headers=self._headers)
        try:
            raw_seasons = body.get("seasons", [])
            if not isinstance(raw_seasons, list):
                raise SourceError("tmdb malformed response")
            numbers = [
                s["season_number"]
                for s in raw_seasons
                if isinstance(s, dict) and is_int(s.get("season_number")) and s["season_number"] > 0
            ]
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise SourceError("tmdb malformed response") from e
        return sorted(numbers)

    async def season(self, show_id: str, number: int) -> list[Episode]:
        body = await self.http.get_json(
            f"{settings.ARM_TMDB_BASE_URL}/tv/{show_id}/season/{number}", headers=self._headers
        )
        try:
            raw_episodes = body.get("episodes") or []
            if not isinstance(raw_episodes, list):
                raise SourceError("tmdb malformed response")
            episodes = [
                Episode(
                    season=number,
                    number=e["episode_number"],
                    name=episode_name(e.get("name")),
                    runtime_s=runtime_s(e.get("runtime")),
                    special=(number == 0),
                )
                for e in raw_episodes
                if isinstance(e, dict) and is_int(e.get("episode_number"))
            ]
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise SourceError("tmdb malformed response") from e
        if not episodes:
            # An existing season with no (usable) episodes is a degenerate/
            # transient response (C7), not a definitive miss — the season
            # route itself 404s when the season truly doesn't exist.
            raise SourceError(f"tmdb season {number} for show {show_id} returned no episodes")
        episodes.sort(key=lambda ep: ep.number)
        return episodes
