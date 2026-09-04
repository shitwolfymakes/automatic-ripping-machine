"""Shared "can this docker host run image X right now?" probe, with a TTL cache.

Used by the transcode dispatcher and the ripper manager for
/api/system/diagnostics. Synchronous and never raises — callers run it via
asyncio.to_thread from request handlers.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

import docker.errors  # type: ignore[import-untyped]

# How long a probe result is reused before re-pinging the docker host. An
# unreachable ssh host stalls each uncached call for docker-py's client
# timeout, and diagnostics polls this on every request.
PROBE_TTL_SECONDS = 30.0


def probe_docker(client: Any, image: str) -> tuple[bool, str | None]:
    """Ping the daemon, then check `image` exists there. (ok, detail)."""
    try:
        client.ping()
    except Exception as exc:  # noqa: BLE001 — any transport failure is the same answer
        return False, f"docker host unreachable: {exc}"
    try:
        client.images.get(image)
    except docker.errors.ImageNotFound:
        return False, f"image {image} not present on docker host"
    except Exception as exc:  # noqa: BLE001
        return False, f"image check failed: {exc}"
    return True, None


class TtlProbe:
    """Memoise a probe callable for `ttl` seconds — failures included, so a
    dead host is not re-pinged on every diagnostics request."""

    def __init__(self, fn: Callable[[], tuple[bool, str | None]], *, ttl: float = PROBE_TTL_SECONDS) -> None:
        self._fn = fn
        self._ttl = ttl
        self._cache: tuple[float, tuple[bool, str | None]] | None = None

    def __call__(self) -> tuple[bool, str | None]:
        now = time.monotonic()
        if self._cache is not None:
            ts, result = self._cache
            if now - ts < self._ttl:
                return result
        result = self._fn()
        self._cache = (now, result)
        return result
