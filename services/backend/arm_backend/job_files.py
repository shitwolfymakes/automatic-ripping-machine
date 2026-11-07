"""Remove a deleted job's raw dir and media outputs from disk."""

import logging
import os
import shutil
from collections.abc import Iterable
from pathlib import Path

from arm_common.path_containment import is_within
from arm_common.ulid import is_valid_id

logger = logging.getLogger(__name__)


def _prune_empty_dirs(leaf_parent: Path, root: Path) -> int:
    """rmdir empty ancestors of `leaf_parent` upward, stopping at (and not
    removing) `root`. Returns count of dirs removed. Safe to call with a
    `leaf_parent` outside `root` — returns 0 without touching the filesystem.
    """
    try:
        leaf_parent.relative_to(root)
    except ValueError:
        return 0
    pruned = 0
    current = leaf_parent
    while current != root and current != current.parent:
        try:
            current.rmdir()
        except OSError:
            # Non-empty, missing, or permission denied — stop walking up.
            break
        pruned += 1
        current = current.parent
    return pruned


# What `makemkvcon backup` writes into a disc backup's title folder.
_DISC_BACKUP_PARTS = ("BDMV", "CERTIFICATE")


def _raw_dir_of(job_id: str, raw_root: Path) -> Path:
    """The raw dir for `job_id` under `raw_root`; raises ValueError on a bad id."""
    # `job_id` is interpolated into a path under `raw_root`; reject anything
    # that isn't the expected `job_<ULID>` shape, then join only its
    # `os.path.basename` so a crafted id can never rmtree outside the raw
    # tree (strips any directory component). Routes pin the param too.
    if not is_valid_id("job", job_id):
        raise ValueError(f"invalid job_id: {job_id!r}")
    return raw_root / os.path.basename(job_id)


def _remove_raw_dir(raw_dir: Path, job_id: str) -> int:
    """rmtree `raw_dir` if present. Returns 1 when removed, else 0."""
    if not raw_dir.exists():
        return 0
    try:
        shutil.rmtree(raw_dir)
    except OSError as exc:
        logger.warning("delete: raw rmtree failed job_id=%s path=%s err=%s", job_id, raw_dir, exc)
        return 0
    logger.info("delete: rmtree raw_dir=%s job_id=%s", raw_dir, job_id)
    return 1


def _remove_disc_backup(path: Path, media_root: Path) -> bool:
    """Remove a disc backup folder's structure. True when the output counts as removed."""
    # A disc backup's output is its title folder. Only ever the
    # recorded path itself, and only inside media_root.
    if not is_within(path, media_root):
        logger.warning("delete: refusing folder not strictly inside media_root path=%s", path)
        return False
    # Movie templates also write into "{title} ({year?})/", so the
    # folder can hold a sibling job's files: remove only the backup
    # structure, then the folder only once nothing else is left.
    removed = False
    for part in _DISC_BACKUP_PARTS:
        sub = path / part
        if sub.is_dir() and not sub.is_symlink():
            shutil.rmtree(sub)
            removed = True
    if not removed:
        logger.warning("delete: no disc backup structure to remove in folder path=%s", path)
        return False
    if not any(path.iterdir()):
        path.rmdir()
    return True


def _remove_media_output(path: Path, media_root: Path) -> bool:
    """Remove one media output. True when it counts as removed; an OSError skips it."""
    try:
        if path.is_dir() and not path.is_symlink():
            return _remove_disc_backup(path, media_root)
        if path.is_symlink() and path.is_dir():
            logger.warning("delete: refusing to follow symlinked folder path=%s", path)
            return False
        path.unlink()
    except OSError as exc:
        logger.warning("delete: media delete failed path=%s err=%s", path, exc)
        return False
    return True


def _prune_emptied_parents(parents: set[Path], media_root: Path) -> int:
    """Prune empty dirs above each of `parents`. Returns the count removed."""
    # Deepest-first so a leaf dir is checked for emptiness before its stem.
    dirs_pruned = 0
    for parent in sorted(parents, key=lambda p: len(p.parts), reverse=True):
        dirs_pruned += _prune_empty_dirs(parent, media_root)
    return dirs_pruned


def delete_job_files(
    job_id: str,
    media_outputs: Iterable[Path],
    *,
    raw_root: Path,
    media_root: Path,
) -> dict[str, int]:
    """Delete `raw_root/<job_id>/` and every file in `media_outputs`, then
    prune emptied media parent dirs. A media output that is a folder (the
    Blu-ray decrypted backup) has its BDMV/ and CERTIFICATE/ removed, and is
    itself removed only once empty, and only when it is a real directory
    inside `media_root`.

    Per-file unlink (rather than rmtree of the title dir) because re-rips of
    the same disc land outputs in the same `media/<Title>/` parent — a sibling
    job's bytes are not ours to delete.

    Idempotent: missing raw dir, missing files, and missing parents are all
    expected. Returns counters for the operator log.
    """
    raw_dir = _raw_dir_of(job_id, raw_root)
    raw_removed = _remove_raw_dir(raw_dir, job_id)

    files_removed = 0
    parents_seen: set[Path] = set()
    for path in media_outputs:
        if not path.exists():
            continue
        if _remove_media_output(path, media_root):
            files_removed += 1
            parents_seen.add(path.parent)

    dirs_pruned = _prune_emptied_parents(parents_seen, media_root)

    return {
        "raw_dir_removed": raw_removed,
        "media_files_removed": files_removed,
        "media_dirs_pruned": dirs_pruned,
    }
