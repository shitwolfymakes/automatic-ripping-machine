"""preset_view, host_notes and normalise_settings: the pure read-side helpers for transcode presets."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from arm_backend.preset_views import host_notes, normalise_settings, preset_view
from arm_common import ContainerFormat, Gpu, GpuVendor, MediaType, TranscodePreset, TranscodeTool
from arm_common.schemas import HandbrakeSettings

from tests._hb_schema import fixture_schema

_SETTINGS = {"common": {}, "encoders": {"nvenc_h264": {"VideoPreset": "slower"}}}
_NOW = datetime(2026, 1, 1, tzinfo=UTC)


def _preset(settings: dict | None = _SETTINGS, encoder: str = "any_h264") -> TranscodePreset:
    return TranscodePreset(
        id="tpr_x",
        name="x",
        media_type=MediaType.MOVIE,
        is_builtin=False,
        tool=TranscodeTool.HANDBRAKE,
        container=ContainerFormat.MKV,
        encoder=encoder,
        handbrake_settings=settings,
    )


def _gpu(vendor: GpuVendor, *, kinds: list[str] | None = None, enabled: bool = True, probed: bool = True) -> Gpu:
    return Gpu(
        id=f"gpu_{vendor.value}",
        vendor=vendor,
        device_path="/dev/dri/x",
        encoder_kinds=["h264"] if kinds is None else kinds,
        enabled=enabled,
        probed_at=_NOW if probed else None,
    )


def test_normalise_turns_none_and_empty_into_none() -> None:
    assert normalise_settings(None) is None
    assert normalise_settings(HandbrakeSettings()) is None


def test_normalise_dumps_non_empty_settings() -> None:
    settings = HandbrakeSettings.model_validate(_SETTINGS)
    assert normalise_settings(settings) == settings.model_dump()


def test_note_when_no_gpus() -> None:
    assert host_notes(_preset(), []) == ["encodes_on_cpu_here"]


def test_note_when_only_amd() -> None:
    assert host_notes(_preset(), [_gpu(GpuVendor.VAAPI)]) == ["encodes_on_cpu_here"]


def test_no_note_with_a_verified_nvidia_card_next_to_amd() -> None:
    assert host_notes(_preset(), [_gpu(GpuVendor.VAAPI), _gpu(GpuVendor.NVENC)]) == []


@pytest.mark.parametrize(
    "gpu",
    [
        _gpu(GpuVendor.NVENC, enabled=False),
        _gpu(GpuVendor.NVENC, probed=False),
        _gpu(GpuVendor.NVENC, kinds=["h265"]),
    ],
    ids=["disabled", "never probed", "other codec"],
)
def test_an_ineligible_nvidia_card_does_not_clear_the_note(gpu: Gpu) -> None:
    assert host_notes(_preset(), [gpu]) == ["encodes_on_cpu_here"]


def test_no_note_without_settings() -> None:
    assert host_notes(_preset(None), []) == []


@pytest.mark.parametrize("encoder", ["cpu_h264", "nvenc_h264", "preset"])
def test_no_note_for_a_pinned_or_cpu_encoder(encoder: str) -> None:
    assert host_notes(_preset(encoder=encoder), []) == []


def test_view_without_a_schema_has_no_issues() -> None:
    view = preset_view(_preset(), None, [_gpu(GpuVendor.NVENC)])
    assert view.issues == [] and view.host_notes == []
    assert view.handbrake_settings is not None and view.handbrake_settings.encoders == _SETTINGS["encoders"]


def test_view_without_settings_has_no_issues() -> None:
    view = preset_view(_preset(None), fixture_schema(), [])
    assert view.issues == [] and view.host_notes == [] and view.handbrake_settings is None


def test_view_carries_issues_and_notes() -> None:
    settings = {"common": {}, "encoders": {"nvenc_h264": {"VideoPreset": "warp"}}}
    view = preset_view(_preset(settings), fixture_schema(), [])
    assert [(i.key, i.code) for i in view.issues] == [("VideoPreset", "not_in_list")]
    assert view.host_notes == ["encodes_on_cpu_here"]


def test_normalise_strips_empty_encoder_blocks() -> None:
    """An empty block (the UI prunes them; a raw client may not) is dropped, not stored or validated."""
    settings = HandbrakeSettings(common={"PictureWidth": 1280}, encoders={"x265": {}, "x264": {"VideoPreset": "fast"}})
    assert normalise_settings(settings) == {
        "common": {"PictureWidth": 1280},
        "encoders": {"x264": {"VideoPreset": "fast"}},
    }


def test_normalise_turns_only_empty_blocks_into_none() -> None:
    assert normalise_settings(HandbrakeSettings(encoders={"x265": {}})) is None
