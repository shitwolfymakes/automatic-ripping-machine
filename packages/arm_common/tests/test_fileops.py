"""Atomic-rename context manager and TranscodeTool.NONE passthrough move."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from arm_common.fileops import INPROGRESS_SUFFIX, atomic_output, move_tree, transcode_none, tree_size


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
    spy.assert_called_once_with(src, dst)
