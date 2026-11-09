"""Direct tests for the whole-file readers in `arm_backend.log_reader`."""

from __future__ import annotations

from pathlib import Path

import pytest

from arm_backend import log_reader


def test_file_log_lines_zero_cap_yields_nothing(tmp_path: Path) -> None:
    path = tmp_path / "x.log"
    path.write_text("a\nb\n")
    assert list(log_reader.file_log_lines(path, 0)) == []


def test_file_log_lines_terminates_last_line(tmp_path: Path) -> None:
    path = tmp_path / "x.log"
    path.write_text("a\nb")
    assert list(log_reader.file_log_lines(path, 5)) == [b"a\n", b"b\n"]


def test_file_log_lines_stops_at_cap(tmp_path: Path) -> None:
    path = tmp_path / "x.log"
    path.write_text("a\nb\nc\n")
    assert list(log_reader.file_log_lines(path, 2)) == [b"a\n", b"b\n"]


def test_file_log_lines_missing_file_yields_nothing(tmp_path: Path) -> None:
    assert list(log_reader.file_log_lines(tmp_path / "nope.log", 5)) == []


def test_file_log_slice_returns_every_line(tmp_path: Path) -> None:
    path = tmp_path / "x.log"
    path.write_text("x\ny")
    assert log_reader.file_log_slice(path) == ["x\n", "y\n"]


def test_file_log_slice_honours_line_cap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "x.log"
    path.write_text("x\ny")
    monkeypatch.setattr(log_reader.settings, "ARM_LOG_ZIP_PER_ENTRY_LINE_CAP", 1)
    assert log_reader.file_log_slice(path) == ["x\n"]
