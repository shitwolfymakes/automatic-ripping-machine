"""Atomic-rename context manager and TranscodeTool.NONE passthrough move."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from arm_common.fileops import INPROGRESS_SUFFIX, atomic_output, transcode_none


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
