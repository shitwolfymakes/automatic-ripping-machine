"""Rules 1 to 5 of HandBrake settings validation, plus effective_value and base_preset."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from arm_common.handbrake_schema.effective import UnknownBasePreset, base_preset, effective_value
from arm_common.handbrake_schema.overlay import ARM_OWNED_KEYS, ENCODER_SPECIFIC_KEYS
from arm_common.handbrake_schema.types import HandbrakeSchema
from arm_common.handbrake_schema.validate import validate_common
from arm_common.schemas.handbrake import HandbrakeSettings, SettingIssue


def codes(issues: list[SettingIssue]) -> list[tuple[str, str]]:
    return [(i.key, i.code) for i in issues]


def check(schema: HandbrakeSchema, common: dict[str, Any], ref: str | None = None) -> list[tuple[str, str]]:
    return codes(validate_common(schema, ref, common))


def test_unknown_key(hb_schema):
    assert check(hb_schema, {"Nope": 1}) == [("Nope", "unknown_key")]


def test_arm_owned_key_not_allowed(hb_schema):
    assert check(hb_schema, {"VideoHWDecode": 1}) == [("VideoHWDecode", "not_allowed_here")]


def test_encoder_specific_key_not_allowed_in_common(hb_schema):
    assert check(hb_schema, {"VideoPreset": "slow"}) == [("VideoPreset", "not_allowed_here")]
    assert check(hb_schema, {"x264Option": "ref=4"}) == [("x264Option", "not_allowed_here")]


def test_bool_is_strict(hb_schema):
    assert check(hb_schema, {"ChapterMarkers": 1}) == [("ChapterMarkers", "wrong_type")]


def test_bool_is_not_an_int(hb_schema):
    assert check(hb_schema, {"PictureWidth": True}) == [("PictureWidth", "wrong_type")]


def test_int_accepted_for_float(hb_schema):
    assert check(hb_schema, {"AudioList": [{"AudioTrackQuality": 3}]}) == []


def test_str_and_lists_are_typed(hb_schema):
    assert check(hb_schema, {"PictureCropMode": 0, "AudioLanguageList": "eng", "AudioList": ["x"]}) == [
        ("AudioLanguageList", "wrong_type"),
        ("AudioList", "wrong_type"),
    ]


def test_audio_list_item_checked(hb_schema):
    assert check(hb_schema, {"AudioList": [{"AudioBitrate": "x"}]}) == [("AudioList[0].AudioBitrate", "wrong_type")]


def test_audio_list_unknown_item_key(hb_schema):
    assert check(hb_schema, {"AudioList": [{"Bogus": 1}]}) == [("AudioList[0].Bogus", "unknown_key")]


def test_mixdown_checked_against_track_encoder(hb_schema):
    by_encoder = hb_schema.lists["audio_mixdowns_by_encoder"]
    bad = next(m for m in hb_schema.lists["mixdowns"] if m not in by_encoder["av_aac"])
    good = by_encoder["av_aac"][0]
    item = {"AudioEncoder": "av_aac", "AudioMixdown": bad}
    assert check(hb_schema, {"AudioList": [item]}) == [("AudioList[0].AudioMixdown", "not_in_list")]
    assert check(hb_schema, {"AudioList": [{**item, "AudioMixdown": good}]}) == []


def test_mixdown_uses_template_encoder_when_item_has_none(hb_schema):
    default_encoder = hb_schema.audio_item_keys["AudioEncoder"].default
    allowed = hb_schema.lists["audio_mixdowns_by_encoder"][default_encoder]
    bad = next((m for m in hb_schema.lists["mixdowns"] if m not in allowed), None)
    assert bad is not None, "fixture fact: the template encoder does not allow every mixdown"
    assert check(hb_schema, {"AudioList": [{"AudioMixdown": bad}]}) == [("AudioList[0].AudioMixdown", "not_in_list")]


def test_mixdown_of_unlisted_encoder_is_unconstrained(hb_schema):
    assert check(hb_schema, {"AudioList": [{"AudioEncoder": "no_such", "AudioMixdown": "x"}]}) == [
        ("AudioList[0].AudioEncoder", "not_in_list")
    ]


def test_static_enum(hb_schema):
    assert check(hb_schema, {"VideoFramerateMode": "wobbly"}) == [("VideoFramerateMode", "not_in_list")]
    assert check(hb_schema, {"VideoFramerateMode": "cfr"}) == []


def test_issue_message_names_value_and_choices(hb_schema):
    [issue] = validate_common(hb_schema, None, {"VideoFramerateMode": "wobbly"})
    assert issue.message == "'wobbly' is not one of vfr, cfr, pfr"
    assert issue.encoder is None


def test_schema_list_and_list_valued_key(hb_schema):
    assert check(hb_schema, {"AudioCopyMask": ["copy:ac3", "copy:nope"]}) == [("AudioCopyMask", "not_in_list")]
    assert check(hb_schema, {"AudioEncoderFallback": "nope"}) == [("AudioEncoderFallback", "not_in_list")]


def test_source_extras_are_accepted(hb_schema):
    item = {"AudioSamplerate": "auto", "AudioBitrate": -1}
    assert check(hb_schema, {"VideoFramerate": "auto", "AudioList": [item]}) == []
    assert check(hb_schema, {"AudioList": [{"AudioSamplerate": "7", "AudioBitrate": 7}]}) == [
        ("AudioList[0].AudioSamplerate", "not_in_list"),
        ("AudioList[0].AudioBitrate", "not_in_list"),
    ]


def test_open_enum_accepts_any_string_but_not_other_types(hb_schema):
    assert check(hb_schema, {"PicturePadColor": "white"}) == []
    assert check(hb_schema, {"PicturePadColor": "#ff00ff"}) == []
    assert check(hb_schema, {"PicturePadColor": "navy"}) == []
    assert check(hb_schema, {"PicturePadColor": 5}) == [("PicturePadColor", "wrong_type")]


def test_closed_enum_still_rejects_unknown_values(hb_schema):
    assert check(hb_schema, {"VideoScaler": "bogus"}) == [("VideoScaler", "not_in_list")]
    assert check(hb_schema, {"PictureModulus": 3}) == [("PictureModulus", "not_in_list")]
    assert check(hb_schema, {"VideoColorMatrixCodeOverride": 9}) == [("VideoColorMatrixCodeOverride", "not_in_list")]


def test_filter_tune_follows_filter_after_base(hb_schema):
    schema = replace(hb_schema, builtin_presets={"Base": {"PictureSharpenFilter": "unsharp"}})
    lapsharp_only = next(t for t in hb_schema.filters["lapsharp"].tunes if t not in hb_schema.filters["unsharp"].tunes)
    unsharp_only = next(t for t in hb_schema.filters["unsharp"].tunes if t not in hb_schema.filters["lapsharp"].tunes)
    # The filter comes from the base preset.
    assert check(schema, {"PictureSharpenTune": lapsharp_only}, "Base") == [("PictureSharpenTune", "not_in_list")]
    assert check(schema, {"PictureSharpenTune": unsharp_only}, "Base") == []
    # common beats the base for the selector.
    assert check(schema, {"PictureSharpenFilter": "lapsharp", "PictureSharpenTune": lapsharp_only}, "Base") == []
    # Without a base the template default (off) names no filter, so nothing constrains the tune.
    assert check(schema, {"PictureSharpenTune": lapsharp_only}) == []


def test_filter_preset_follows_filter(hb_schema):
    assert check(hb_schema, {"PictureDenoiseFilter": "hqdn3d", "PictureDenoisePreset": "nope"}) == [
        ("PictureDenoisePreset", "not_in_list")
    ]
    assert check(hb_schema, {"PictureDenoiseFilter": "hqdn3d", "PictureDenoisePreset": "medium"}) == []


def test_filter_without_tunes_does_not_constrain_tune(hb_schema):
    assert check(hb_schema, {"PictureDenoiseFilter": "hqdn3d", "PictureDenoiseTune": "none"}) == []


def test_filter_tune_follows_filter(hb_schema):
    assert check(hb_schema, {"PictureSharpenFilter": "lapsharp", "PictureSharpenTune": "nope"}) == [
        ("PictureSharpenTune", "not_in_list")
    ]
    tune = hb_schema.filters["lapsharp"].tunes[0]
    assert check(hb_schema, {"PictureSharpenFilter": "lapsharp", "PictureSharpenTune": tune}) == []


def test_filter_named_directly_by_source(hb_schema):
    assert check(hb_schema, {"PictureDetelecine": "nope"}) == [("PictureDetelecine", "not_in_list")]
    assert check(hb_schema, {"PictureDetelecine": "default"}) == []


def test_selector_alias_resolves_to_libhb_filter(hb_schema):
    # "deinterlace" is yadif in libhb, which has a preset bwdif/decomb lack.
    only_yadif = next(p for p in hb_schema.filters["yadif"].presets if p not in hb_schema.filters["bwdif"].presets)
    assert check(hb_schema, {"PictureDeinterlaceFilter": "deinterlace", "PictureDeinterlacePreset": only_yadif}) == []
    assert check(hb_schema, {"PictureDeinterlaceFilter": "bwdif", "PictureDeinterlacePreset": only_yadif}) == [
        ("PictureDeinterlacePreset", "not_in_list")
    ]


def test_out_of_range(hb_schema):
    assert check(hb_schema, {"AudioList": [{"AudioTrackDRCSlider": 9}]}) == [
        ("AudioList[0].AudioTrackDRCSlider", "out_of_range")
    ]
    assert check(hb_schema, {"AudioList": [{"AudioTrackDRCSlider": 2.5, "AudioTrackGainSlider": -20}]}) == []


def test_fixture_common_is_clean(hb_schema, plex_export):
    preset = plex_export["PresetList"][0]
    skip = ARM_OWNED_KEYS | ENCODER_SPECIFIC_KEYS
    common = {k: v for k, v in preset.items() if k not in skip and k in hb_schema.keys}
    assert common
    assert check(hb_schema, common) == []


def test_effective_value_order(hb_schema):
    base = next(n for n, p in hb_schema.builtin_presets.items() if p.get("PictureWidth") not in (None, 0))
    base_width = hb_schema.builtin_presets[base]["PictureWidth"]
    template = hb_schema.keys["PictureWidth"].default
    none = HandbrakeSettings()
    assert effective_value(hb_schema, None, none, "PictureWidth") == template
    assert effective_value(hb_schema, base, none, "PictureWidth") == base_width
    assert effective_value(hb_schema, base, HandbrakeSettings(common={"PictureWidth": 1}), "PictureWidth") == 1


def test_base_preset(hb_schema):
    assert base_preset(hb_schema, None) == {}
    name = next(iter(hb_schema.builtin_presets))
    assert base_preset(hb_schema, name) is hb_schema.builtin_presets[name]


def test_unknown_base_preset(hb_schema):
    with pytest.raises(UnknownBasePreset, match=r"HandBrake 1\.11\.1 has no built-in preset named 'Nope'"):
        base_preset(hb_schema, "Nope")
    with pytest.raises(UnknownBasePreset):
        validate_common(hb_schema, "Nope", {})


def test_settings_is_empty():
    assert HandbrakeSettings().is_empty()
    assert HandbrakeSettings(encoders={"x264": {}}).is_empty()
    assert not HandbrakeSettings(common={"a": 1}).is_empty()
    assert not HandbrakeSettings(encoders={"x264": {"VideoPreset": "slow"}}).is_empty()


def test_unhashable_selector_is_only_a_type_issue(hb_schema):
    common = {"PictureSharpenFilter": [], "PictureSharpenTune": "x"}
    assert check(hb_schema, common) == [("PictureSharpenFilter", "wrong_type")]


def test_unhashable_track_encoder_is_only_a_type_issue(hb_schema):
    item = {"AudioEncoder": [], "AudioMixdown": "x"}
    assert check(hb_schema, {"AudioList": [item]}) == [("AudioList[0].AudioEncoder", "wrong_type")]
