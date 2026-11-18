"""Reachable families and rules 6 to 11 of HandBrake settings validation."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from arm_common.enums import TranscodeTool
from arm_common.handbrake_schema.reach import base_families, reachable_families
from arm_common.handbrake_schema.effective import UnknownBasePreset
from arm_common.handbrake_schema.types import HandbrakeSchema
from arm_common.handbrake_schema.validate import validate_family, validate_settings
from arm_common.schemas.handbrake import HandbrakeSettings, SettingIssue


def codes(issues: list[SettingIssue]) -> list[tuple[str, str]]:
    return [(i.key, i.code) for i in issues]


def blocks(**by_family: dict[str, Any]) -> HandbrakeSettings:
    return HandbrakeSettings(encoders=by_family)


def check(
    schema: HandbrakeSchema,
    settings: HandbrakeSettings | None,
    encoder_id: str = "any_h264",
    ref: str | None = None,
    tool: TranscodeTool = TranscodeTool.HANDBRAKE,
) -> list[tuple[str, str]]:
    return codes(validate_settings(schema, tool=tool, encoder_id=encoder_id, preset_ref=ref, settings=settings))


def test_any_h264_reaches_gpu_families_then_cpu(hb_schema):
    assert reachable_families(hb_schema, "any_h264", None) == ["nvenc_h264", "qsv_h264", "x264"]


def test_pinned_and_cpu(hb_schema):
    assert reachable_families(hb_schema, "nvenc_h265", None) == ["nvenc_h265"]
    assert reachable_families(hb_schema, "cpu_av1", None) == ["svt_av1"]


def test_preset_encoder_uses_base_family(hb_schema):
    assert reachable_families(hb_schema, "preset", "H.265 MKV 1080p30") == ["x265"]
    assert reachable_families(hb_schema, "preset", None) == []


def test_base_families(hb_schema):
    assert base_families(hb_schema, "H.265 MKV 1080p30") == ["x265"]
    assert base_families(hb_schema, None) == []


def test_preset_encoder_with_base_lacking_encoder(hb_schema):
    schema = replace(hb_schema, builtin_presets={"Bare": {}})
    assert reachable_families(schema, "preset", "Bare") == []


def test_vaapi_reaches_nothing(hb_schema):
    assert reachable_families(hb_schema, "vaapi_h264", None) == []


def test_unknown_base_raises_from_reachable_families(hb_schema):
    with pytest.raises(UnknownBasePreset):
        reachable_families(hb_schema, "preset", "No Such Preset")


@pytest.mark.parametrize("settings", [None, HandbrakeSettings(), blocks(x264={})])
def test_nothing_to_validate(hb_schema, settings):
    assert check(hb_schema, settings, "vaapi_h264") == []


def test_block_for_unreachable_family(hb_schema):
    assert check(hb_schema, blocks(x265={"bit_depth": 8})) == [("x265", "encoder_not_reachable")]


def test_block_for_family_unknown_to_the_schema(hb_schema):
    assert check(hb_schema, blocks(bogus={"bit_depth": 8})) == [("bogus", "encoder_not_reachable")]


def test_issue_names_its_block(hb_schema):
    issue = validate_settings(
        hb_schema,
        tool=TranscodeTool.HANDBRAKE,
        encoder_id="any_h264",
        preset_ref=None,
        settings=blocks(x264={"bit_depth": 9}),
    )[0]
    assert (issue.encoder, issue.key, issue.code) == ("x264", "bit_depth", "not_in_list")


def test_settings_on_vaapi_pin(hb_schema):
    assert check(hb_schema, blocks(x264={"bit_depth": 8}), "vaapi_h264") == [
        ("handbrake_settings", "engine_ignores_settings")
    ]


def test_settings_with_non_handbrake_tool(hb_schema):
    settings = HandbrakeSettings(common={"PictureWidth": 1280})
    assert check(hb_schema, settings, "preset", tool=TranscodeTool.NONE) == [
        ("handbrake_settings", "engine_ignores_settings")
    ]


def test_unknown_base_with_settings(hb_schema):
    settings = HandbrakeSettings(common={"PictureWidth": 1280})
    assert check(hb_schema, settings, "any_h264", "No Such Preset") == [("preset_ref", "not_in_list")]


def test_common_issues_are_included(hb_schema):
    assert check(hb_schema, HandbrakeSettings(common={"Nope": 1})) == [("Nope", "unknown_key")]


def test_unknown_block_key(hb_schema):
    assert check(hb_schema, blocks(x264={"Bogus": 1, "bit_depth": 8, "VideoOptionExtra": "a=b"})) == [
        ("Bogus", "unknown_key")
    ]


def test_bit_depth_not_offered(hb_schema):
    assert check(hb_schema, blocks(nvenc_h264={"bit_depth": 10})) == [("bit_depth", "not_in_list")]


def test_bit_depth_bool_is_not_a_depth(hb_schema):
    assert check(hb_schema, blocks(x264={"bit_depth": True})) == [("bit_depth", "not_in_list")]


def test_bit_depth_10_uses_the_10_bit_lists(hb_schema):
    assert check(hb_schema, blocks(x265={"bit_depth": 10, "VideoProfile": "main10"}), "cpu_h265") == []
    assert check(hb_schema, blocks(x265={"bit_depth": 10, "VideoProfile": "main"}), "cpu_h265") == [
        ("VideoProfile", "not_in_list")
    ]


def test_slower_valid_for_nvenc_and_x264_not_qsv(hb_schema):
    for family, expected in (("nvenc_h264", []), ("x264", []), ("qsv_h264", [("VideoPreset", "not_in_list")])):
        assert check(hb_schema, blocks(**{family: {"VideoPreset": "slower"}})) == expected


def test_profile_level_and_tune_lists(hb_schema):
    block = {"VideoProfile": "nope", "VideoLevel": "9.9", "VideoTune": "film,bogus"}
    assert check(hb_schema, blocks(x264=block)) == [
        ("VideoTune", "not_in_list"),
        ("VideoProfile", "not_in_list"),
        ("VideoLevel", "not_in_list"),
    ]


def test_tune_lists_accept_several_and_unset(hb_schema):
    for tune in ("film,fastdecode", "none", "", None):
        assert check(hb_schema, blocks(x264={"VideoTune": tune})) == []


def test_non_string_tune_is_not_in_list(hb_schema):
    assert check(hb_schema, blocks(x264={"VideoTune": 3})) == [("VideoTune", "not_in_list")]


def test_quality_step_and_range(hb_schema):
    def quality(value: Any) -> list[tuple[str, str]]:
        return check(hb_schema, blocks(svt_av1={"VideoQualitySlider": value}), "cpu_av1")

    assert quality(70.1) == [("VideoQualitySlider", "out_of_range")]
    assert quality(0.3) == [("VideoQualitySlider", "out_of_range")]
    assert quality(69.75) == []


def test_quality_step_tolerates_float_error(hb_schema):
    assert check(hb_schema, blocks(x264={"VideoQualitySlider": 18.3})) == []


def test_int_accepted_for_float_quality(hb_schema):
    assert check(hb_schema, blocks(nvenc_h264={"VideoQualitySlider": 18})) == []


def test_quality_must_be_a_number(hb_schema):
    assert check(hb_schema, blocks(x264={"VideoQualitySlider": "high"})) == [("VideoQualitySlider", "wrong_type")]
    assert check(hb_schema, blocks(x264={"VideoQualitySlider": True})) == [("VideoQualitySlider", "wrong_type")]


def test_rule_11_multipass_on_gpu_block(hb_schema):
    assert check(hb_schema, blocks(nvenc_h264={"VideoMultiPass": True})) == [
        ("VideoMultiPass", "not_supported_by_encoder")
    ]
    assert check(hb_schema, blocks(x264={"VideoMultiPass": True, "VideoTurboMultiPass": True})) == []


def test_rule_11_turbo_needs_the_turbo_flag(hb_schema):
    assert check(hb_schema, blocks(svt_av1={"VideoMultiPass": True, "VideoTurboMultiPass": True}), "cpu_av1") == [
        ("VideoTurboMultiPass", "not_supported_by_encoder")
    ]


def test_rule_11_advanced_options_off_x264(hb_schema):
    assert check(hb_schema, blocks(x265={"x264UseAdvancedOptions": True}), "cpu_h265") == [
        ("x264UseAdvancedOptions", "not_supported_by_encoder")
    ]
    assert check(hb_schema, blocks(x264={"x264UseAdvancedOptions": True})) == []
    assert check(hb_schema, blocks(x265={"x264Option": "ref=4"}), "cpu_h265") == [
        ("x264Option", "not_supported_by_encoder")
    ]
    assert check(hb_schema, blocks(x264={"x264Option": "ref=4"})) == []


def test_rule_10_rate_control(hb_schema):
    family = replace(hb_schema.families["x264"], rate_controls=frozenset({2}))
    schema = replace(hb_schema, families={**hb_schema.families, "x264": family})
    average_bitrate = HandbrakeSettings(common={"VideoQualityType": 1})
    assert check(schema, average_bitrate, "cpu_h264") == [("VideoQualityType", "not_supported_by_encoder")]
    assert check(schema, HandbrakeSettings(common={"VideoQualityType": 2}), "cpu_h264") == []


def test_validate_family_inherited_quality_out_of_range(hb_schema):
    settings = HandbrakeSettings()
    issues = validate_family(hb_schema, family="nvenc_h264", preset_ref="Preservation FFV1", settings=settings)
    assert [(i.encoder, i.key, i.code) for i in issues] == [("nvenc_h264", "VideoQualitySlider", "out_of_range")]


def test_validate_settings_flags_inherited_quality_on_save(hb_schema):
    settings = HandbrakeSettings(common={"PictureWidth": 1280})
    assert ("VideoQualitySlider", "out_of_range") in check(hb_schema, settings, "nvenc_h264", "Preservation FFV1")


def test_explicit_quality_replaces_the_inherited_one(hb_schema):
    settings = blocks(nvenc_h264={"VideoQualitySlider": 20})
    assert validate_family(hb_schema, family="nvenc_h264", preset_ref="Preservation FFV1", settings=settings) == []


def test_inherited_quality_skipped_for_a_bad_depth(hb_schema):
    settings = blocks(nvenc_h264={"bit_depth": 10})
    issues = validate_family(hb_schema, family="nvenc_h264", preset_ref="Preservation FFV1", settings=settings)
    assert codes(issues) == [("bit_depth", "not_in_list")]


def test_inherited_quality_not_a_number_is_left_to_common(hb_schema):
    schema = replace(hb_schema, builtin_presets={"Odd": {"VideoQualitySlider": "x"}})
    assert validate_family(schema, family="x264", preset_ref="Odd", settings=HandbrakeSettings()) == []


def test_validate_family_missing_block_is_valid(hb_schema):
    assert validate_family(hb_schema, family="x264", preset_ref=None, settings=HandbrakeSettings()) == []


def test_validate_family_checks_the_block(hb_schema):
    settings = blocks(x264={"VideoPreset": "nope", "Bogus": 1})
    assert codes(validate_family(hb_schema, family="x264", preset_ref=None, settings=settings)) == [
        ("VideoPreset", "not_in_list")
    ]


def test_validate_family_unknown_to_schema(hb_schema):
    issues = validate_family(hb_schema, family="nvenc_av1x", preset_ref=None, settings=HandbrakeSettings())
    assert codes(issues) == [("nvenc_av1x", "encoder_not_reachable")]
