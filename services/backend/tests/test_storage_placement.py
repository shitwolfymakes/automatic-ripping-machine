"""Where staging sits relative to raw: the pure decision and the stat-ing wrapper."""

from __future__ import annotations

from pathlib import Path

import pytest

from arm_backend import storage_placement as sp
from arm_backend.config import settings as base_settings
from arm_common.schemas import StoragePlacement


@pytest.mark.parametrize(
    ("inside", "staging_dev", "raw_dev", "expected"),
    [
        (True, None, None, StoragePlacement.INSIDE_RAW),
        (True, 2, 1, StoragePlacement.INSIDE_RAW),
        (False, 5, 5, StoragePlacement.SAME_DEVICE),
        (False, 5, 6, StoragePlacement.SEPARATE_DEVICE),
        (False, None, 6, None),
        (False, 5, None, None),
    ],
)
def test_staging_placement(inside: bool, staging_dev: int | None, raw_dev: int | None, expected) -> None:
    assert sp.staging_placement(inside, staging_dev, raw_dev) == expected


def test_device_of_reads_st_dev_and_tolerates_missing(tmp_path: Path) -> None:
    assert sp._device_of(str(tmp_path)) == tmp_path.stat().st_dev
    assert sp._device_of(str(tmp_path / "gone")) is None
    assert sp._device_of(None) is None


def test_root_placement_is_only_set_for_staging(tmp_path: Path) -> None:
    roots = {"RAW_ROOT": str(tmp_path), "STAGING_ROOT": str(tmp_path)}
    assert sp.root_placement("RAW_ROOT", roots, base_settings) is None


def test_root_placement_inside_raw_when_staging_is_unset(tmp_path: Path) -> None:
    cfg = base_settings.model_copy(update={"ARM_HOST_STAGING_PATH": ""})
    roots = {"RAW_ROOT": str(tmp_path), "STAGING_ROOT": str(tmp_path / ".staging")}
    assert sp.root_placement("STAGING_ROOT", roots, cfg) == StoragePlacement.INSIDE_RAW


def test_root_placement_same_device_for_a_separate_path_on_one_disk(tmp_path: Path) -> None:
    (tmp_path / "raw").mkdir()
    (tmp_path / "stage").mkdir()
    cfg = base_settings.model_copy(update={"ARM_HOST_RAW_PATH": "/h/raw", "ARM_HOST_STAGING_PATH": "/h/stage"})
    roots = {"RAW_ROOT": str(tmp_path / "raw"), "STAGING_ROOT": str(tmp_path / "stage")}
    assert sp.root_placement("STAGING_ROOT", roots, cfg) == StoragePlacement.SAME_DEVICE


def test_root_placement_separate_device(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = base_settings.model_copy(update={"ARM_HOST_RAW_PATH": "/h/raw", "ARM_HOST_STAGING_PATH": "/h/stage"})
    monkeypatch.setattr(sp, "_device_of", lambda path: 2 if path == "/staging" else 1)
    roots = {"RAW_ROOT": "/raw", "STAGING_ROOT": "/staging"}
    assert sp.root_placement("STAGING_ROOT", roots, cfg) == StoragePlacement.SEPARATE_DEVICE


def test_root_placement_unknown_when_staging_is_missing(tmp_path: Path) -> None:
    cfg = base_settings.model_copy(update={"ARM_HOST_RAW_PATH": "/h/raw", "ARM_HOST_STAGING_PATH": "/h/stage"})
    roots = {"RAW_ROOT": str(tmp_path), "STAGING_ROOT": str(tmp_path / "gone")}
    assert sp.root_placement("STAGING_ROOT", roots, cfg) is None
