"""The claim-time settings filters in gpu_claim: which families a preset's HandBrake settings make
invalid, and how that prunes the devices and the CPU fallback."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from arm_backend.gpu_claim import (
    GpuAssignment,
    assignment_when_only_family_invalid,
    assignment_with_no_candidate,
    exclude_ffmpeg_engine,
    exclude_invalid_families,
    has_handbrake_settings,
    invalid_families,
    invalid_families_or_failure,
    invalid_settings_reason,
)
from arm_common import Gpu, GpuStatus, GpuVendor, TranscodePreset
from arm_common.encoders import get_encoder
from arm_common.enums import ContainerFormat, MediaType, TranscodeTool
from arm_common.handbrake_schema.effective import UnknownBasePreset
from arm_common.schemas import SettingIssue
from tests._hb_schema import fixture_schema

BASE = "H.264 MKV 1080p30"


def _preset(encoder: str = "any_h264", settings: dict[str, Any] | None = None, preset_ref: str | None = BASE):
    return TranscodePreset(
        id="tpr_x",
        name="p",
        media_type=MediaType.MOVIE,
        is_builtin=False,
        tool=TranscodeTool.HANDBRAKE,
        preset_ref=preset_ref,
        container=ContainerFormat.MKV,
        encoder=encoder,
        handbrake_settings=settings,
    )


def _bad(*families: str) -> dict[str, Any]:
    return {"common": {}, "encoders": {f: {"VideoPreset": "nope"} for f in families}}


def _gpu(vendor: GpuVendor, i: int = 0) -> Gpu:
    return Gpu(
        id=f"gpu_{i}",
        vendor=vendor,
        device_path=f"/dev/dri/renderD{128 + i}",
        encoder_kinds=["h264"],
        status=GpuStatus.AVAILABLE,
        probed_at=datetime.now(UTC),
    )


def _issue(family: str, message: str) -> SettingIssue:
    return SettingIssue(key="VideoPreset", encoder=family, code="not_in_list", message=message)


# --- has_handbrake_settings ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("settings", "expected"),
    [(None, False), ({}, False), ({"common": {}, "encoders": {"x264": {}}}, False), (_bad("x264"), True)],
)
def test_has_handbrake_settings(settings: dict[str, Any] | None, expected: bool) -> None:
    assert has_handbrake_settings(_preset(settings=settings)) is expected


# --- invalid_families ---------------------------------------------------------------------------


def test_invalid_families_is_empty_without_a_schema() -> None:
    assert invalid_families(None, _preset(settings=_bad("nvenc_h264"))) == {}


def test_invalid_families_is_empty_for_a_preset_without_settings() -> None:
    assert invalid_families(fixture_schema(), _preset(settings=None)) == {}


def test_invalid_families_lists_only_the_families_with_issues() -> None:
    invalid = invalid_families(fixture_schema(), _preset(settings=_bad("nvenc_h264", "x264")))
    assert list(invalid) == ["nvenc_h264", "x264"]
    assert invalid["nvenc_h264"][0].code == "not_in_list"


def test_invalid_families_is_empty_when_every_family_is_valid() -> None:
    settings = {"common": {}, "encoders": {"nvenc_h264": {"VideoPreset": "slow"}}}
    assert invalid_families(fixture_schema(), _preset(settings=settings)) == {}


def test_invalid_families_raises_for_an_unknown_base_preset() -> None:
    with pytest.raises(UnknownBasePreset):
        invalid_families(fixture_schema(), _preset(settings=_bad("x264"), preset_ref="No Such Preset"))


# --- invalid_families_or_failure ----------------------------------------------------------------


def test_invalid_families_or_failure_passes_the_map_through() -> None:
    result = invalid_families_or_failure(fixture_schema(), _preset(settings=_bad("x264")))
    assert isinstance(result, dict)
    assert list(result) == ["x264"]


def test_invalid_families_or_failure_fails_on_an_unknown_base_preset() -> None:
    result = invalid_families_or_failure(fixture_schema(), _preset(settings=_bad("x264"), preset_ref="No Such Preset"))
    assert result == GpuAssignment(
        gpu=None,
        encoder=None,
        action="fail",
        reason="HandBrake 1.11.1 has no built-in preset named 'No Such Preset'",
    )


# --- invalid_settings_reason --------------------------------------------------------------------


def test_invalid_settings_reason_lists_every_family_and_message() -> None:
    invalid = {"nvenc_h264": [_issue("nvenc_h264", "a"), _issue("nvenc_h264", "b")], "x264": [_issue("x264", "c")]}
    assert invalid_settings_reason(invalid) == "no valid encoder for this preset: nvenc_h264: a; b; x264: c"


# --- exclude_ffmpeg_engine ----------------------------------------------------------------------


def test_exclude_ffmpeg_engine_drops_vaapi_devices_for_a_preset_with_settings() -> None:
    gpus = [_gpu(GpuVendor.VAAPI, 0), _gpu(GpuVendor.QSV, 1)]
    assert exclude_ffmpeg_engine(gpus, _preset(settings=_bad("x264"))) == [gpus[1]]


def test_exclude_ffmpeg_engine_keeps_every_device_for_a_preset_without_settings() -> None:
    gpus = [_gpu(GpuVendor.VAAPI, 0), _gpu(GpuVendor.QSV, 1)]
    assert exclude_ffmpeg_engine(gpus, _preset(settings=None)) == gpus


# --- exclude_invalid_families -------------------------------------------------------------------


def test_exclude_invalid_families_drops_devices_of_an_invalid_family() -> None:
    gpus = [_gpu(GpuVendor.NVENC, 0), _gpu(GpuVendor.QSV, 1)]
    invalid = {"nvenc_h264": [_issue("nvenc_h264", "a")]}
    assert exclude_invalid_families(gpus, "h264", invalid) == [gpus[1]]


def test_exclude_invalid_families_keeps_a_device_with_no_encoder_for_the_codec() -> None:
    gpus = [_gpu(GpuVendor.NVENC, 0)]
    assert exclude_invalid_families(gpus, "vp9", {"nvenc_h264": [_issue("nvenc_h264", "a")]}) == gpus


def test_exclude_invalid_families_keeps_every_device_when_nothing_is_invalid() -> None:
    gpus = [_gpu(GpuVendor.NVENC, 0), _gpu(GpuVendor.VAAPI, 1)]
    assert exclude_invalid_families(gpus, "h264", {}) == gpus


# --- assignment_when_only_family_invalid --------------------------------------------------------


def test_only_family_invalid_leaves_an_any_encoder_to_the_device_lookup() -> None:
    invalid = {"x264": [_issue("x264", "c")]}
    assert assignment_when_only_family_invalid(get_encoder("any_h264"), invalid) is None


@pytest.mark.parametrize(
    "decided",
    [
        get_encoder("nvenc_h264"),
        GpuAssignment(gpu=None, encoder=get_encoder("cpu_h264"), action="spawn"),
        GpuAssignment(gpu=None, encoder=None, action="spawn"),
    ],
)
def test_only_family_invalid_passes_a_valid_single_family(decided: Any) -> None:
    assert assignment_when_only_family_invalid(decided, {}) is None


def test_only_family_invalid_fails_a_pinned_gpu_encoder() -> None:
    spec = get_encoder("nvenc_h264")
    result = assignment_when_only_family_invalid(spec, {"nvenc_h264": [_issue("nvenc_h264", "a")]})
    assert result == GpuAssignment(
        gpu=None, encoder=spec, action="fail", reason="no valid encoder for this preset: nvenc_h264: a"
    )


def test_only_family_invalid_fails_a_cpu_or_preset_spawn() -> None:
    cpu = get_encoder("cpu_h264")
    decided = GpuAssignment(gpu=None, encoder=cpu, action="spawn")
    result = assignment_when_only_family_invalid(decided, {"x264": [_issue("x264", "c")]})
    assert result == GpuAssignment(
        gpu=None, encoder=cpu, action="fail", reason="no valid encoder for this preset: x264: c"
    )


# --- assignment_with_no_candidate: the CPU fallback ---------------------------------------------


def _never_awaiting(_: Gpu) -> bool:
    return False


def test_cpu_fallback_spawns_when_the_cpu_family_is_valid() -> None:
    invalid = {"nvenc_h264": [_issue("nvenc_h264", "a")]}
    result = assignment_with_no_candidate(get_encoder("any_h264"), "h264", [], [], _never_awaiting, invalid)
    assert result == GpuAssignment(gpu=None, encoder=get_encoder("cpu_h264"), action="spawn")


def test_cpu_fallback_fails_with_every_family_when_the_cpu_family_is_invalid() -> None:
    invalid = {"nvenc_h264": [_issue("nvenc_h264", "a")], "x264": [_issue("x264", "c")]}
    result = assignment_with_no_candidate(get_encoder("any_h264"), "h264", [], [], _never_awaiting, invalid)
    assert result == GpuAssignment(
        gpu=None,
        encoder=get_encoder("cpu_h264"),
        action="fail",
        reason="no valid encoder for this preset: nvenc_h264: a; x264: c",
    )
