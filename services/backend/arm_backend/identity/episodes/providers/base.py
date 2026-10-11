"""What an episode-list provider is (design spec 6.2).

One `EpisodeListProvider` per external episode-order source (TMDb, TVmaze,
TVDB). Each provider owns its own `SourceHttp` instance (rate limit, cache,
and backoff state are never shared across providers) — the episode-match
stage reads `provider.http.backing_off()` directly to decide whether to skip
a provider without spending a request on it.
"""

from __future__ import annotations

import math
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


# Runtimes of a day or more are garbage, and bounding them also keeps the
# `* 60` from overflowing an int conversion of a huge float.
MAX_RUNTIME_MIN = 1440


def is_int(value: object) -> bool:
    """True for a real int, false for a bool (a `bool` is an `int` subclass
    in Python but is never a valid season/episode number)."""
    return isinstance(value, int) and not isinstance(value, bool)


def runtime_s(value: object) -> int | None:
    """Minutes -> seconds, only for a finite, sane positive runtime; booleans,
    strings, non-finite floats, zero/negative values, and runtimes of
    MAX_RUNTIME_MIN minutes or more all map to None (a malformed runtime must
    not crash the provider, and must not read as a real runtime downstream)."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if not math.isfinite(value) or value <= 0 or value >= MAX_RUNTIME_MIN:
        return None
    return int(value * 60)


def episode_name(value: object) -> str | None:
    """A non-empty str name, else None (a provider has been seen to send
    numbers or objects where a name belongs)."""
    return value if isinstance(value, str) and value else None
