"""Local TheDiscDB snapshot: lookups against the sqlite index.

`thediscdb_index.build_index` builds the index from the GitHub data tarball
and `thediscdb_refresh.refresh` keeps it current.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
