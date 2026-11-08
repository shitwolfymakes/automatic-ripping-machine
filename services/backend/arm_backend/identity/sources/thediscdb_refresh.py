"""Refresh the local TheDiscDB index: download the data tarball, rebuild.

Refresh keeps the previous index on any failure (mirror philosophy: a
third-party outage must never break local operation). `refresh` holds a
process-wide lock so the daily loop and a manual refresh never build
concurrently.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import httpx

from arm_backend.identity.sources.thediscdb_index import build_index
from arm_backend.identity.sources.thediscdb_snapshot import INDEX_FILENAME

TARBALL_URL = "https://codeload.github.com/TheDiscDb/data/tar.gz/refs/heads/main"

# Serialises refreshes within the process (daily loop vs the manual route).
_refresh_lock = asyncio.Lock()


def refresh_running() -> bool:
    """True while a refresh holds the lock; the manual route answers 409."""
    return _refresh_lock.locked()


class RefreshBusy(RuntimeError):
    """A refresh is already running in this process."""


async def refresh(http: httpx.AsyncClient, dir_path: Path) -> int:
    """Download the tarball and rebuild the index. Raises on failure — the
    caller logs and keeps the previous index. Raises RefreshBusy, without
    waiting, while another refresh holds the lock: a manual refresh must not
    hang behind the daily download, and the daily loop has nothing to add
    after a manual one."""
    if _refresh_lock.locked():
        raise RefreshBusy("thediscdb refresh already in progress")
    async with _refresh_lock:
        return await _refresh_locked(http, dir_path)


async def _refresh_locked(http: httpx.AsyncClient, dir_path: Path) -> int:
    dir_path.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        async with http.stream("GET", TARBALL_URL, follow_redirects=True, timeout=300.0) as resp:
            resp.raise_for_status()
            with open(tmp_path, "wb") as out:
                async for chunk in resp.aiter_bytes():
                    out.write(chunk)
        return await asyncio.to_thread(build_index, tmp_path, Path(dir_path) / INDEX_FILENAME)
    finally:
        tmp_path.unlink(missing_ok=True)
