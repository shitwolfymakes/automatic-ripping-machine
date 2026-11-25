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


def test_job_without_a_per_job_file_has_no_lines(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(log_reader, "LOG_DIR", tmp_path)
    (tmp_path / "arm-backend.log").write_text('{"job_id": "job_01JZXR7K3M5Q8N4VWA00000001", "msg": "x"}\n')
    assert list(log_reader.job_log_lines("job_01JZXR7K3M5Q8N4VWA00000001", 100)) == []


def test_zip_of_a_job_without_a_per_job_file_is_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(log_reader, "LOG_DIR", tmp_path)
    (tmp_path / "arm-backend.log").write_text('{"job_id": "job_01JZXR7K3M5Q8N4VWA00000001", "msg": "x"}\n')
    assert list(log_reader.job_log_slices("job_01JZXR7K3M5Q8N4VWA00000001")) == []


def test_job_with_a_per_job_file_reads_and_slices_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(log_reader, "LOG_DIR", tmp_path)
    (tmp_path / "jobs").mkdir()
    (tmp_path / "jobs" / "job_01JZXR7K3M5Q8N4VWA00000001.log").write_text("a\nb\n")
    assert list(log_reader.job_log_lines("job_01JZXR7K3M5Q8N4VWA00000001", 100)) == [b"a\n", b"b\n"]
    assert list(log_reader.job_log_slices("job_01JZXR7K3M5Q8N4VWA00000001")) == [
        ("job_01JZXR7K3M5Q8N4VWA00000001.log", ["a\n", "b\n"])
    ]


def test_job_log_lines_zero_cap_yields_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(log_reader, "LOG_DIR", tmp_path)
    (tmp_path / "jobs").mkdir()
    (tmp_path / "jobs" / "job_01JZXR7K3M5Q8N4VWA00000001.log").write_text("a\n")
    assert list(log_reader.job_log_lines("job_01JZXR7K3M5Q8N4VWA00000001", 0)) == []


def test_file_log_slice_of_an_unopenable_file_is_empty(tmp_path: Path) -> None:
    (tmp_path / "bad.log").mkdir()
    assert log_reader.file_log_slice(tmp_path / "bad.log") == []
