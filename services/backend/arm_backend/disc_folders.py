"""Disc folders in the ISO library, for "Rip from folder".

A disc folder is a directory with a `BDMV` (Blu-ray) or `VIDEO_TS` (DVD)
tree at its root: an extracted or backed-up disc MakeMKV reads directly
(`file:<folder>`). They can sit many levels deep (a box set's
`Lord of the Rings/Extended/Fellowship/Disc 1`), so `find` walks the library,
bounded so a huge network share can't hang the picker: it never walks into a
disc folder (its BDMV/STREAM tree is not a library), skips hidden folders,
stops at `max_depth`, and gives up after visiting `max_dirs` folders,
reporting the listing as partial.

Pure (stdlib only); the router runs it in a worker thread.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

logger = logging.getLogger("arm_backend.disc_folders")

DiscType = Literal["bluray", "dvd"]

MAX_DEPTH = 8
MAX_DIRS = 10_000


@dataclass(frozen=True)
class DiscFolder:
    path: str  # relative to the library, "/"-separated
    disc_type: DiscType


def disc_type(folder: Path) -> DiscType | None:
    """The disc type of `folder`: bluray / dvd by its BDMV / VIDEO_TS tree, else None."""
    if (folder / "BDMV").is_dir():
        return "bluray"
    if (folder / "VIDEO_TS").is_dir():
        return "dvd"
    return None


def _subdirs(current: str) -> list[tuple[str, str]]:
    """The visible, non-symlinked subfolders of `current` as (name, path)
    pairs sorted by name; an unreadable folder is logged and has none."""
    try:
        return sorted(
            (e.name, e.path) for e in os.scandir(current) if e.is_dir(follow_symlinks=False) and e.name[:1] != "."
        )
    except OSError as exc:
        logger.warning("disc folders: cannot read %s: %s", current, exc)
        return []


def _child_rel(rel: str, name: str) -> str:
    """A child folder's library-relative path."""
    return str(PurePosixPath(rel) / name) if rel else name


def _walk(root: Path, *, max_depth: int, max_dirs: int) -> tuple[list[DiscFolder], bool]:
    """Walk the library below `root` depth-first, collecting disc folders
    unsorted; True when the `max_dirs` budget ran out."""
    found: list[DiscFolder] = []
    visited = 0
    # (absolute dir, relative path, depth); depth 1 = a direct child of root.
    stack: list[tuple[str, str, int]] = [(str(root), "", 0)]
    while stack:
        current, rel, depth = stack.pop()
        children = _subdirs(current)
        for name, path in children:
            visited += 1
            if visited > max_dirs:
                logger.warning("disc folders: stopped after %d folders under %s", max_dirs, root)
                return found, True
            child_rel = _child_rel(rel, name)
            kind = disc_type(Path(path))
            if kind is not None:
                found.append(DiscFolder(path=child_rel, disc_type=kind))
            elif depth + 1 < max_depth:
                stack.append((path, child_rel, depth + 1))
    return found, False


def find(root: Path, *, max_depth: int = MAX_DEPTH, max_dirs: int = MAX_DIRS) -> tuple[list[DiscFolder], bool]:
    """Every disc folder below `root`, sorted by path, and whether the walk
    stopped early (the `max_dirs` budget ran out)."""
    found, partial = _walk(root, max_depth=max_depth, max_dirs=max_dirs)
    return sorted(found, key=lambda f: f.path), partial
