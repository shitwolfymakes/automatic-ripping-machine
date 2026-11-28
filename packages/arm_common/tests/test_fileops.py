"""Atomic-rename context manager, resumable copier and TranscodeTool.NONE passthrough move."""

from __future__ import annotations

import errno
import logging
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import threading

from arm_common import fileops
from arm_common.fileops import (
    INPROGRESS_SUFFIX,
    CopyCancelled,
    LinkUnavailable,
    PlaceResult,
    SourceChanged,
    SourceStamp,
    atomic_output,
    copy_file_resumable,
    inprogress_path,
    is_placed,
    move_tree,
    place_by_link,
    place_by_rename,
    transcode_none,
    tree_size,
)


def test_atomic_output_renames_on_clean_exit(tmp_path: Path) -> None:
    final = tmp_path / "movies" / "Iron Man.mkv"
    with atomic_output(final) as tmp:
        assert tmp.name.endswith(INPROGRESS_SUFFIX)
        tmp.write_bytes(b"video content")
    assert final.exists()
    assert final.read_bytes() == b"video content"
    assert not (tmp_path / "movies" / ("Iron Man.mkv" + INPROGRESS_SUFFIX)).exists()


def test_atomic_output_leaves_partial_on_exception(tmp_path: Path) -> None:
    final = tmp_path / "movies" / "X.mkv"
    with pytest.raises(RuntimeError):
        with atomic_output(final) as tmp:
            tmp.write_bytes(b"half")
            raise RuntimeError("encoder died")
    assert not final.exists()
    # The partial is left for the Backend startup sweep — this is by design.
    assert (tmp_path / "movies" / ("X.mkv" + INPROGRESS_SUFFIX)).exists()


def test_atomic_output_raises_when_encoder_wrote_nothing(tmp_path: Path) -> None:
    final = tmp_path / "Y.mkv"
    with pytest.raises(FileNotFoundError):
        with atomic_output(final):
            pass


def test_atomic_output_overwrites_existing_final(tmp_path: Path) -> None:
    final = tmp_path / "Z.mkv"
    final.write_bytes(b"old version")
    with atomic_output(final) as tmp:
        tmp.write_bytes(b"new version")
    assert final.read_bytes() == b"new version"


def _backup_tree(root: Path) -> Path:
    (root / "BDMV" / "STREAM").mkdir(parents=True)
    (root / "BDMV" / "index.bdmv").write_bytes(b"i" * 10)
    (root / "BDMV" / "STREAM" / "00000.m2ts").write_bytes(b"v" * 100)
    (root / "CERTIFICATE").mkdir()
    (root / "CERTIFICATE" / "id.bdmv").write_bytes(b"c" * 5)
    return root


def test_tree_size_sums_every_file(tmp_path: Path) -> None:
    assert tree_size(_backup_tree(tmp_path / "backup")) == 115


def test_tree_size_does_not_follow_symlinks(tmp_path: Path) -> None:
    root = _backup_tree(tmp_path / "backup")
    (tmp_path / "big").write_bytes(b"x" * 1000)
    (root / "link").symlink_to(tmp_path / "big")
    assert tree_size(root) == 115


def test_move_tree_moves_the_folder_and_returns_its_size(tmp_path: Path) -> None:
    src = _backup_tree(tmp_path / "raw" / "job" / "backup")
    dst = tmp_path / "media" / "Iron Man (2008)"
    assert move_tree(src, dst) == 115
    assert (dst / "BDMV" / "STREAM" / "00000.m2ts").read_bytes() == b"v" * 100
    assert not src.exists()


def test_move_tree_refuses_an_existing_destination_and_leaves_it(tmp_path: Path) -> None:
    src = _backup_tree(tmp_path / "raw" / "backup")
    dst = tmp_path / "media" / "Iron Man (2008)"
    dst.mkdir(parents=True)
    (dst / "keep.txt").write_text("mine")
    with pytest.raises(FileExistsError):
        move_tree(src, dst)
    assert (dst / "keep.txt").read_text() == "mine"
    assert sorted(p.name for p in dst.iterdir()) == ["keep.txt"]
    assert src.exists()


def test_move_tree_uses_shutil_move_for_cross_filesystem(tmp_path: Path) -> None:
    """The cross-filesystem copy is shutil.move's; move_tree does not add its own."""
    src = _backup_tree(tmp_path / "raw" / "backup")
    dst = tmp_path / "media" / "T"
    with patch("arm_common.fileops.shutil.move", wraps=__import__("shutil").move) as spy:
        move_tree(src, dst)
    spy.assert_called_once()
    assert spy.call_args.args == (src, dst)


def _no_rename(monkeypatch: pytest.MonkeyPatch) -> None:
    def _exdev(a: object, b: object) -> None:
        raise OSError(18, "Invalid cross-device link")

    monkeypatch.setattr(fileops.os, "rename", _exdev)


def test_cancelled_tree_copy_removes_the_partial_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _backup_tree(tmp_path / "raw" / "backup")
    dst = tmp_path / "media" / "T"
    _no_rename(monkeypatch)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(CopyCancelled):
        move_tree(src, dst, cancel=cancel)
    assert not dst.exists() and tree_size(src) == 115


@pytest.fixture(autouse=True)
def _reset_shared_filesystem_advice(monkeypatch: pytest.MonkeyPatch) -> None:
    """The shared-filesystem advice is once per process; each test starts with none given."""
    monkeypatch.setattr(fileops, "_shared_filesystem_advised", False)


def _only_record(caplog: pytest.LogCaptureFixture, fragment: str) -> logging.LogRecord:
    matches = [r for r in caplog.records if fragment in r.getMessage()]
    assert len(matches) == 1, f"expected one record containing {fragment!r}, got {len(matches)}"
    return matches[0]


def test_per_file_detail_lines_log_at_debug(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """The atomic rename, the passthrough write and the folder move are per-file detail: DEBUG."""
    with caplog.at_level(logging.DEBUG, logger="arm_common.fileops"):
        with atomic_output(tmp_path / "out.mkv") as tmp:
            tmp.write_bytes(b"x")
        src = tmp_path / "raw" / "t0.mkv"
        src.parent.mkdir()
        src.write_bytes(b"y")
        transcode_none(src, tmp_path / "media" / "t0.mkv")
        move_tree(_backup_tree(tmp_path / "raw" / "backup"), tmp_path / "media" / "backup")
    assert _only_record(caplog, "atomic rename").levelno == logging.DEBUG
    assert _only_record(caplog, "passthrough wrote").levelno == logging.DEBUG
    assert _only_record(caplog, "passthrough moved folder").levelno == logging.DEBUG


def test_passthrough_fallback_keeps_the_link_failure_at_info(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    src = tmp_path / "raw" / "t0.mkv"
    src.parent.mkdir()
    src.write_bytes(b"v" * 10)
    _no_link(monkeypatch)
    with caplog.at_level(logging.DEBUG, logger="arm_common.fileops"):
        transcode_none(src, tmp_path / "media" / "t0.mkv")
    assert _only_record(caplog, "passthrough link failed").levelno == logging.INFO


def test_copy_reports_progress_and_hints_at_a_shared_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The copy reports every chunk, and a copy between two mounts of
    one filesystem logs the single-parent-mount hint, at INFO on the first file."""
    src = tmp_path / "raw" / "t0.mkv"
    src.parent.mkdir()
    src.write_bytes(b"v" * 10)
    _no_link(monkeypatch)
    monkeypatch.setattr(fileops, "COPY_CHUNK_BYTES", 4)
    chunks: list[int] = []
    with caplog.at_level(logging.DEBUG, logger="arm_common.fileops"):
        transcode_none(src, tmp_path / "media" / "t0.mkv", on_bytes=chunks.append)
    assert chunks == [4, 4, 2]
    assert _only_record(caplog, "share a filesystem").levelno == logging.INFO


def test_shared_filesystem_hint_is_info_once_then_debug(caplog: pytest.LogCaptureFixture) -> None:
    src = SimpleNamespace(name="t0.mkv", stat=lambda: SimpleNamespace(st_dev=1))
    dst_dir = SimpleNamespace(stat=lambda: SimpleNamespace(st_dev=1))
    with caplog.at_level(logging.DEBUG, logger="arm_common.fileops"):
        fileops._same_device_hint(src, dst_dir)  # type: ignore[arg-type]
        fileops._same_device_hint(src, dst_dir)  # type: ignore[arg-type]
    first, second = [r for r in caplog.records if "share a filesystem" in r.getMessage()]
    assert first.levelno == logging.INFO
    assert second.levelno == logging.DEBUG


def test_same_device_hint_is_silent_when_the_source_cannot_be_stat(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    def _missing() -> None:
        raise OSError(2, "No such file")

    src = SimpleNamespace(name="t0.mkv", stat=_missing)
    with caplog.at_level(logging.DEBUG, logger="arm_common.fileops"):
        fileops._same_device_hint(src, tmp_path)  # type: ignore[arg-type]
    assert caplog.records == []


def test_same_device_hint_is_silent_across_filesystems(caplog: pytest.LogCaptureFixture) -> None:
    src = SimpleNamespace(name="t0.mkv", stat=lambda: SimpleNamespace(st_dev=1))
    dst_dir = SimpleNamespace(stat=lambda: SimpleNamespace(st_dev=2))
    with caplog.at_level(logging.DEBUG, logger="arm_common.fileops"):
        fileops._same_device_hint(src, dst_dir)  # type: ignore[arg-type]
    assert caplog.records == []


def test_tree_copy_reports_progress(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _backup_tree(tmp_path / "raw" / "backup")
    _no_rename(monkeypatch)
    done: list[int] = []
    move_tree(src, tmp_path / "media" / "T", on_bytes=done.append)
    assert sum(done) == 115


def _record_durability_ops(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Log fsync and replace calls by the path they touched, in order."""
    ops: list[tuple[str, str]] = []
    real_replace = os.replace

    def spy_fsync(fd: int) -> None:
        ops.append(("fsync", Path(os.readlink(f"/proc/self/fd/{fd}")).name))

    def spy_replace(src: object, dst: object) -> None:
        ops.append(("replace", Path(str(src)).name))
        real_replace(src, dst)  # type: ignore[arg-type]

    monkeypatch.setattr(fileops.os, "fsync", spy_fsync)
    monkeypatch.setattr(fileops.os, "replace", spy_replace)
    return ops


def test_atomic_output_fsyncs_file_then_renames_then_fsyncs_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The data file is fsynced, and the directory is fsynced after the rename
    (a directory fsync before it makes nothing durable)."""
    ops = _record_durability_ops(monkeypatch)
    final = tmp_path / "movies" / "Iron Man.mkv"
    with atomic_output(final) as tmp:
        tmp.write_bytes(b"video")
    inprogress = "Iron Man.mkv" + INPROGRESS_SUFFIX
    assert ops == [("fsync", inprogress), ("replace", inprogress), ("fsync", "movies")]


def test_move_tree_fsyncs_each_file_before_the_source_goes_then_the_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cross-filesystem copy of a backup tree is fsynced."""
    src = _backup_tree(tmp_path / "raw" / "backup")
    dst = tmp_path / "media" / "T"
    _no_rename(monkeypatch)
    ops = _record_durability_ops(monkeypatch)
    real_rmtree = fileops.shutil.rmtree

    def spy_rmtree(path: object, *a: object, **kw: object) -> None:
        ops.append(("rmtree", Path(str(path)).name))
        real_rmtree(path, *a, **kw)

    monkeypatch.setattr(fileops.shutil, "rmtree", spy_rmtree)
    move_tree(src, dst)
    removed = ops.index(("rmtree", "backup"))
    file_fsyncs = [n for op, n in ops[:removed] if op == "fsync" and n.endswith(INPROGRESS_SUFFIX)]
    assert sorted(file_fsyncs) == [f"{n}{INPROGRESS_SUFFIX}" for n in ("00000.m2ts", "id.bdmv", "index.bdmv")]
    assert ops[removed + 1 :] == [
        ("fsync", "CERTIFICATE"),
        ("fsync", "STREAM"),
        ("fsync", "BDMV"),
        ("fsync", "T"),
        ("fsync", "media"),
    ]


def test_move_tree_rename_does_not_fsync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _backup_tree(tmp_path / "raw" / "backup")
    ops = _record_durability_ops(monkeypatch)
    move_tree(src, tmp_path / "media" / "T")
    assert ops == []


def test_directory_fsync_failure_does_not_fail_a_finished_rename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_fsync = os.fsync
    final = tmp_path / "out" / "a.mkv"

    def picky_fsync(fd: int) -> None:
        if os.path.isdir(f"/proc/self/fd/{fd}"):
            raise OSError(22, "EINVAL")
        real_fsync(fd)

    monkeypatch.setattr(fileops.os, "fsync", picky_fsync)
    with atomic_output(final) as tmp:
        tmp.write_bytes(b"x")
    assert final.read_bytes() == b"x"


# ---- resumable copier ----------------------------------------------


def _src(tmp_path: Path, data: bytes = b"0123456789abcdefghij", name: str = "raw/t0.mkv") -> Path:
    src = tmp_path / name
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_bytes(data)
    return src


def _no_link(monkeypatch: pytest.MonkeyPatch, code: int = errno.EXDEV) -> None:
    def _fail(a: object, b: object) -> None:
        raise OSError(code, os.strerror(code))

    monkeypatch.setattr(fileops.os, "link", _fail)


def _no_rename(monkeypatch: pytest.MonkeyPatch) -> None:
    def _exdev(a: object, b: object) -> None:
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    monkeypatch.setattr(fileops.os, "rename", _exdev)


def test_inprogress_path_appends_the_suffix(tmp_path: Path) -> None:
    assert inprogress_path(tmp_path / "a.mkv") == tmp_path / ("a.mkv" + INPROGRESS_SUFFIX)


def test_source_stamp_of_reads_size_and_mtime(tmp_path: Path) -> None:
    src = _src(tmp_path)
    stamp = SourceStamp.of(src)
    assert stamp.size == 20 and stamp.mtime_ns == src.stat().st_mtime_ns


def test_link_unavailable_carries_errno_and_is_not_an_oserror() -> None:
    exc = LinkUnavailable(errno.EXDEV, "boom")
    assert exc.errno == errno.EXDEV and str(exc) == "boom" and not isinstance(exc, OSError)


def test_copy_resumable_copies_and_keeps_mtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fileops, "COPY_CHUNK_BYTES", 7)
    src = _src(tmp_path)
    os.utime(src, (1_000_000_000, 1_000_000_000))
    stamp = SourceStamp.of(src)
    dst = tmp_path / "media" / "out.mkv"
    result = copy_file_resumable(src, dst, expect=stamp)
    assert result == PlaceResult(size=20, linked=False)
    assert dst.read_bytes() == src.read_bytes()
    assert not inprogress_path(dst).exists()
    assert is_placed(stamp, dst)


def test_checkpoint_fsyncs_before_reporting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fileops, "COPY_CHUNK_BYTES", 4)
    monkeypatch.setattr(fileops, "CHECKPOINT_BYTES", 8)
    src = _src(tmp_path)
    dst = tmp_path / "media" / "out.mkv"
    events: list[tuple[str, int]] = []
    real_fsync = os.fsync

    def spy_fsync(fd: int) -> None:
        events.append(("fsync", Path(os.readlink(f"/proc/self/fd/{fd}")).name == "out.mkv" + INPROGRESS_SUFFIX))  # type: ignore[arg-type]
        real_fsync(fd)

    monkeypatch.setattr(fileops.os, "fsync", spy_fsync)
    copy_file_resumable(src, dst, on_checkpoint=lambda off: events.append(("ckpt", off)))
    ckpts = [i for i, (kind, _v) in enumerate(events) if kind == "ckpt"]
    assert [events[i][1] for i in ckpts] == [8, 16]
    assert all(events[i - 1] == ("fsync", True) for i in ckpts)


def test_checkpoint_fires_on_time_for_a_slow_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fileops, "COPY_CHUNK_BYTES", 5)
    ticks = iter(range(0, 10_000, 31))
    reported: list[int] = []
    copy_file_resumable(
        _src(tmp_path),
        tmp_path / "media" / "o.mkv",
        on_checkpoint=reported.append,
        clock=lambda: float(next(ticks)),
    )
    assert reported == [5, 10, 15, 20]


def test_truncate_and_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fileops, "COPY_CHUNK_BYTES", 6)
    src = _src(tmp_path)
    dst = tmp_path / "media" / "o.mkv"
    dst.parent.mkdir()
    inprogress_path(dst).write_bytes(src.read_bytes()[:8] + b"GARBAGE")
    seen: list[int] = []
    result = copy_file_resumable(src, dst, resume_from=8, on_bytes=seen.append)
    assert dst.read_bytes() == src.read_bytes()
    assert result.size == 20
    assert seen[0] == 8 and sum(seen) == 20


class _ReadLog:
    """Wraps a source opened for reading; records the offset and size of every read."""

    def __init__(self, fh: object, log: list[tuple[int, int]]) -> None:
        self._fh = fh
        self._log = log

    def __enter__(self) -> _ReadLog:
        return self

    def __exit__(self, *exc: object) -> None:
        self._fh.close()  # type: ignore[attr-defined]

    def read(self, n: int = -1) -> bytes:
        at = self._fh.tell()  # type: ignore[attr-defined]
        data: bytes = self._fh.read(n)  # type: ignore[attr-defined]
        self._log.append((at, len(data)))
        return data

    def __getattr__(self, name: str) -> object:
        return getattr(self._fh, name)


def _log_reads_of(monkeypatch: pytest.MonkeyPatch, src: Path) -> list[tuple[int, int]]:
    """Record every read of `src` through `Path.open`."""
    log: list[tuple[int, int]] = []
    real_open = Path.open

    def spy(self: Path, mode: str = "r", *a: object, **kw: object):  # type: ignore[no-untyped-def]
        fh = real_open(self, mode, *a, **kw)  # type: ignore[arg-type]
        return _ReadLog(fh, log) if self == src else fh

    monkeypatch.setattr(Path, "open", spy)
    return log


def test_resume_continues_from_the_prefix_without_reading_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _src(tmp_path)
    dst = tmp_path / "media" / "o.mkv"
    dst.parent.mkdir()
    inprogress_path(dst).write_bytes(src.read_bytes()[:8])
    reads = _log_reads_of(monkeypatch, src)
    result = copy_file_resumable(src, dst, resume_from=8)
    assert result == PlaceResult(size=20, linked=False)
    assert reads[0][0] == 8 and sum(n for _at, n in reads) == 12
    assert dst.read_bytes() == src.read_bytes()


def test_resume_with_short_temp_restarts_and_reports_zero(tmp_path: Path) -> None:
    src = _src(tmp_path)
    dst = tmp_path / "media" / "o.mkv"
    dst.parent.mkdir()
    inprogress_path(dst).write_bytes(b"abc")
    seen: list[int] = []
    result = copy_file_resumable(src, dst, resume_from=8, on_checkpoint=seen.append)
    assert seen[:1] == [0] and dst.read_bytes() == src.read_bytes() and result.size == 20


def test_resume_without_temp_restarts(tmp_path: Path) -> None:
    src = _src(tmp_path)
    dst = tmp_path / "media" / "o.mkv"
    seen: list[int] = []
    copy_file_resumable(src, dst, resume_from=8, on_checkpoint=seen.append)
    assert seen[:1] == [0] and dst.read_bytes() == src.read_bytes()


def test_resume_restart_without_a_checkpoint_callback(tmp_path: Path) -> None:
    src = _src(tmp_path)
    dst = tmp_path / "o.mkv"
    assert copy_file_resumable(src, dst, resume_from=8).size == 20


def test_expect_mismatch_raises_and_drops_temp(tmp_path: Path) -> None:
    src = _src(tmp_path)
    stamp = SourceStamp.of(src)
    src.write_bytes(b"changed!")
    dst = tmp_path / "media" / "o.mkv"
    dst.parent.mkdir()
    inprogress_path(dst).write_bytes(b"old")
    with pytest.raises(SourceChanged):
        copy_file_resumable(src, dst, expect=stamp)
    assert not inprogress_path(dst).exists() and not dst.exists()


def test_source_grows_during_copy_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fileops, "COPY_CHUNK_BYTES", 5)
    src = _src(tmp_path)
    dst = tmp_path / "media" / "o.mkv"

    grown: list[int] = []

    def grow(_n: int) -> None:
        if not grown:
            grown.append(1)
            with src.open("ab") as fh:
                fh.write(b"+")

    with pytest.raises(SourceChanged):
        copy_file_resumable(src, dst, on_bytes=grow)
    assert not inprogress_path(dst).exists() and not dst.exists()


def test_cancel_keeps_temp_and_does_not_fsync(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fileops, "COPY_CHUNK_BYTES", 4)
    monkeypatch.setattr(fileops, "CHECKPOINT_BYTES", 8)
    src = _src(tmp_path)
    dst = tmp_path / "media" / "o.mkv"
    cancel = threading.Event()
    calls: list[str] = []
    monkeypatch.setattr(fileops.os, "fsync", lambda fd: calls.append("fsync"))
    chunks: list[int] = []

    def on_bytes(n: int) -> None:
        chunks.append(n)
        if len(chunks) == 2:
            cancel.set()

    with pytest.raises(CopyCancelled):
        copy_file_resumable(src, dst, cancel=cancel, on_bytes=on_bytes, on_checkpoint=lambda _o: calls.append("ckpt"))
    # the checkpoint at 8 bytes ran before the cancel was seen; nothing was fsynced after it
    assert calls == ["fsync", "ckpt"]
    assert inprogress_path(dst).read_bytes() == src.read_bytes()[:8] and not dst.exists()


def test_cancel_on_resume_keeps_temp(tmp_path: Path) -> None:
    src = _src(tmp_path)
    dst = tmp_path / "o.mkv"
    inprogress_path(dst).write_bytes(src.read_bytes()[:8])
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(CopyCancelled):
        copy_file_resumable(src, dst, resume_from=8, cancel=cancel)
    assert inprogress_path(dst).exists()


def test_write_error_keeps_temp_for_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fileops, "COPY_CHUNK_BYTES", 5)
    src = _src(tmp_path)
    dst = tmp_path / "media" / "o.mkv"

    def boom(_n: int) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    with pytest.raises(OSError):
        copy_file_resumable(src, dst, on_bytes=boom)
    assert inprogress_path(dst).exists()


def test_crash_between_rename_and_commit_is_detectable(tmp_path: Path) -> None:
    src = _src(tmp_path)
    stamp = SourceStamp.of(src)
    dst = tmp_path / "media" / "o.mkv"
    assert not is_placed(stamp, dst)  # nothing there
    copy_file_resumable(src, dst)
    assert is_placed(stamp, dst)
    inprogress_path(dst).write_bytes(b"leftover")
    assert not is_placed(stamp, dst)
    inprogress_path(dst).unlink()
    dst.write_bytes(b"other size")
    assert not is_placed(stamp, dst)
    dst.write_bytes(src.read_bytes())
    os.utime(dst, ns=(stamp.mtime_ns + 10 * 10**9, stamp.mtime_ns + 10 * 10**9))
    assert not is_placed(stamp, dst)


# ---- link and rename placement ---------------------------------------------


def test_place_by_link_keeps_source(tmp_path: Path) -> None:
    src = _src(tmp_path)
    dst = tmp_path / "media" / "o.mkv"
    result = place_by_link(src, dst, keep_source=True, expect=SourceStamp.of(src))
    assert result == PlaceResult(size=20, linked=True)
    assert src.exists() and os.path.samefile(src, dst) and not inprogress_path(dst).exists()


def test_place_by_link_move_removes_source(tmp_path: Path) -> None:
    src = _src(tmp_path)
    dst = tmp_path / "media" / "o.mkv"
    place_by_link(src, dst, keep_source=False)
    assert not src.exists() and dst.read_bytes() == b"0123456789abcdefghij"


def test_place_by_link_replaces_a_stale_temp(tmp_path: Path) -> None:
    src = _src(tmp_path)
    dst = tmp_path / "media" / "o.mkv"
    dst.parent.mkdir()
    inprogress_path(dst).write_bytes(b"stale")
    place_by_link(src, dst, keep_source=True)
    assert dst.read_bytes() == src.read_bytes()


def test_place_by_link_exdev_raises_link_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _src(tmp_path)
    dst = tmp_path / "media" / "o.mkv"
    _no_link(monkeypatch)
    with pytest.raises(LinkUnavailable) as info:
        place_by_link(src, dst, keep_source=False)
    assert info.value.errno == errno.EXDEV
    assert src.exists() and list((tmp_path / "media").iterdir()) == []


def test_place_by_link_expect_mismatch(tmp_path: Path) -> None:
    src = _src(tmp_path)
    stamp = SourceStamp.of(src)
    src.write_bytes(b"x")
    with pytest.raises(SourceChanged):
        place_by_link(src, tmp_path / "media" / "o.mkv", keep_source=True, expect=stamp)


def test_place_by_link_does_not_read_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _src(tmp_path)
    reads = _log_reads_of(monkeypatch, src)
    place_by_link(src, tmp_path / "media" / "o.mkv", keep_source=True)
    assert reads == []


def test_place_by_link_source_changed_after_link(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _src(tmp_path)
    dst = tmp_path / "media" / "o.mkv"
    real_link = fileops._link_temp

    def link_then_touch(s: Path, tmp: Path) -> None:
        real_link(s, tmp)
        os.utime(src, ns=(1, 1))

    monkeypatch.setattr(fileops, "_link_temp", link_then_touch)
    with pytest.raises(SourceChanged):
        place_by_link(src, dst, keep_source=False)
    assert src.exists() and not dst.exists() and not inprogress_path(dst).exists()


def test_place_by_rename_moves(tmp_path: Path) -> None:
    src = _src(tmp_path)
    dst = tmp_path / "media" / "o.mkv"
    result = place_by_rename(src, dst, expect=SourceStamp.of(src))
    assert result == PlaceResult(size=20, linked=True)
    assert not src.exists() and dst.exists()


def test_place_by_rename_does_not_read_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _src(tmp_path)
    reads = _log_reads_of(monkeypatch, src)
    place_by_rename(src, tmp_path / "media" / "o.mkv")
    assert reads == []


def test_place_by_rename_failure_raises_link_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _src(tmp_path)
    _no_rename(monkeypatch)
    with pytest.raises(LinkUnavailable) as info:
        place_by_rename(src, tmp_path / "media" / "o.mkv")
    assert info.value.errno == errno.EXDEV and src.exists()


def test_place_by_rename_expect_mismatch(tmp_path: Path) -> None:
    src = _src(tmp_path)
    stamp = SourceStamp.of(src)
    src.write_bytes(b"x")
    with pytest.raises(SourceChanged):
        place_by_rename(src, tmp_path / "o.mkv", expect=stamp)


# ---- helpers, directly ------------------------------------------------------


def test_can_resume_is_false_for_a_missing_or_short_temp(tmp_path: Path) -> None:
    tmp = tmp_path / "t"
    assert not fileops._can_resume(tmp, 1)
    tmp.write_bytes(b"ab")
    assert not fileops._can_resume(tmp, 3) and fileops._can_resume(tmp, 2)


def test_raise_if_cancelled_only_raises_when_set() -> None:
    fileops._raise_if_cancelled(None, "x")
    event = threading.Event()
    fileops._raise_if_cancelled(event, "x")
    event.set()
    with pytest.raises(CopyCancelled):
        fileops._raise_if_cancelled(event, "x")


def test_checkpoint_clock_fires_on_bytes_or_seconds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fileops, "CHECKPOINT_BYTES", 10)
    now = [0.0]
    ckpt = fileops._CheckpointClock(lambda: now[0])
    assert not ckpt.due(9)
    assert ckpt.due(10)
    ckpt.mark(10)
    assert not ckpt.due(15)
    now[0] = fileops.CHECKPOINT_SECONDS
    assert ckpt.due(15)


def test_verify_source_unchanged_accepts_an_unchanged_source_and_drops_temp_otherwise(tmp_path: Path) -> None:
    src = _src(tmp_path)
    tmp = tmp_path / "t"
    tmp.write_bytes(b"p")
    stamp = SourceStamp.of(src)
    fileops._verify_source_unchanged(src, stamp, 20, tmp)
    assert tmp.exists()
    with pytest.raises(SourceChanged):
        fileops._verify_source_unchanged(src, stamp, 19, tmp)
    assert not tmp.exists()


def test_remove_source_unlinks(tmp_path: Path) -> None:
    src = _src(tmp_path)
    fileops._remove_source(src)
    assert not src.exists()


# ---- transcode_none ---------------------------------------------------------


def test_transcode_none_same_fs_links(tmp_path: Path) -> None:
    src = _src(tmp_path, b"iso bytes", "raw/dump.iso")
    dst = tmp_path / "media" / "Movie (2024)" / "Movie (2024).iso"
    result = transcode_none(src, dst)
    assert result == PlaceResult(size=9, linked=True)
    assert dst.read_bytes() == b"iso bytes" and not src.exists()


def test_transcode_none_same_fs_does_not_read_the_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _src(tmp_path)
    reads = _log_reads_of(monkeypatch, src)
    transcode_none(src, tmp_path / "media" / "o.mkv")
    assert reads == []


def test_transcode_none_exdev_copies_and_removes_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(fileops, "COPY_CHUNK_BYTES", 4)
    src = _src(tmp_path)
    dst = tmp_path / "media" / "t0.mkv"
    _no_link(monkeypatch)
    chunks: list[int] = []
    with caplog.at_level("INFO", logger="arm_common.fileops"):
        result = transcode_none(src, dst, on_bytes=chunks.append)
    assert result == PlaceResult(size=20, linked=False)
    assert dst.read_bytes() == b"0123456789abcdefghij" and not src.exists()
    assert chunks == [4] * 5
    assert "share a filesystem" in caplog.text


def test_transcode_none_eperm_link_falls_back_to_rename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _src(tmp_path)
    dst = tmp_path / "media" / "t0.mkv"
    _no_link(monkeypatch, errno.EPERM)
    calls: list[object] = []
    real_rename = os.rename
    monkeypatch.setattr(fileops.os, "rename", lambda a, b: (calls.append(a), real_rename(a, b))[1])
    result = transcode_none(src, dst)
    assert len(calls) == 1 and result.linked
    assert not src.exists()


def test_transcode_none_eperm_then_rename_failure_copies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _src(tmp_path)
    dst = tmp_path / "media" / "t0.mkv"
    _no_link(monkeypatch, errno.EPERM)
    _no_rename(monkeypatch)
    result = transcode_none(src, dst)
    assert not result.linked and dst.read_bytes() == b"0123456789abcdefghij" and not src.exists()


def test_transcode_none_copy_cancel_removes_partial_keeps_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fileops, "COPY_CHUNK_BYTES", 3)
    src = _src(tmp_path)
    dst = tmp_path / "media" / "t0.mkv"
    _no_link(monkeypatch)
    cancel = threading.Event()
    with pytest.raises(CopyCancelled):
        transcode_none(src, dst, cancel=cancel, on_bytes=lambda _n: cancel.set())
    assert src.read_bytes() == b"0123456789abcdefghij"
    assert list((tmp_path / "media").iterdir()) == []


def test_transcode_none_post_copy_unlink_failure_keeps_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    src = _src(tmp_path)
    dst = tmp_path / "media" / "t0.mkv"
    _no_link(monkeypatch)
    real_unlink = Path.unlink

    def _unlink(self: Path, *args: object, **kwargs: object) -> None:
        if self == src:
            raise PermissionError(13, "Permission denied")
        real_unlink(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "unlink", _unlink)
    with caplog.at_level("WARNING", logger="arm_common.fileops"):
        result = transcode_none(src, dst)
    assert result.size == 20 and dst.read_bytes() == src.read_bytes()
    assert "post-copy unlink failed" in caplog.text and "will leave source in /raw" in caplog.text


def test_transcode_none_copy_fsyncs_before_rename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _src(tmp_path, b"iso", "raw/title.iso")
    dst = tmp_path / "media" / "title.iso"
    _no_link(monkeypatch)
    ops = _record_durability_ops(monkeypatch)
    transcode_none(src, dst)
    inprogress = "title.iso" + INPROGRESS_SUFFIX
    assert ops == [("fsync", inprogress), ("replace", inprogress), ("fsync", "media")]


def test_same_device_hint_is_silent_when_a_path_cannot_be_statted(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("INFO", logger="arm_common.fileops"):
        fileops._same_device_hint(tmp_path / "missing", tmp_path)
    assert "share a filesystem" not in caplog.text


def test_same_device_hint_is_silent_across_devices(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    src = _src(tmp_path)
    real_stat = Path.stat

    def fake_stat(self: Path, *a: object, **kw: object) -> os.stat_result:
        st = real_stat(self, *a, **kw)  # type: ignore[arg-type]
        values = list(st)
        values[2] = 999 if self == tmp_path else st.st_dev  # st_dev slot
        return os.stat_result(values)

    monkeypatch.setattr(Path, "stat", fake_stat)
    with caplog.at_level("INFO", logger="arm_common.fileops"):
        fileops._same_device_hint(src, tmp_path)
    assert "share a filesystem" not in caplog.text
