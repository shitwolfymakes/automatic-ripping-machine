"""Tests for the Backend GPU inventory loader.

The backend no longer probes hardware; it parses the `ARM_GPUS` JSON descriptor
written host-side at install time. These tests cover `load_configured_gpus` and
the per-entry validation in `_parse_entry`.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import json  # noqa: E402

import pytest  # noqa: E402

from arm_backend.gpu_probe import _DEFAULT_ENCODER_KINDS, load_configured_gpus  # noqa: E402
from arm_common.enums import GpuVendor  # noqa: E402


@pytest.mark.parametrize("raw", [None, "", "   ", "\n\t"])
def test_blank_descriptor_returns_empty(raw: str | None) -> None:
    assert load_configured_gpus(raw) == []


def test_invalid_json_returns_empty() -> None:
    assert load_configured_gpus("{not json") == []


def test_non_array_json_returns_empty() -> None:
    # A JSON object (not a list) is rejected wholesale.
    assert load_configured_gpus('{"vendor": "qsv"}') == []


def test_valid_single_entry() -> None:
    raw = json.dumps([{"vendor": "qsv", "device_path": "/dev/dri/renderD128", "encoder_kinds": ["h264", "h265"]}])
    gpus = load_configured_gpus(raw)
    assert len(gpus) == 1
    assert gpus[0].vendor == GpuVendor.QSV
    assert gpus[0].device_path == "/dev/dri/renderD128"
    assert gpus[0].encoder_kinds == ["h264", "h265"]


def test_mixed_vendors_all_parsed() -> None:
    raw = json.dumps(
        [
            {"vendor": "vaapi", "device_path": "/dev/dri/renderD128"},
            {"vendor": "nvenc", "device_path": "nvidia://0"},
            {"vendor": "qsv", "device_path": "/dev/dri/renderD129"},
        ]
    )
    gpus = load_configured_gpus(raw)
    assert [g.vendor for g in gpus] == [GpuVendor.VAAPI, GpuVendor.NVENC, GpuVendor.QSV]


def test_missing_encoder_kinds_defaults() -> None:
    raw = json.dumps([{"vendor": "nvenc", "device_path": "nvidia://0"}])
    gpus = load_configured_gpus(raw)
    assert gpus[0].encoder_kinds == _DEFAULT_ENCODER_KINDS
    assert gpus[0].encoder_kinds is not _DEFAULT_ENCODER_KINDS  # fresh copy, not the shared constant


@pytest.mark.parametrize("bad_kinds", [[], "h264", [1, 2], ["h264", 5]])
def test_malformed_encoder_kinds_falls_back_to_default(bad_kinds: object) -> None:
    raw = json.dumps([{"vendor": "vaapi", "device_path": "/dev/dri/renderD128", "encoder_kinds": bad_kinds}])
    gpus = load_configured_gpus(raw)
    assert gpus[0].encoder_kinds == _DEFAULT_ENCODER_KINDS


def test_non_object_entry_is_skipped() -> None:
    raw = json.dumps(["not-an-object", {"vendor": "qsv", "device_path": "/dev/dri/renderD128"}])
    gpus = load_configured_gpus(raw)
    assert len(gpus) == 1
    assert gpus[0].vendor == GpuVendor.QSV


def test_unknown_vendor_is_skipped() -> None:
    raw = json.dumps([{"vendor": "magic-gpu", "device_path": "/dev/dri/renderD128"}])
    assert load_configured_gpus(raw) == []


@pytest.mark.parametrize(
    "entry", [{"device_path": "/dev/dri/renderD128"}, {"vendor": 5, "device_path": "/dev/dri/renderD128"}]
)
def test_non_string_or_missing_vendor_is_skipped(entry: dict[str, object]) -> None:
    assert load_configured_gpus(json.dumps([entry])) == []


@pytest.mark.parametrize(
    "entry", [{"vendor": "qsv"}, {"vendor": "qsv", "device_path": ""}, {"vendor": "qsv", "device_path": 123}]
)
def test_missing_or_bad_device_path_is_skipped(entry: dict[str, object]) -> None:
    assert load_configured_gpus(json.dumps([entry])) == []
