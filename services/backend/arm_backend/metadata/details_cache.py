"""A small in-process TTL cache for match details (match picker spec 3.4)."""

from __future__ import annotations

import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class TtlCache(Generic[K, V]):
    """Entries expire `ttl_s` after they were put; past `max_entries` the
    oldest put is evicted. Not shared across processes."""

    def __init__(
        self, ttl_s: float = 3600.0, max_entries: int = 256, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._ttl = ttl_s
        self._max = max_entries
        self._clock = clock
        self._entries: OrderedDict[K, tuple[float, V]] = OrderedDict()

    def get(self, key: K) -> V | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        expires, value = entry
        if self._clock() >= expires:
            del self._entries[key]
            return None
        return value

    def put(self, key: K, value: V) -> None:
        self._entries.pop(key, None)
        self._entries[key] = (self._clock() + self._ttl, value)
        while len(self._entries) > self._max:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()
