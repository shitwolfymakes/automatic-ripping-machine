"""Atomic-rename context manager and TranscodeTool.NONE passthrough move."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

import threading

from arm_common import fileops
from arm_common.fileops import (
    INPROGRESS_SUFFIX,
    CopyCancelled,
    atomic_output,
    is_within,
    move_tree,
    safe_join,
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


def test_passthrough_renames_when_same_fs(tmp_path: Path) -> None:
    src = tmp_path / "raw" / "dump.iso"
    src.parent.mkdir()
    src.write_bytes(b"iso bytes")
    dst = tmp_path / "media" / "Movie (2024)" / "Movie (2024).iso"

    size = transcode_none(src, dst)
    assert size == len(b"iso bytes")
    assert dst.exists()
    assert not src.exists()


def test_passthrough_falls_back_to_copy_on_cross_fs_rename(tmp_path: Path) -> None:
    src = tmp_path / "raw" / "dump.iso"
    src.parent.mkdir()
    src.write_bytes(b"iso bytes")
    dst = tmp_path / "media" / "X.iso"

    real_rename = __import__("os").rename

    def _fake_rename(s: str, d: str) -> None:
        if "/raw/" in str(s) and "/media/" in str(d):
            raise OSError(18, "Invalid cross-device link")
        real_rename(s, d)

    with patch("os.rename", _fake_rename):
        size = transcode_none(src, dst)

    assert size == len(b"iso bytes")
    assert dst.exists()
    assert not src.exists()


def test_transcode_none_copy_fallback(tmp_path, monkeypatch):
    src = tmp_path / "in.mkv"
    src.write_bytes(b"x" * 32)
    dst = tmp_path / "out" / "final.mkv"

    def _rename_fails(a: object, b: object) -> None:
        raise OSError(18, "Invalid cross-device link")

    monkeypatch.setattr(os, "rename", _rename_fails)
    size = transcode_none(src, dst)
    assert size == 32
    assert dst.read_bytes() == b"x" * 32
    assert not src.exists()


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


def test_copy_fallback_goes_through_inprogress_then_renames(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """D-066: the cross-mount copy never exposes a partial file at the final path."""
    src = tmp_path / "raw" / "t0.mkv"
    src.parent.mkdir()
    src.write_bytes(b"v" * 10)
    dst = tmp_path / "media" / "t0.mkv"
    _no_rename(monkeypatch)
    monkeypatch.setattr(fileops, "COPY_CHUNK_BYTES", 3)
    seen: list[str] = []
    real_replace = os.replace

    def _replace(a: object, b: object) -> None:
        seen.append(Path(str(a)).name)
        real_replace(a, b)  # type: ignore[arg-type]

    monkeypatch.setattr(fileops.os, "replace", _replace)
    assert transcode_none(src, dst) == 10
    assert seen == ["t0.mkv" + INPROGRESS_SUFFIX] and dst.read_bytes() == b"v" * 10 and not src.exists()


def test_cancelled_copy_removes_the_partial_and_keeps_the_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-066: a cancel stops the copy at the next chunk; nothing lands in
    /media and the raw source is not consumed."""
    src = tmp_path / "raw" / "t0.mkv"
    src.parent.mkdir()
    src.write_bytes(b"v" * 10)
    dst = tmp_path / "media" / "t0.mkv"
    _no_rename(monkeypatch)
    monkeypatch.setattr(fileops, "COPY_CHUNK_BYTES", 3)
    cancel = threading.Event()
    real_open = Path.open

    def _open(self: Path, mode: str = "r", *a: object, **kw: object):  # type: ignore[no-untyped-def]
        fh = real_open(self, mode, *a, **kw)  # type: ignore[arg-type]
        if mode == "rb":
            real_read = fh.read

            def _read(n: int = -1) -> bytes:
                chunk = real_read(n)
                cancel.set()  # cancelled after the first chunk is read
                return chunk

            fh.read = _read  # type: ignore[method-assign]
        return fh

    monkeypatch.setattr(Path, "open", _open)
    with pytest.raises(CopyCancelled):
        transcode_none(src, dst, cancel=cancel)
    assert src.read_bytes() == b"v" * 10
    assert list((tmp_path / "media").iterdir()) == []


def test_cancelled_tree_copy_removes_the_partial_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _backup_tree(tmp_path / "raw" / "backup")
    dst = tmp_path / "media" / "T"
    _no_rename(monkeypatch)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(CopyCancelled):
        move_tree(src, dst, cancel=cancel)
    assert not dst.exists() and tree_size(src) == 115


def test_copy_reports_progress_and_hints_at_a_shared_filesystem(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """D-127: the copy reports every chunk, and a copy between two mounts of
    one filesystem logs the single-parent-mount hint."""
    src = tmp_path / "raw" / "t0.mkv"
    src.parent.mkdir()
    src.write_bytes(b"v" * 10)
    _no_rename(monkeypatch)
    monkeypatch.setattr(fileops, "COPY_CHUNK_BYTES", 4)
    chunks: list[int] = []
    with caplog.at_level("INFO", logger="arm_common.fileops"):
        transcode_none(src, tmp_path / "media" / "t0.mkv", on_bytes=chunks.append)
    assert chunks == [4, 4, 2]
    assert "share a filesystem" in caplog.text


def test_tree_copy_reports_progress(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = _backup_tree(tmp_path / "raw" / "backup")
    _no_rename(monkeypatch)
    done: list[int] = []
    move_tree(src, tmp_path / "media" / "T", on_bytes=done.append)
    assert sum(done) == 115


def test_safe_join_returns_the_resolved_path_inside_base(tmp_path: Path) -> None:
    assert safe_join(tmp_path, "a/./b/../c.txt") == tmp_path.resolve() / "a" / "c.txt"


@pytest.mark.parametrize("relative", ["../x", "a/../../x", "/etc/passwd"])
def test_safe_join_rejects_a_path_outside_base(tmp_path: Path, relative: str) -> None:
    with pytest.raises(ValueError, match="escapes"):
        safe_join(tmp_path / "base", relative)


def test_safe_join_rejects_a_symlink_pointing_outward(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    (base / "link").symlink_to(tmp_path)
    with pytest.raises(ValueError, match="escapes"):
        safe_join(base, "link/x")


def test_safe_join_rejects_base_itself_unless_allowed(tmp_path: Path) -> None:
    for relative in ("", ".", "a/.."):
        with pytest.raises(ValueError, match="escapes"):
            safe_join(tmp_path, relative)
        assert safe_join(tmp_path, relative, allow_root=True) == tmp_path.resolve()


def test_safe_join_resolves_a_symlinked_base(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "alias").symlink_to(real)
    assert safe_join(tmp_path / "alias", "x") == real / "x"


def test_is_within(tmp_path: Path) -> None:
    assert is_within(tmp_path / "a" / "b", tmp_path)
    assert not is_within(tmp_path, tmp_path)
    assert is_within(tmp_path, tmp_path, allow_root=True)
    assert not is_within(tmp_path / ".." / "x", tmp_path)
    assert not is_within(tmp_path.parent, tmp_path, allow_root=True)


def _record_durability_ops(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Log fsync and replace calls by the path they touched, in order."""
    ops: list[tuple[str, str]] = []
    real_open, real_replace = os.open, os.replace
    fd_paths: dict[int, str] = {}

    def spy_open(path: str, flags: int, *a: object, **kw: object) -> int:
        fd = real_open(path, flags, *a, **kw)
        fd_paths[fd] = Path(path).name
        return fd

    def spy_fsync(fd: int) -> None:
        ops.append(("fsync", fd_paths[fd]))

    def spy_replace(src: object, dst: object) -> None:
        ops.append(("replace", Path(str(src)).name))
        real_replace(src, dst)

    monkeypatch.setattr(fileops.os, "open", spy_open)
    monkeypatch.setattr(fileops.os, "fsync", spy_fsync)
    monkeypatch.setattr(fileops.os, "replace", spy_replace)
    return ops


def test_atomic_output_fsyncs_file_then_renames_then_fsyncs_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-179: a directory fsync before the rename made nothing durable and
    the data file was never fsynced at all."""
    ops = _record_durability_ops(monkeypatch)
    final = tmp_path / "movies" / "Iron Man.mkv"
    with atomic_output(final) as tmp:
        tmp.write_bytes(b"video")
    inprogress = "Iron Man.mkv" + INPROGRESS_SUFFIX
    assert ops == [("fsync", inprogress), ("replace", inprogress), ("fsync", "movies")]


def test_copy_fallback_fsyncs_before_the_rename(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "raw" / "title.iso"
    src.parent.mkdir()
    src.write_bytes(b"iso")
    dst = tmp_path / "media" / "title.iso"
    monkeypatch.setattr(fileops.os, "rename", lambda *_a: (_ for _ in ()).throw(OSError(18, "EXDEV")))
    ops = _record_durability_ops(monkeypatch)
    transcode_none(src, dst)
    inprogress = "title.iso" + INPROGRESS_SUFFIX
    assert ops == [("fsync", inprogress), ("replace", inprogress), ("fsync", "media")]


def test_move_tree_fsyncs_each_file_before_the_source_goes_then_the_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-247: the cross-filesystem copy of a backup tree was never fsynced."""
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
    assert sorted(n for _op, n in ops[:removed]) == ["00000.m2ts", "id.bdmv", "index.bdmv"]
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
