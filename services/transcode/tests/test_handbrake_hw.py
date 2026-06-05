"""Phase 7b: `_hw_encoder_args()` reads ARM_GPU_VENDOR + ARM_GPU_CODEC and
returns the right HandBrake `--encoder` flag.
"""

from __future__ import annotations

from typing import Iterator

import pytest

from arm_transcode.handbrake import _HW_ENCODER_TABLE, _hw_encoder_args


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.delenv("ARM_GPU_VENDOR", raising=False)
    monkeypatch.delenv("ARM_GPU_CODEC", raising=False)
    yield


def test_no_env_returns_empty(clean_env: None) -> None:
    assert _hw_encoder_args() == []


@pytest.mark.parametrize(
    "vendor,codec,expected",
    [
        ("vaapi", "h264", "vaapi_h264"),
        ("vaapi", "h265", "vaapi_h265"),
        ("qsv", "h264", "qsv_h264"),
        ("qsv", "h265", "qsv_h265"),
        ("nvenc", "h264", "nvenc_h264"),
        ("nvenc", "h265", "nvenc_h265"),
    ],
)
def test_known_combinations(monkeypatch: pytest.MonkeyPatch, vendor: str, codec: str, expected: str) -> None:
    monkeypatch.setenv("ARM_GPU_VENDOR", vendor)
    monkeypatch.setenv("ARM_GPU_CODEC", codec)
    assert _hw_encoder_args() == ["--encoder", expected]


def test_unknown_vendor_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unrecognised vendor falls through (CPU encoder from preset wins)."""
    monkeypatch.setenv("ARM_GPU_VENDOR", "amf")  # AMD AMF: not in the Phase 7b table
    monkeypatch.setenv("ARM_GPU_CODEC", "h265")
    assert _hw_encoder_args() == []


def test_av1_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """AV1 isn't on the Phase 7b matrix; preset's CPU encoder runs."""
    monkeypatch.setenv("ARM_GPU_VENDOR", "nvenc")
    monkeypatch.setenv("ARM_GPU_CODEC", "av1")
    assert _hw_encoder_args() == []


def test_partial_env_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vendor without codec, or vice versa, falls back to CPU."""
    monkeypatch.setenv("ARM_GPU_VENDOR", "vaapi")
    monkeypatch.delenv("ARM_GPU_CODEC", raising=False)
    assert _hw_encoder_args() == []


def test_table_covers_all_six_combinations() -> None:
    """Sanity check: every (vendor, codec) tuple yields a non-empty mapping."""
    expected_pairs = {
        ("vaapi", "h264"),
        ("vaapi", "h265"),
        ("qsv", "h264"),
        ("qsv", "h265"),
        ("nvenc", "h264"),
        ("nvenc", "h265"),
    }
    assert set(_HW_ENCODER_TABLE.keys()) == expected_pairs
