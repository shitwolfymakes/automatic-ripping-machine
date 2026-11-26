"""Build the local TheDiscDB index: GitHub data tarball -> sqlite.

The data repo (github.com/TheDiscDb/data, MIT) lays out
`data/<movie|series|sets>/<Title (Year)>/[metadata.json + <release>/
(release.json + disc*.json)]`. We index every disc*.json by its ContentHash
(uppercased) with its sibling metadata/release JSON attached. `sets/` is
skipped in v1 (deferred; different grouping shape).

Build raises an exception if the tarball contains zero indexable discs
(e.g., upstream layout change), so refresh propagates the error and the
previous index remains untouched. Build is atomic: write a uniquely named
temp file next to the live index, then os.replace over it.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import tarfile
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

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
    release_json TEXT NOT NULL,
    release_seasons TEXT
);
CREATE INDEX IF NOT EXISTS idx_discs_global ON discs(global_disc_id);
"""


def _episode_seasons(disc: dict[str, Any]) -> set[int]:
    seasons: set[int] = set()
    for entry in disc.get("Titles") or []:
        item = entry.get("Item") if isinstance(entry, dict) else None
        if not isinstance(item, dict) or item.get("Type") != "Episode":
            continue
        try:
            seasons.add(int(item["Season"]))
        except KeyError, TypeError, ValueError:
            continue
    return seasons


def _load_json_member(tar: tarfile.TarFile, member: tarfile.TarInfo) -> dict[str, Any] | None:
    """A member's JSON object, or None when it can't be extracted, isn't
    valid JSON or isn't an object."""
    fh = tar.extractfile(member)
    if fh is None:
        return None
    try:
        loaded = json.load(fh)
        return loaded if isinstance(loaded, dict) else None
    except json.JSONDecodeError, UnicodeDecodeError:
        logger.debug("thediscdb: skipping malformed %s", member.name)
        return None


def _metadata_key(parts: list[str]) -> str | None:
    """The "<kind>/<title-dir>" key of a title's metadata.json path, or None
    for any other path."""
    return "/".join(parts[2:4]) if len(parts) >= 4 and parts[-1] == "metadata.json" and parts[1] == "data" else None


def _release_key(parts: list[str]) -> str | None:
    """The "<kind>/<title>/<release>" key of a release's release.json path,
    or None for any other path."""
    return "/".join(parts[2:5]) if parts[-1] == "release.json" and len(parts) >= 5 and parts[1] == "data" else None


def _add_disc(discs: list[tuple[str, str, str, dict[str, Any]]], m: re.Match[str], obj: dict[str, Any] | None) -> None:
    """Record a loaded disc JSON that has a ContentHash under its (kind,
    title_dir, release_dir)."""
    if obj and obj.get("ContentHash"):
        discs.append((m.group(1), m.group(2), m.group(3), obj))


def _add_json(by_key: dict[str, dict[str, Any]], key: str, obj: dict[str, Any] | None) -> None:
    """Record a loaded JSON object under `key`."""
    if obj is not None:
        by_key[key] = obj


def _read_tarball(
    tarball: Path,
) -> tuple[list[tuple[str, str, str, dict[str, Any]]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    """Every disc, title-metadata and release JSON in the data tarball,
    grouped by directory: (discs as (kind, title_dir, release_dir, disc),
    metadata by "<kind>/<title-dir>", release by "<kind>/<title>/<release>")."""
    # Pass 1: read everything grouped by directory.
    discs: list[tuple[str, str, str, dict[str, Any]]] = []  # (kind, title_dir, release_dir, disc)
    metadata_by_title: dict[str, dict[str, Any]] = {}
    release_by_dir: dict[str, dict[str, Any]] = {}

    with tarfile.open(tarball, "r:gz") as tar:
        for member in tar:
            if not member.isfile() or not member.name.endswith(".json"):
                continue
            parts = member.name.split("/")
            if m := _DISC_RE.match(member.name):
                _add_disc(discs, m, _load_json_member(tar, member))
            elif (key := _metadata_key(parts)) is not None:
                _add_json(metadata_by_title, key, _load_json_member(tar, member))  # "<kind>/<title-dir>"
            elif (key := _release_key(parts)) is not None:
                _add_json(release_by_dir, key, _load_json_member(tar, member))  # "<kind>/<title>/<release>"
    return discs, metadata_by_title, release_by_dir


def _replace_index_atomically(
    dest_sqlite: Path,
    discs: list[tuple[str, str, str, dict[str, Any]]],
    metadata_by_title: dict[str, dict[str, Any]],
    release_by_dir: dict[str, dict[str, Any]],
) -> int:
    """Write the index to a uniquely named temp file beside `dest_sqlite` and
    os.replace it over the live one; the temp file is removed on any failure.
    Returns the row count."""
    dest_sqlite.parent.mkdir(parents=True, exist_ok=True)
    # Unique name per build: a fixed `<dest>.new` let two overlapping builds
    # unlink each other's open database.
    fd, tmp_name = tempfile.mkstemp(dir=dest_sqlite.parent, prefix=f"{dest_sqlite.name}.", suffix=".new")
    os.close(fd)
    new_path = Path(tmp_name)
    try:
        rows = _write_index(new_path, discs, metadata_by_title, release_by_dir)
        os.replace(new_path, dest_sqlite)
    except BaseException:
        new_path.unlink(missing_ok=True)
        raise
    return rows


def build_index(tarball: Path, dest_sqlite: Path) -> int:
    """Parse the data tarball into a fresh sqlite index; atomic replace."""
    discs, metadata_by_title, release_by_dir = _read_tarball(tarball)
    if not discs:
        raise ValueError("thediscdb: tarball contained no indexable discs — refusing to replace index")
    rows = _replace_index_atomically(dest_sqlite, discs, metadata_by_title, release_by_dir)
    logger.info("thediscdb: index built with %d discs", rows)
    return rows


def _write_index(
    new_path: Path,
    discs: list[tuple[str, str, str, dict[str, Any]]],
    metadata_by_title: dict[str, dict[str, Any]],
    release_by_dir: dict[str, dict[str, Any]],
) -> int:
    conn = sqlite3.connect(new_path)
    try:
        conn.executescript(_SCHEMA)
        rows = 0
        seasons_by_release: dict[tuple[str, str, str], set[int]] = {}
        for kind, title_dir, release_dir, disc in discs:
            seasons_by_release.setdefault((kind, title_dir, release_dir), set()).update(_episode_seasons(disc))
        for kind, title_dir, release_dir, disc in discs:
            meta = metadata_by_title.get(f"{kind}/{title_dir}", {})
            release = release_by_dir.get(f"{kind}/{title_dir}/{release_dir}", {})
            conn.execute(
                "INSERT OR REPLACE INTO discs VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    str(disc["ContentHash"]).upper(),
                    (str(disc["GlobalDiscId"]).upper() if disc.get("GlobalDiscId") else None),
                    kind,
                    str(meta.get("Slug") or title_dir),
                    str(release.get("Slug") or release_dir),
                    json.dumps(disc),
                    json.dumps(meta),
                    json.dumps(release),
                    json.dumps(sorted(seasons))
                    if (seasons := seasons_by_release[(kind, title_dir, release_dir)])
                    else None,
                ),
            )
            rows += 1
        conn.commit()
    finally:
        conn.close()
    return rows
