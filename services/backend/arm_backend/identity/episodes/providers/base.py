"""What an episode-list provider is (design spec 6.2).

One `EpisodeListProvider` per external episode-order source (TMDb, TVmaze,
TVDB). Each provider owns its own `SourceHttp` instance (rate limit, cache,
and backoff state are never shared across providers) — the episode-match
stage reads `provider.http.backing_off()` directly to decide whether to skip
a provider without spending a request on it.
"""

from __future__ import annotations

from typing import Protocol

from arm_common import Config
from arm_common.schemas import ExternalIds

from arm_backend.identity.episodes.model import Episode
from arm_backend.identity.http import SourceHttp


class EpisodeListProvider(Protocol):
    source_id: str  # "episodes_tmdb" etc.
    id_field: str  # ExternalIds field holding this provider's show id: "tmdb" | "tvmaze" | "tvdb"
    http: SourceHttp

    def configured(self, cfg: Config) -> str | None:
        """None when usable; otherwise the skip reason (e.g. "no TVDB key")."""
        ...

    async def resolve_show_id(self, ids: ExternalIds) -> str | None:
        """This provider's show id from the ids already known; None if it cannot."""
        ...

    async def seasons(self, show_id: str) -> list[int]:
        """Regular season numbers (> 0), ascending."""
        ...

    async def season(self, show_id: str, number: int) -> list[Episode]:
        """Episodes of one season in episode order. Raises SourceMiss when the season does not exist."""
        ...
