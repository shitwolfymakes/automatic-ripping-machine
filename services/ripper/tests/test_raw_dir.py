"""Tests for the best-effort /raw/<job_id>/ wipe and what it logs."""

import logging
import os
from pathlib import Path
from typing import Any

import pytest

import arm_ripper.raw_dir as raw_dir_module
from arm_ripper.raw_dir import wipe_raw_dir

_LOGGER = "arm_ripper.raw_dir"


@pytest.fixture(autouse=True)
def patch_raw_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(raw_dir_module, "RAW_ROOT", tmp_path)


def _records(caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == level and r.name == _LOGGER]


async def test_wipe_removes_nested_files_and_logs_wiped(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    nested = tmp_path / "job_x" / "title" / "deep"
    nested.mkdir(parents=True)
    (nested / "a.mkv").write_bytes(b"x")
    (tmp_path / "job_x" / "b.mkv").write_bytes(b"y")
    caplog.set_level(logging.INFO, logger=_LOGGER)

    await wipe_raw_dir("job_x")

    assert not (tmp_path / "job_x").exists()
    assert any("wiped raw dir" in m for m in _records(caplog, logging.INFO))
    assert _records(caplog, logging.WARNING) == []


async def test_wipe_missing_dir_logs_already_absent(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger=_LOGGER)

    await wipe_raw_dir("never_existed")

    infos = _records(caplog, logging.INFO)
    assert any("raw dir already absent" in m for m in infos)
    assert not any("wiped raw dir" in m for m in infos)
    assert _records(caplog, logging.WARNING) == []


async def test_wipe_unremovable_entry_logs_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    path = str(tmp_path / "job_x" / "a.mkv")

    def fake_rmtree(_target: Path, *, onexc: Any) -> None:
        onexc(os.unlink, path, PermissionError(13, "Permission denied", path))

    monkeypatch.setattr(raw_dir_module.shutil, "rmtree", fake_rmtree)
    caplog.set_level(logging.INFO, logger=_LOGGER)

    await wipe_raw_dir("job_x")

    warnings = _records(caplog, logging.WARNING)
    assert len(warnings) == 1
    assert "raw-dir cleanup failed" in warnings[0]
    assert "Permission denied" in warnings[0]
    assert "(1 error(s))" in warnings[0]


async def test_wipe_vanished_inner_entry_still_counts_as_wiped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    path = str(tmp_path / "job_x" / "gone.mkv")

    def fake_rmtree(_target: Path, *, onexc: Any) -> None:
        onexc(os.unlink, path, FileNotFoundError(2, "No such file or directory", path))

    monkeypatch.setattr(raw_dir_module.shutil, "rmtree", fake_rmtree)
    caplog.set_level(logging.INFO, logger=_LOGGER)

    await wipe_raw_dir("job_x")

    infos = _records(caplog, logging.INFO)
    assert any("wiped raw dir" in m for m in infos)
    assert not any("already absent" in m for m in infos)
    assert _records(caplog, logging.WARNING) == []


async def test_wipe_not_found_without_filename_is_not_absent(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def fake_rmtree(_target: Path, *, onexc: Any) -> None:
        onexc(os.unlink, "x", FileNotFoundError())

    monkeypatch.setattr(raw_dir_module.shutil, "rmtree", fake_rmtree)
    caplog.set_level(logging.INFO, logger=_LOGGER)

    await wipe_raw_dir("job_x")

    assert any("wiped raw dir" in m for m in _records(caplog, logging.INFO))
