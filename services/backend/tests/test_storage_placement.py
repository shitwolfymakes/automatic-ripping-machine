"""Where staging sits relative to raw: the pure decision and the stat-ing wrapper."""

from __future__ import annotations

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


def _cache_devices(monkeypatch: pytest.MonkeyPatch, devices: dict[str, int]) -> None:
    monkeypatch.setattr(sp, "get_device", lambda path: devices.get(path))


def test_root_placement_is_only_set_for_staging() -> None:
    roots = {"RAW_ROOT": "/raw", "STAGING_ROOT": "/staging"}
    assert sp.root_placement("RAW_ROOT", roots, base_settings) is None


def test_root_placement_inside_raw_when_staging_is_unset() -> None:
    cfg = base_settings.model_copy(update={"ARM_HOST_STAGING_PATH": ""})
    roots = {"RAW_ROOT": "/raw", "STAGING_ROOT": "/raw/.staging"}
    assert sp.root_placement("STAGING_ROOT", roots, cfg) == StoragePlacement.INSIDE_RAW


_OUTSIDE = base_settings.model_copy(update={"ARM_HOST_RAW_PATH": "/h/raw", "ARM_HOST_STAGING_PATH": "/h/stage"})
_ROOTS = {"RAW_ROOT": "/raw", "STAGING_ROOT": "/staging"}


def test_root_placement_same_device_for_a_separate_path_on_one_disk(monkeypatch: pytest.MonkeyPatch) -> None:
    _cache_devices(monkeypatch, {"/raw": 1, "/staging": 1})
    assert sp.root_placement("STAGING_ROOT", _ROOTS, _OUTSIDE) == StoragePlacement.SAME_DEVICE


def test_root_placement_separate_device(monkeypatch: pytest.MonkeyPatch) -> None:
    _cache_devices(monkeypatch, {"/raw": 1, "/staging": 2})
    assert sp.root_placement("STAGING_ROOT", _ROOTS, _OUTSIDE) == StoragePlacement.SEPARATE_DEVICE


def test_root_placement_unknown_before_the_refresher_has_cached_both(monkeypatch: pytest.MonkeyPatch) -> None:
    _cache_devices(monkeypatch, {"/raw": 1})
    assert sp.root_placement("STAGING_ROOT", _ROOTS, _OUTSIDE) is None


def test_root_placement_unknown_without_a_staging_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _cache_devices(monkeypatch, {"/raw": 1})
    assert sp.root_placement("STAGING_ROOT", {"RAW_ROOT": "/raw"}, _OUTSIDE) is None
