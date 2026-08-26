"""Local TheDiscDB snapshot: GitHub data tarball -> sqlite index -> lookups.

The data repo (github.com/TheDiscDb/data, MIT) lays out
`data/<movie|series|sets>/<Title (Year)>/[metadata.json + <release>/
(release.json + disc*.json)]`. We index every disc*.json by its ContentHash
(uppercased) with its sibling metadata/release JSON attached. `sets/` is
skipped in v1 (deferred; different grouping shape).

Refresh keeps the previous index on any failure (mirror philosophy: a
third-party outage must never break local operation). Build raises an
exception if the tarball contains zero indexable discs (e.g., upstream
layout change), so refresh propagates the error and the previous index
remains untouched. Build is atomic: write `<dest>.new`, then os.replace
over the live file.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import sqlite3
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

TARBALL_URL = "https://codeload.github.com/TheDiscDb/data/tar.gz/refs/heads/main"
INDEX_FILENAME = "index.sqlite"

# <root>/data/(movie|series)/<title-dir>/<release-dir>/disc<NN>.json
_DISC_RE = re.compile(r"^[^/]+/data/(movie|series)/([^/]+)/([^/]+)/disc\d+\.json$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS discs (
    content_hash TEXT PRIMARY KEY,
    global_disc_id TEXT,
    kind TEXT NOT NULL,
    title_slug TEXT NOT NULL,
    release_slug TEXT NOT NULL,
    disc_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    release_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_discs_global ON discs(global_disc_id);
"""


@dataclass(slots=True)
class DiscMatch:
    kind: str
    title_slug: str
    release_slug: str
    disc: dict[str, Any]
    metadata: dict[str, Any]
    release: dict[str, Any]


def build_index(tarball: Path, dest_sqlite: Path) -> int:
    """Parse the data tarball into a fresh sqlite index; atomic replace."""
    # Pass 1: read everything grouped by directory.
    discs: list[tuple[str, str, str, dict[str, Any]]] = []  # (kind, title_dir, release_dir, disc)
    metadata_by_title: dict[str, dict[str, Any]] = {}
    release_by_dir: dict[str, dict[str, Any]] = {}

    def _load(tar: tarfile.TarFile, member: tarfile.TarInfo) -> dict[str, Any] | None:
        fh = tar.extractfile(member)
        if fh is None:
            return None
        try:
            loaded = json.load(fh)
            return loaded if isinstance(loaded, dict) else None
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.debug("thediscdb: skipping malformed %s", member.name)
            return None

    with tarfile.open(tarball, "r:gz") as tar:
        for member in tar:
            if not member.isfile() or not member.name.endswith(".json"):
                continue
            parts = member.name.split("/")
            m = _DISC_RE.match(member.name)
            if m:
                obj = _load(tar, member)
                if obj and obj.get("ContentHash"):
                    discs.append((m.group(1), m.group(2), m.group(3), obj))
            elif len(parts) >= 4 and parts[-1] == "metadata.json" and parts[1] == "data":
                obj = _load(tar, member)
                if obj is not None:
                    metadata_by_title["/".join(parts[2:4])] = obj  # "<kind>/<title-dir>"
            elif parts[-1] == "release.json" and len(parts) >= 5 and parts[1] == "data":
                obj = _load(tar, member)
                if obj is not None:
                    release_by_dir["/".join(parts[2:5])] = obj  # "<kind>/<title>/<release>"

    if not discs:
        raise ValueError("thediscdb: tarball contained no indexable discs — refusing to replace index")

    new_path = dest_sqlite.with_suffix(".sqlite.new")
    new_path.unlink(missing_ok=True)
    dest_sqlite.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(new_path)
    try:
        conn.executescript(_SCHEMA)
        rows = 0
        for kind, title_dir, release_dir, disc in discs:
            meta = metadata_by_title.get(f"{kind}/{title_dir}", {})
            release = release_by_dir.get(f"{kind}/{title_dir}/{release_dir}", {})
            conn.execute(
                "INSERT OR REPLACE INTO discs VALUES (?,?,?,?,?,?,?,?)",
                (
                    str(disc["ContentHash"]).upper(),
                    (str(disc["GlobalDiscId"]).upper() if disc.get("GlobalDiscId") else None),
                    kind,
                    str(meta.get("Slug") or title_dir),
                    str(release.get("Slug") or release_dir),
                    json.dumps(disc),
                    json.dumps(meta),
                    json.dumps(release),
                ),
            )
            rows += 1
        conn.commit()
    finally:
        conn.close()
    os.replace(new_path, dest_sqlite)
    logger.info("thediscdb: index built with %d discs", rows)
    return rows


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
            row = conn.execute(
                "SELECT kind, title_slug, release_slug, disc_json, metadata_json, release_json"
                " FROM discs WHERE content_hash = ?",
                (content_hash.upper(),),
            ).fetchone()
        if row is None:
            return None
        return DiscMatch(
            kind=row[0],
            title_slug=row[1],
            release_slug=row[2],
            disc=json.loads(row[3]),
            metadata=json.loads(row[4]),
            release=json.loads(row[5]),
        )


async def refresh(http: httpx.AsyncClient, dir_path: Path) -> int:
    """Download the tarball and rebuild the index. Raises on failure — the
    caller logs and keeps the previous index."""
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
