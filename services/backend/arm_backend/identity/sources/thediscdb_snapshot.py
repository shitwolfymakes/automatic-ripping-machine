"""Local TheDiscDB snapshot: sqlite index -> lookups, and its refresh.

`thediscdb_index.build_index` builds the index from the GitHub data tarball.

Refresh keeps the previous index on any failure (mirror philosophy: a
third-party outage must never break local operation). `refresh` holds a
process-wide lock so the daily loop and a manual refresh never build
concurrently.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from arm_backend.identity.sources.thediscdb_index import build_index

TARBALL_URL = "https://codeload.github.com/TheDiscDb/data/tar.gz/refs/heads/main"
INDEX_FILENAME = "index.sqlite"


@dataclass(slots=True)
class DiscMatch:
    kind: str
    title_slug: str
    release_slug: str
    disc: dict[str, Any]
    metadata: dict[str, Any]
    release: dict[str, Any]
    # Seasons covered by the whole release (sorted); None when it has no Episode titles.
    release_seasons: list[int] | None = None


class SnapshotStore:
    """Read-side handle. sqlite3 opens are per-call (cheap, and immune to the
    os.replace swap under a running process)."""

    def __init__(self, dir_path: Path) -> None:
        self._path = Path(dir_path) / INDEX_FILENAME

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        return self._path.exists()

    def count(self) -> int:
        if not self.exists():
            return 0
        with sqlite3.connect(f"file:{self._path}?mode=ro", uri=True) as conn:
            return int(conn.execute("SELECT COUNT(*) FROM discs").fetchone()[0])

    def lookup(self, content_hash: str) -> DiscMatch | None:
        if not content_hash or not self.exists():
            return None
        with sqlite3.connect(f"file:{self._path}?mode=ro", uri=True) as conn:
            select = "SELECT kind, title_slug, release_slug, disc_json, metadata_json, release_json{} FROM discs WHERE content_hash = ?"
            try:
                row = conn.execute(select.format(", release_seasons"), (content_hash.upper(),)).fetchone()
            except sqlite3.OperationalError:  # index built before release_seasons existed
                row = conn.execute(select.format(""), (content_hash.upper(),)).fetchone()
        if row is None:
            return None
        return DiscMatch(
            kind=row[0],
            title_slug=row[1],
            release_slug=row[2],
            disc=json.loads(row[3]),
            metadata=json.loads(row[4]),
            release=json.loads(row[5]),
            release_seasons=json.loads(row[6]) if len(row) > 6 and row[6] else None,
        )


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
