"""TranscodeTool.NONE passthrough — same-fs rename + cross-fs copy."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from arm_transcode.passthrough import transcode_none


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
