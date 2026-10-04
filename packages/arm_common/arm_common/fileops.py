"""Atomic-rename helper and TranscodeTool.NONE passthrough move.

`atomic_output`: the transcoder writes `<final>.arm-inprogress`, `fsync`s,
then renames to `<final>` on success. Same filesystem, so rename is atomic.
Plex/Jellyfin scanners ignore `.arm-inprogress`, so half-written files are
invisible. On failure (exception, SIGTERM, container kill), the partial file
stays on disk for the Backend startup sweep.

`transcode_none`: used by ISO and data-copy sessions where there's no
transcoding to do. Tries `os.rename` first (atomic, instant on the same
filesystem); falls back to `shutil.copy2` + remove when source and dest are
on different mount points (common when /raw is local and /media is a NAS
share).

No live progress — the operation is either instantaneous (rename) or
limited by disk throughput (copy). The caller may still report a single
100% heartbeat after success for UI consistency.

`move_tree`: the folder counterpart of `transcode_none`, for the Blu-ray
decrypted backup. `shutil.move` renames on the same filesystem and copies
the tree then removes the source across filesystems; `move_tree` adds only
the refusal to overwrite an existing destination and the size of the tree.
"""

from __future__ import annotations

import logging
import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

logger = logging.getLogger("arm_common.fileops")

INPROGRESS_SUFFIX = ".arm-inprogress"


@contextmanager
def atomic_output(final_path: Path) -> Iterator[Path]:
    """Yield a temp `<final>.arm-inprogress` path; rename on clean exit.

    On exception inside the `with` body the temp file is left in place
    intentionally — the Backend startup sweep cleans orphans whose
    `transcode_tasks` row is not `in_progress`. Re-raising lets the
    caller mark the task `failed` via the REST API.
    """
    tmp_path = final_path.with_name(final_path.name + INPROGRESS_SUFFIX)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        yield tmp_path
    except Exception:
        logger.warning("atomic_output failed; leaving %s for sweeper", tmp_path)
        raise
    if not tmp_path.exists():
        raise FileNotFoundError(f"transcoder did not write expected output: {tmp_path}")
    # Best-effort fsync of the directory so the rename is durable on crash.
    fd = os.open(str(final_path.parent), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp_path, final_path)
    logger.info("atomic rename → %s", final_path)


def transcode_none(input_path: Path, output_path: Path) -> int:
    """Move-or-copy `input_path` → `output_path`. Returns the final file size.

    Caller is responsible for using `atomic_output` if the destination
    needs the `.arm-inprogress` rename dance — but for passthrough the
    operation is itself atomic, so the caller can just write directly to
    the final path.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(input_path, output_path)
    except OSError as exc:
        logger.info("passthrough rename failed (%s); falling back to copy+remove", exc)
        shutil.copy2(input_path, output_path)
        try:
            input_path.unlink()
        except OSError as cleanup_exc:
            logger.warning("post-copy unlink failed: %s (will leave source in /raw)", cleanup_exc)
    size = output_path.stat().st_size
    logger.info("passthrough wrote %s (%d bytes)", output_path, size)
    return size


def tree_size(root: Path) -> int:
    """Total size of the regular files under `root`; symlinks are not followed."""
    return sum(p.lstat().st_size for p in root.rglob("*") if p.is_file() and not p.is_symlink())


def move_tree(src: Path, dst: Path) -> int:
    """Move the folder `src` to `dst`. Returns the total size of its files.

    Refuses to touch an existing `dst` (`FileExistsError`, an `OSError`, so a
    caller that fails a task on `OSError` needs nothing extra). Unlike
    `transcode_none`'s rename, it never overwrites: an existing destination is
    always refused, whatever the session's overwrite flag.
    """
    if dst.exists() or dst.is_symlink():
        raise FileExistsError(f"destination already exists: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(src, dst)
    size = tree_size(dst)
    logger.info("passthrough moved folder to %s (%d bytes)", dst, size)
    return size
