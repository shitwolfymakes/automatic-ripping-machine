"""Atomic-rename helper and TranscodeTool.NONE passthrough move.

`atomic_output`: the transcoder writes `<final>.arm-inprogress`; on success
the helper `fsync`s that file, renames it to `<final>`, then `fsync`s the
directory so the rename survives a power cut. Same filesystem, so rename is
atomic.
Plex/Jellyfin scanners ignore `.arm-inprogress`, so half-written files are
invisible. On failure (exception, SIGTERM, container kill), the partial file
stays on disk for the Backend startup sweep.

`transcode_none`: used by ISO and data-copy sessions where there's no
transcoding to do. Tries `os.rename` first (atomic, instant on the same
filesystem); falls back to a chunked copy + remove when source and dest are
on different mount points (common when /raw is local and /media is a NAS
share, and always with the stock compose layout's separate /raw and /media
bind mounts). The copy goes to `<final>.arm-inprogress` and is fsynced and
renamed into place only once complete, and it checks an optional `cancel` event between
chunks: a cancelled copy removes its partial file and keeps the source.

Progress: the rename is instant; the copy reports each chunk through an
optional `on_bytes(n)` callback, which the in-process executor turns into
`progress_pct` heartbeats. When the copy fallback fires although source and
destination sit on the same filesystem (two bind mounts of one disk or one
NFS export), it logs a hint that a single parent mount would make the move
an instant rename.

`move_tree`: the folder counterpart of `transcode_none`, for the Blu-ray
decrypted backup. `shutil.move` renames on the same filesystem and copies
the tree then removes the source across filesystems; `move_tree` adds the
refusal to overwrite an existing destination, the same `cancel` check
(a cancelled copy removes the partial tree), and the size of the tree.

`safe_join` / `is_within`: the one containment guard for a path built from
untrusted input (a request, a theme id, a name read off a disc). Both
resolve symlinks before the check, so a link inside the root that points
outward is caught, as are `..` and absolute names.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

logger = logging.getLogger("arm_common.fileops")

INPROGRESS_SUFFIX = ".arm-inprogress"
COPY_CHUNK_BYTES = 8 * 1024 * 1024


def _fsync_file(path: Path) -> None:
    fd = os.open(str(path), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_dir(path: Path) -> None:
    """Make a rename into `path` durable. Best effort: the rename already
    happened, and some network filesystems reject fsync on a directory."""
    try:
        _fsync_file(path)
    except OSError as exc:
        logger.debug("directory fsync failed for %s: %s", path, exc)


class CopyCancelled(Exception):
    """A passthrough copy stopped because its `cancel` event was set.

    Deliberately not an `OSError`: `shutil.copytree` collects a per-file
    `OSError` and keeps going, while this must stop the whole tree at once.
    """


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
    # Data first, then the rename, then the directory entry. A directory
    # fsync before the rename would make nothing about the rename durable.
    _fsync_file(tmp_path)
    os.replace(tmp_path, final_path)
    _fsync_dir(final_path.parent)
    logger.info("atomic rename → %s", final_path)


def _contained(resolved: Path, base: Path, allow_root: bool) -> bool:
    return allow_root if resolved == base else resolved.is_relative_to(base)


def is_within(path: Path, root: Path, *, allow_root: bool = False) -> bool:
    """True when `path` resolves inside `root`; `root` itself only with `allow_root`."""
    return _contained(path.resolve(), root.resolve(), allow_root)


def safe_join(base: Path, relative: str | Path, *, allow_root: bool = False) -> Path:
    """Join `relative` onto `base` and return the resolved path, proven inside `base`.

    Raises ValueError when the result lands outside `base` (`..`, an absolute
    name, an outward symlink), or is `base` itself unless `allow_root`.
    """
    base = base.resolve()
    target = (base / relative).resolve()
    if not _contained(target, base, allow_root):
        raise ValueError(f"path {str(relative)!r} escapes {base}")
    return target


def _copy_file(
    src: Path, dst: Path, cancel: threading.Event | None, on_bytes: Callable[[int], None] | None = None
) -> None:
    """`shutil.copy2`, in chunks, checking `cancel` before each one."""
    with src.open("rb") as fin, dst.open("wb") as fout:
        while True:
            if cancel is not None and cancel.is_set():
                raise CopyCancelled(str(src))
            chunk = fin.read(COPY_CHUNK_BYTES)
            if not chunk:
                break
            fout.write(chunk)
            if on_bytes is not None:
                on_bytes(len(chunk))
    shutil.copystat(src, dst)


def _same_device_hint(src: Path, dst_dir: Path) -> None:
    try:
        same = src.stat().st_dev == dst_dir.stat().st_dev
    except OSError:
        return
    if same:
        logger.info(
            "passthrough is copying %s although source and destination share a filesystem; "
            "mount their common parent once (raw and media as subfolders) to make this an instant rename",
            src.name,
        )


def transcode_none(
    input_path: Path,
    output_path: Path,
    *,
    cancel: threading.Event | None = None,
    on_bytes: Callable[[int], None] | None = None,
) -> int:
    """Move-or-copy `input_path` → `output_path`. Returns the final file size.

    The rename is atomic; the copy fallback writes `<output>.arm-inprogress`
    and renames it into place, so a library scanner never sees a partial
    file. On `CopyCancelled` (or any copy error) the partial file is removed
    and the source is left where it was.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(input_path, output_path)
    except OSError as exc:
        logger.info("passthrough rename failed (%s); falling back to copy+remove", exc)
        _same_device_hint(input_path, output_path.parent)
        tmp_path = output_path.with_name(output_path.name + INPROGRESS_SUFFIX)
        try:
            _copy_file(input_path, tmp_path, cancel, on_bytes)
            _fsync_file(tmp_path)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise
        os.replace(tmp_path, output_path)
        try:
            input_path.unlink()
        except OSError as cleanup_exc:
            logger.warning("post-copy unlink failed: %s (will leave source in /raw)", cleanup_exc)
    _fsync_dir(output_path.parent)
    size = output_path.stat().st_size
    logger.info("passthrough wrote %s (%d bytes)", output_path, size)
    return size


def tree_size(root: Path) -> int:
    """Total size of the regular files under `root`; symlinks are not followed."""
    return sum(p.lstat().st_size for p in root.rglob("*") if p.is_file() and not p.is_symlink())


def move_tree(
    src: Path,
    dst: Path,
    *,
    cancel: threading.Event | None = None,
    on_bytes: Callable[[int], None] | None = None,
) -> int:
    """Move the folder `src` to `dst`. Returns the total size of its files.

    Refuses to touch an existing `dst` (`FileExistsError`, an `OSError`, so a
    caller that fails a task on `OSError` needs nothing extra). Unlike
    `transcode_none`'s rename, it never overwrites: an existing destination is
    always refused, whatever the session's overwrite flag.
    """
    if dst.exists() or dst.is_symlink():
        raise FileExistsError(f"destination already exists: {dst}")
    dst.parent.mkdir(parents=True, exist_ok=True)

    copying = False

    def copy(s: str, d: str) -> None:
        # shutil.move only copies once its rename failed (another filesystem).
        nonlocal copying
        if not copying:
            copying = True
            _same_device_hint(src, dst.parent)
        _copy_file(Path(s), Path(d), cancel, on_bytes)

    try:
        shutil.move(src, dst, copy_function=copy)
    except CopyCancelled:
        # Only a cross-filesystem copy can be cancelled, and it leaves the
        # source in place; drop the partial tree.
        shutil.rmtree(dst, ignore_errors=True)
        raise
    size = tree_size(dst)
    logger.info("passthrough moved folder to %s (%d bytes)", dst, size)
    return size
