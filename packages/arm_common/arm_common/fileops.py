"""Atomic output, the resumable copier, and the TranscodeTool.NONE passthrough move.

`atomic_output`: the transcoder writes `<final>.arm-inprogress`; on success
the helper `fsync`s that file, renames it to `<final>`, then `fsync`s the
directory so the rename survives a power cut. Same filesystem, so rename is
atomic. Plex/Jellyfin skip a file whose extension they do not recognise, so a
half-written `.arm-inprogress` file is invisible to them. On failure (exception, SIGTERM, container kill), the
partial file stays on disk for the Backend startup sweep.

`copy_file_resumable`: the one copy primitive. It copies in chunks through
`<dst>.arm-inprogress` and (when the caller passes `on_checkpoint`) fsyncs
and reports a durable checkpoint every `CHECKPOINT_BYTES` or
`CHECKPOINT_SECONDS`. A later call with `resume_from` truncates the temp file
to the checkpoint and carries on from that offset of the source. A source
whose size or mtime changed, or that did not yield exactly its stamped size
(`SourceChanged`), is never placed. The finished file is fsynced, renamed
into place, and the directory fsynced.

`place_by_link` and `place_by_rename`: placement that copies and reads no
bytes. They hard-link or rename the source into place; `LinkUnavailable`
tells the caller to fall back to a copy.

`transcode_none`: used by ISO and data-copy sessions where there's no
transcoding to do. Links the source into place, falls back to a rename when
the link is refused for a reason other than EXDEV, and to a copy plus source
removal across mount points (common when /raw is local and /media is a NAS
share, and always with the stock compose layout's separate bind mounts). It
returns the size of the placed file. When the copy happens
although source and destination sit on the same filesystem, it logs a hint
that a single parent mount would make the move instant.

`move_tree`: the folder counterpart of `transcode_none`, for the Blu-ray
decrypted backup. It refuses an existing destination, then tries
`os.rename`; across filesystems it copies the tree into a staging folder
`<dst>.arm-inprogress` with the copier (each file fsynced before it lands), every directory fsynced
once the copy is done, renames the staging folder to `<dst>`, fsyncs the
parent, and only then removes the source. A copy error, a cancel (checked
between chunks) or a crash leaves only the staging folder and the source;
the next attempt replaces a leftover staging folder, and the Backend startup
sweep removes an orphaned one. Unlike a single `.arm-inprogress` file, the
staging folder holds ordinary `BDMV/STREAM/*.m2ts` files, so a library
scanner may index the partial copy while it runs or until a leftover is
removed; `<dst>` itself only ever appears complete. Returns the total size
of the tree's files.
"""

from __future__ import annotations

import errno
import logging
import os
import shutil
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator

logger = logging.getLogger("arm_common.fileops")

INPROGRESS_SUFFIX = ".arm-inprogress"
COPY_CHUNK_BYTES = 8 * 1024 * 1024
CHECKPOINT_BYTES = 1024**3  # fsync + checkpoint at least every 1 GiB ...
CHECKPOINT_SECONDS = 30.0  # ... or every 30 s, whichever comes first
MTIME_TOLERANCE_SECONDS = 2.0  # SMB/FAT mtime granularity


def inprogress_path(final: Path) -> Path:
    """`<final>.arm-inprogress`, the temp name every writer uses."""
    return final.with_name(final.name + INPROGRESS_SUFFIX)


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


def _make_parent_dirs(folder: Path) -> None:
    """`folder.mkdir(parents=True, exist_ok=True)`, naming a dangling symlink on the way.

    Docker mounts only the media folder, so a symlink inside it with an
    absolute target (`/media/Movies -> /mnt/nas/movies`) is valid on the host
    but dangles in the container, and `mkdir` on it fails with a bare
    "[Errno 17] File exists" that points at the wrong problem.
    """
    for path in (folder, *folder.parents):
        if path.is_symlink() and not path.exists():
            raise OSError(
                f"{path} is a symlink to {os.readlink(path)}, which does not exist inside the container; "
                "mount the target or use a relative link"
            )
    folder.mkdir(parents=True, exist_ok=True)


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
    tmp_path = inprogress_path(final_path)
    _make_parent_dirs(final_path.parent)
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
    logger.debug("atomic rename → %s", final_path)


@dataclass(frozen=True)
class SourceStamp:
    """Size and mtime of a source file, to tell whether it changed under a copy."""

    size: int
    mtime_ns: int

    @classmethod
    def of(cls, path: Path) -> SourceStamp:
        st = path.stat()
        return cls(size=st.st_size, mtime_ns=st.st_mtime_ns)


@dataclass(frozen=True)
class PlaceResult:
    size: int
    linked: bool  # True when no bytes were copied (hard link or rename)


class SourceChanged(OSError):
    """The source's size or mtime differs from the expected stamp, or changed during the copy."""


class LinkUnavailable(Exception):
    """`os.link` / `os.rename` can't place this file (EXDEV across mounts, EPERM from
    `fs.protected_hardlinks`, ENOTSUP...). `.errno` holds the cause.

    Not an `OSError` on purpose: callers fall back to a copy, they don't fail the task.
    """

    def __init__(self, errno_: int | None, message: str) -> None:
        super().__init__(message)
        self.errno = errno_


def _raise_if_cancelled(cancel: threading.Event | None, src: object) -> None:
    if cancel is not None and cancel.is_set():
        raise CopyCancelled(str(src))


def is_placed(stamp: SourceStamp, dst: Path) -> bool:
    """True when `dst` is a finished placement of the source `stamp` describes.

    `dst` exists, its temp file does not, its size equals the stamp's and its mtime is within
    `MTIME_TOLERANCE_SECONDS` of the stamp's (the copier `copystat`s the source onto the temp file
    before the rename). A false negative only costs a re-copy.
    """
    try:
        st = dst.stat()
    except OSError:
        return False
    if inprogress_path(dst).exists() or st.st_size != stamp.size:
        return False
    return abs(st.st_mtime_ns - stamp.mtime_ns) <= MTIME_TOLERANCE_SECONDS * 1e9


def _check_expected(src: Path, expect: SourceStamp | None, tmp: Path) -> SourceStamp:
    """Stamp `src`; when it differs from `expect`, drop the temp file (it belongs to the old source) and raise."""
    stamp = SourceStamp.of(src)
    if expect is not None and stamp != expect:
        tmp.unlink(missing_ok=True)
        raise SourceChanged(f"source changed since it was stamped: {src}")
    return stamp


def _can_resume(tmp: Path, resume_from: int) -> bool:
    try:
        return tmp.stat().st_size >= resume_from
    except OSError:
        return False


def _open_temp(tmp: Path, resume_from: int, on_checkpoint: Callable[[int], None] | None) -> tuple[BinaryIO, int]:
    """Open the temp file to resume at `resume_from`, or fresh; returns it and the offset it starts at."""
    if resume_from > 0 and _can_resume(tmp, resume_from):
        fout = tmp.open("r+b")
        fout.truncate(resume_from)
        fout.seek(resume_from)
        return fout, resume_from
    if resume_from > 0 and on_checkpoint is not None:
        on_checkpoint(0)  # the caller's durable count drops to what is really on disk
    return tmp.open("wb"), 0


class _CheckpointClock:
    """When a checkpoint is due: enough bytes since the last one, or enough seconds."""

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._offset = 0
        self._at = clock()

    def due(self, offset: int) -> bool:
        return offset - self._offset >= CHECKPOINT_BYTES or self._clock() - self._at >= CHECKPOINT_SECONDS

    def mark(self, offset: int) -> None:
        self._offset = offset
        self._at = self._clock()


def _checkpoint(fout: BinaryIO, offset: int, on_checkpoint: Callable[[int], None]) -> None:
    """Make the bytes written so far durable, then report them."""
    fout.flush()
    os.fsync(fout.fileno())
    on_checkpoint(offset)


def _copy_chunks(
    fin: BinaryIO,
    fout: BinaryIO,
    start: int,
    cancel: threading.Event | None,
    on_bytes: Callable[[int], None] | None,
    ckpt: tuple[_CheckpointClock, Callable[[int], None]] | None,
) -> int:
    """The read-write loop; returns the final offset. Checkpoints when `ckpt` is given."""
    offset = start
    while True:
        # Cancelled: the temp file stays and nothing is fsynced; the caller's last checkpoint is
        # the durable truth (an fsync here could take minutes on a slow NAS).
        _raise_if_cancelled(cancel, fin.name)
        chunk = fin.read(COPY_CHUNK_BYTES)
        if not chunk:
            return offset
        fout.write(chunk)
        offset += len(chunk)
        if on_bytes is not None:
            on_bytes(len(chunk))
        if ckpt is not None and ckpt[0].due(offset):
            _checkpoint(fout, offset, ckpt[1])
            ckpt[0].mark(offset)


def _verify_source_unchanged(src: Path, stamp: SourceStamp, offset: int, tmp: Path) -> None:
    """After reading the source: its size and stamp must still be what the copy started from."""
    if offset != stamp.size or SourceStamp.of(src) != stamp:
        tmp.unlink(missing_ok=True)
        raise SourceChanged(f"source changed during the copy: {src}")


def _finalise(src: Path, fout: BinaryIO, tmp: Path, dst: Path) -> None:
    """Carry the source's times over, make the bytes durable, rename into place, fsync the directory."""
    fout.flush()
    shutil.copystat(src, tmp)
    os.fsync(fout.fileno())
    fout.close()
    os.replace(tmp, dst)
    _fsync_dir(dst.parent)


def copy_file_resumable(
    src: Path,
    dst: Path,
    *,
    resume_from: int = 0,
    expect: SourceStamp | None = None,
    cancel: threading.Event | None = None,
    on_bytes: Callable[[int], None] | None = None,
    on_checkpoint: Callable[[int], None] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> PlaceResult:
    """Copy `src` to `dst` through `<dst>.arm-inprogress`.

    With `on_checkpoint`, the temp file is fsynced and the durable offset reported every
    `CHECKPOINT_BYTES` or `CHECKPOINT_SECONDS`; `resume_from` (a reported offset) continues such a
    copy. Raises `SourceChanged` when the source is not the one `expect` describes or changes under
    the copy, and `CopyCancelled` on `cancel` (the temp file stays). Any other `OSError` propagates
    and leaves the temp file for a resume.
    """
    tmp = inprogress_path(dst)
    stamp = _check_expected(src, expect, tmp)
    _make_parent_dirs(dst.parent)
    fout, start = _open_temp(tmp, resume_from, on_checkpoint)
    ckpt = (_CheckpointClock(clock), on_checkpoint) if on_checkpoint is not None else None
    with fout, src.open("rb") as fin:
        fin.seek(start)
        if start and on_bytes is not None:
            on_bytes(start)
        offset = _copy_chunks(fin, fout, start, cancel, on_bytes, ckpt)
        _verify_source_unchanged(src, stamp, offset, tmp)
        _finalise(src, fout, tmp, dst)
    return PlaceResult(size=offset, linked=False)


def _link_temp(src: Path, tmp: Path) -> None:
    try:
        os.link(src, tmp)
    except OSError as exc:
        raise LinkUnavailable(exc.errno, str(exc)) from exc


def _commit_link(tmp: Path, dst: Path) -> None:
    os.replace(tmp, dst)
    _fsync_dir(dst.parent)


def _remove_source(src: Path) -> None:
    src.unlink()
    _fsync_dir(src.parent)


def place_by_link(
    src: Path,
    dst: Path,
    *,
    keep_source: bool,
    expect: SourceStamp | None = None,
) -> PlaceResult:
    """Hard-link `src` to `dst` (through the temp name); copies and reads no bytes.

    Raises `LinkUnavailable` when the link is refused (the caller falls back to a copy), and
    `SourceChanged` when the source changed meanwhile (a re-rip writes a new inode, so the link would
    point at the old bytes). Unless `keep_source`, the source name is removed afterwards.
    """
    tmp = inprogress_path(dst)
    stamp = _check_expected(src, expect, tmp)
    tmp.unlink(missing_ok=True)
    _make_parent_dirs(dst.parent)
    _link_temp(src, tmp)
    _verify_source_unchanged(src, stamp, stamp.size, tmp)
    _commit_link(tmp, dst)
    if not keep_source:
        _remove_source(src)
    return PlaceResult(size=stamp.size, linked=True)


def place_by_rename(
    src: Path,
    dst: Path,
    *,
    expect: SourceStamp | None = None,
) -> PlaceResult:
    """Rename `src` to `dst`; copies and reads no bytes.

    For when `os.link` is refused (EPERM from `fs.protected_hardlinks`) but a rename on the same
    mount works. Raises `LinkUnavailable` when the rename fails too.
    """
    tmp = inprogress_path(dst)
    stamp = _check_expected(src, expect, tmp)
    _make_parent_dirs(dst.parent)
    try:
        os.rename(src, dst)
    except OSError as exc:
        raise LinkUnavailable(exc.errno, str(exc)) from exc
    _fsync_dir(dst.parent)
    return PlaceResult(size=stamp.size, linked=True)


_shared_filesystem_advised = False


def _same_device_hint(src: Path, dst_dir: Path) -> None:
    try:
        same = src.stat().st_dev == dst_dir.stat().st_dev
    except OSError:
        return
    if same:
        _log_shared_filesystem_hint(src.name)


def _log_shared_filesystem_hint(name: str) -> None:
    """The operator advice at INFO once per process; repeats for later files are DEBUG."""
    global _shared_filesystem_advised
    level = logging.DEBUG if _shared_filesystem_advised else logging.INFO
    _shared_filesystem_advised = True
    logger.log(
        level,
        "passthrough is copying %s although source and destination share a filesystem; "
        "mount their common parent once (raw and media as subfolders) to make this an instant rename",
        name,
    )


def _copy_then_remove(
    src: Path,
    dst: Path,
    cancel: threading.Event | None,
    on_bytes: Callable[[int], None] | None,
) -> PlaceResult:
    """Copy through `.arm-inprogress`, then remove the source (best effort). A failed copy leaves no partial."""
    _same_device_hint(src, dst.parent)
    try:
        result = copy_file_resumable(src, dst, cancel=cancel, on_bytes=on_bytes)
    except BaseException:
        inprogress_path(dst).unlink(missing_ok=True)
        raise
    try:
        src.unlink()
    except OSError as cleanup_exc:
        logger.warning("post-copy unlink failed: %s (will leave source in /raw)", cleanup_exc)
    return result


def _place_without_link(
    src: Path,
    dst: Path,
    link_errno: int | None,
    cancel: threading.Event | None,
    on_bytes: Callable[[int], None] | None,
) -> PlaceResult:
    """Placement after a refused link: a rename unless the link failed across devices, else a copy."""
    if link_errno != errno.EXDEV:
        try:
            return place_by_rename(src, dst)
        except LinkUnavailable as exc:
            logger.info("passthrough rename failed (%s); falling back to copy+remove", exc)
    return _copy_then_remove(src, dst, cancel, on_bytes)


def transcode_none(
    input_path: Path,
    output_path: Path,
    *,
    cancel: threading.Event | None = None,
    on_bytes: Callable[[int], None] | None = None,
) -> PlaceResult:
    """Move-or-copy `input_path` → `output_path`. Returns the size of the placed file.

    Hard-links first (no bytes copied or read); a rename when the link is
    refused for a reason other than EXDEV; otherwise a copy through `<output>.arm-inprogress`, so a
    library scanner never sees a partial file. On `CopyCancelled` (or any copy error) the partial
    file is removed and the source is left where it was.
    """
    try:
        result = place_by_link(input_path, output_path, keep_source=False)
    except LinkUnavailable as exc:
        logger.info("passthrough link failed (%s); falling back", exc)
        result = _place_without_link(input_path, output_path, exc.errno, cancel, on_bytes)
    logger.debug("passthrough wrote %s (%d bytes)", output_path, result.size)
    return result


def _fsync_tree_dirs(root: Path) -> None:
    """fsync every directory of a copied tree, deepest first, then the root itself."""
    for d in sorted((p for p in root.rglob("*") if p.is_dir() and not p.is_symlink()), reverse=True):
        _fsync_dir(d)
    _fsync_dir(root)


def tree_size(root: Path) -> int:
    """Total size of the regular files under `root`; symlinks are not followed."""
    return sum(p.lstat().st_size for p in root.rglob("*") if p.is_file() and not p.is_symlink())


def _copy_tree_across_filesystems(
    src: Path, dst: Path, cancel: threading.Event | None, on_bytes: Callable[[int], None] | None
) -> None:
    """Copy the folder `src` to `dst` through `<dst>.arm-inprogress`, then remove `src`.

    A copy error (ENOSPC, EIO, one unreadable file), a cancel or a crash
    leaves only the staging folder, never a partial `dst` that the
    destination-exists guard would refuse on every retry; the source is kept.
    A staging folder already there is a copy that died part way and is
    replaced. The source goes only once the backup is durable in place, and a
    source that cannot be removed is left in /raw rather than ever taking the
    only complete copy with it.
    """
    staging = inprogress_path(dst)
    if staging.is_symlink() or staging.is_file():
        staging.unlink()
    elif staging.exists():
        shutil.rmtree(staging)
    _same_device_hint(src, dst.parent)

    def copy(s: str, d: str) -> None:
        # The copier fsyncs each file before it lands.
        copy_file_resumable(Path(s), Path(d), cancel=cancel, on_bytes=on_bytes)

    try:
        shutil.copytree(src, staging, symlinks=True, copy_function=copy)
        _fsync_tree_dirs(staging)
        os.replace(staging, dst)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    _fsync_dir(dst.parent)
    try:
        shutil.rmtree(src)
    except OSError as exc:
        logger.warning(
            "passthrough folder copied to %s, but removing %s failed (%s); leaving it in /raw", dst, src, exc
        )


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

    A rename when it can; across filesystems, a copy staged at
    `<dst>.arm-inprogress` (see `_copy_tree_across_filesystems`), so `dst`
    only ever appears complete.
    """
    if dst.exists() or dst.is_symlink():
        raise FileExistsError(f"destination already exists: {dst}")
    _make_parent_dirs(dst.parent)
    try:
        os.rename(src, dst)
    except OSError as exc:
        logger.info("passthrough folder rename failed (%s); copying across filesystems", exc)
        _copy_tree_across_filesystems(src, dst, cancel, on_bytes)
    size = tree_size(dst)
    logger.debug("passthrough moved folder to %s (%d bytes)", dst, size)
    return size
