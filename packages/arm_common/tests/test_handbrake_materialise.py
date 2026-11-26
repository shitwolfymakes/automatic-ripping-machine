"""resolve_depth and materialise: the one-preset file and encoder flags the transcoder runs."""

from __future__ import annotations

import copy

import pytest

from arm_common.enums import ContainerFormat
from arm_common.handbrake_schema.materialise import UnknownBasePreset, materialise, resolve_depth
from arm_common.schemas.handbrake import HandbrakeSettings

BASE = "H.265 MKV 1080p30"
MKV = ContainerFormat.MKV


def one(result):
    return result.preset_file["PresetList"][0]


def test_depth_from_block(hb_schema):
    assert resolve_depth(hb_schema, "x265", BASE, {"bit_depth": 8}) == 8


def test_depth_from_same_family_base(hb_schema):
    assert resolve_depth(hb_schema, "x265", BASE, {}) == 10


def test_depth_default_when_base_other_family(hb_schema):
    assert resolve_depth(hb_schema, "nvenc_h265", BASE, {}) == 8


def test_depth_default_without_base(hb_schema):
    assert resolve_depth(hb_schema, "x265", None, {}) == 8


def test_no_base_builds_empty_preset(hb_schema):
    settings = HandbrakeSettings(common={"PictureWidth": 1280})
    preset = one(materialise(hb_schema, None, settings, "x264", MKV))
    assert preset == {
        "PictureWidth": 1280,
        "PresetName": "arm",
        "Type": 1,
        "FileFormat": "av_mkv",
        "VideoHWDecode": 0,
    }


@pytest.mark.parametrize(
    ("container", "file_format"),
    [(ContainerFormat.MKV, "av_mkv"), (ContainerFormat.MP4, "av_mp4"), (ContainerFormat.WEBM, "av_webm")],
)
def test_file_format_from_container(hb_schema, container, file_format):
    assert one(materialise(hb_schema, None, HandbrakeSettings(), "x264", container))["FileFormat"] == file_format


def test_builtin_base_layered_with_common(hb_schema):
    base = hb_schema.builtin_presets[BASE]
    settings = HandbrakeSettings(common={"PictureWidth": 123})
    preset = one(materialise(hb_schema, BASE, settings, "x265", MKV))
    assert preset["PictureWidth"] == 123
    assert preset["PictureHeight"] == base["PictureHeight"]
    assert preset["VideoEncoder"] == base["VideoEncoder"]
    assert preset["PresetName"] == "arm"


def test_unknown_base_raises(hb_schema):
    with pytest.raises(UnknownBasePreset) as excinfo:
        materialise(hb_schema, "Nope", HandbrakeSettings(), "x264", MKV)
    assert str(excinfo.value) == f"HandBrake {hb_schema.handbrake_tag} has no built-in preset named 'Nope'"


def test_builtin_presets_not_mutated(hb_schema):
    before = copy.deepcopy(hb_schema.builtin_presets[BASE])
    settings = HandbrakeSettings(common={"PictureWidth": 123, "AudioList": [{"AudioEncoder": "x"}]})
    result = materialise(hb_schema, BASE, settings, "x265", MKV)
    one(result)["AudioList"].append("changed")
    assert hb_schema.builtin_presets[BASE] == before
    assert settings.common["AudioList"] == [{"AudioEncoder": "x"}]


def test_flags_for_block(hb_schema, plex_settings):
    flags = materialise(hb_schema, None, plex_settings, "nvenc_h264", MKV).flags
    assert flags == [
        "--encoder", "nvenc_h264", "--encoder-preset", "slower", "--encoder-profile", "main", "--encoder-level", "4.0",
    ]  # fmt: skip


def test_flags_in_flag_keys_order(hb_schema):
    block = {"VideoOptionExtra": "a=b", "VideoTune": "film", "VideoPreset": "fast"}
    settings = HandbrakeSettings(encoders={"x264": block})
    flags = materialise(hb_schema, None, settings, "x264", MKV).flags
    assert flags == ["--encoder", "x264", "--encoder-preset", "fast", "--encoder-tune", "film", "--encopts", "a=b"]


def test_flags_ten_bit_encoder_name(hb_schema):
    settings = HandbrakeSettings(encoders={"x265": {"bit_depth": 10}})
    assert materialise(hb_schema, None, settings, "x265", MKV).flags[:2] == ["--encoder", "x265_10bit"]


def test_flags_ten_bit_from_base(hb_schema):
    assert materialise(hb_schema, BASE, HandbrakeSettings(), "x265", MKV).flags == ["--encoder", "x265_10bit"]


def test_missing_block_only_encoder_flag(hb_schema):
    assert materialise(hb_schema, None, HandbrakeSettings(), "x264", MKV).flags == ["--encoder", "x264"]


def test_no_family_no_flags(hb_schema, plex_settings):
    """No family (the ``preset`` encoder without a base): no block, no flags."""
    result = materialise(hb_schema, None, plex_settings, None, MKV, emit_encoder=False)
    assert result.flags == []
    assert "VideoQualitySlider" not in one(result)


def test_preset_encoder_uses_base_family_block_without_encoder_flag(hb_schema):
    """The base family's block is written and flagged, but the base's own encoder is kept."""
    block = {"VideoPreset": "slow", "VideoQualitySlider": 20}
    settings = HandbrakeSettings(encoders={"x265": block})
    result = materialise(hb_schema, BASE, settings, "x265", MKV, emit_encoder=False)
    assert result.flags == ["--encoder-preset", "slow"]
    assert one(result)["VideoQualitySlider"] == 20
    assert one(result)["VideoEncoder"] == hb_schema.builtin_presets[BASE]["VideoEncoder"]


def test_x264_option_written_into_file_from_the_x264_block(hb_schema):
    settings = HandbrakeSettings(encoders={"x264": {"x264Option": "ref=4"}})
    result = materialise(hb_schema, None, settings, "x264", MKV)
    assert one(result)["x264Option"] == "ref=4"
    assert "ref=4" not in result.flags


def test_block_scalars_written_into_file(hb_schema):
    block = {"VideoQualitySlider": 22, "VideoMultiPass": True, "VideoPreset": "fast"}
    result = materialise(hb_schema, None, HandbrakeSettings(encoders={"x264": block}), "x264", MKV)
    assert one(result)["VideoQualitySlider"] == 22
    assert one(result)["VideoMultiPass"] is True
    assert "VideoPreset" not in one(result)
    assert "22" not in result.flags
    assert "VideoQualitySlider" not in result.flags


def test_other_family_block_ignored(hb_schema, plex_settings):
    result = materialise(hb_schema, None, plex_settings, "x264", MKV)
    assert result.flags == ["--encoder", "x264"]
    assert "VideoQualitySlider" not in one(result)


def test_base_encoder_keys_left_alone(hb_schema):
    base = hb_schema.builtin_presets[BASE]
    settings = HandbrakeSettings(encoders={"nvenc_h265": {"VideoPreset": "slow"}})
    preset = one(materialise(hb_schema, BASE, settings, "nvenc_h265", MKV))
    assert preset["VideoEncoder"] == base["VideoEncoder"]
    assert preset["VideoPreset"] == base["VideoPreset"]


def test_version_fields(hb_schema):
    result = materialise(hb_schema, None, HandbrakeSettings(), "x264", MKV)
    assert (result.preset_file["VersionMajor"], result.preset_file["VersionMinor"]) == (72, 0)
    assert result.preset_file["VersionMicro"] == 0
