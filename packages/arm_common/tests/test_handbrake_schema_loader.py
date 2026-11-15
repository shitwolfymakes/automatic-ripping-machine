"""The libhb schema dump plus the overlay load into a HandbrakeSchema."""

from __future__ import annotations

import copy
import json
import logging

import pytest

from arm_common.handbrake_schema.loader import content_hash, family_and_depth, load_schema, tab_for_key
from arm_common.handbrake_schema.overlay import (
    ARM_OWNED_KEYS,
    DEFAULT_RATE_CONTROLS,
    ENCODER_SPECIFIC_KEYS,
    FILTER_TAB_KEYS,
    FLAG_KEYS,
    KEY_OVERLAY,
    QSV_QUALITY_FALLBACK,
    STATIC_ENUMS,
    TURBO_FAMILIES,
)
from arm_common.handbrake_schema.types import QualityLimits


def test_loads_every_template_key(hb_schema):
    assert len(hb_schema.keys) == 103
    assert hb_schema.preset_version == (72, 0, 0)
    assert hb_schema.handbrake_tag == "1.11.1"


def test_key_types_come_from_the_template_defaults(hb_schema):
    types = {k: v.type for k, v in hb_schema.keys.items()}
    assert types["Optimize"] == "bool"
    assert types["PictureWidth"] == "int"
    assert types["VideoQualitySlider"] == "float"
    assert types["VideoEncoder"] == "str"
    assert types["AudioCopyMask"] == "list_str"
    assert types["AudioList"] == "list_obj"
    assert hb_schema.keys["VideoPreset"].default == "medium"


def test_audio_item_keys_are_the_eleven_template_audio_keys(hb_schema):
    assert len(hb_schema.audio_item_keys) == 11
    assert hb_schema.audio_item_keys["AudioMixdown"].source.kind == "audio_mixdowns"
    assert hb_schema.audio_item_keys["AudioTrackGainSlider"].limits == (-20, 20)


def test_family_and_depth_prefers_suffix_over_libhb_depth():
    assert family_and_depth("vce_av1_10bit", 8) == ("vce_av1", 10)
    assert family_and_depth("x265_12bit", 12) == ("x265", 12)
    assert family_and_depth("nvenc_h264", 8) == ("nvenc_h264", 8)


def test_families_group_depth_variants(hb_schema):
    x265 = hb_schema.families["x265"]
    assert set(x265.variants) == {8, 10, 12}
    assert x265.variants[10].encoder == "x265_10bit"
    assert x265.turbo and x265.multipass
    assert not hb_schema.families["nvenc_h265"].multipass
    assert not hb_schema.families["nvenc_h265"].turbo
    assert x265.rate_controls == DEFAULT_RATE_CONTROLS
    assert set(hb_schema.families["vce_av1"].variants) == {8, 10}


def test_variant_carries_encoder_lists(hb_schema, hb_raw):
    x264 = hb_schema.families["x264"].variants[8]
    assert "medium" in x264.presets
    assert "film" in x264.tunes
    assert "high" in x264.profiles
    assert "4.1" in x264.levels
    raw_x264 = next(e for e in hb_raw["video_encoders"] if e["name"] == "x264")
    assert hb_schema.families["x264"].codec_id == raw_x264["codec_id"]


@pytest.mark.parametrize(
    ("family", "depth", "limits"),
    [
        ("x264", 8, (0, 51, 0.1)),
        ("x264", 10, (-12, 51, 0.1)),
        ("nvenc_h264", 8, (1, 51, 0.1)),
        ("nvenc_av1", 8, (1, 63, 0.1)),
        ("svt_av1", 8, (0, 70, 0.25)),
        ("vce_h265", 8, (0, 51, None)),
        ("vce_av1", 8, (0, 255, None)),
    ],
)
def test_quality_limits(hb_schema, family, depth, limits):
    quality = hb_schema.families[family].variants[depth].quality
    assert (quality.low, quality.high) == limits[:2]
    if limits[2] is not None:
        assert quality.step == pytest.approx(limits[2])


def test_qsv_falls_back_to_overlay_range(hb_schema):
    assert hb_schema.families["qsv_h264"].variants[8].quality == QSV_QUALITY_FALLBACK
    assert QSV_QUALITY_FALLBACK == QualityLimits(1, 51, 1, "ICQ")


def test_every_encoder_family_is_kept(hb_schema):
    assert {"theora", "VP9", "mpeg2", "dnxhr", "vt_h264", "qsv_av1"} <= set(hb_schema.families)


def test_lists(hb_schema):
    lists = hb_schema.lists
    assert "av_aac" in lists["audio_encoders"]
    assert "stereo" in lists["mixdowns"]
    rates = lists["audio_samplerates"]
    assert {"48", "44.1", "22.05", "11.025", "8"} <= set(rates)
    assert 48000 not in rates
    assert len(rates) == len(set(rates))
    assert 160 in lists["audio_bitrates"]
    assert "triangular" in lists["audio_dithers"]
    assert "23.976" in lists["video_framerates"]
    assert "auto" not in lists["video_framerates"]
    assert lists["containers"] == ("av_mp4", "av_mov", "av_mkv", "av_webm")
    assert "stereo" in lists["audio_mixdowns_by_encoder"]["av_aac"]


def test_filters(hb_schema):
    assert len(hb_schema.filters) == 12
    assert "ultralight" in hb_schema.filters["nlmeans"].presets
    assert "film" in hb_schema.filters["nlmeans"].tunes
    assert hb_schema.filters["yadif"].tunes == ()


def test_builtin_presets_and_hash(hb_schema, hb_raw):
    assert len(hb_schema.builtin_presets) == 106
    assert hb_schema.content_hash == content_hash(hb_raw)


def test_prefix_tab_rule():
    assert tab_for_key("ChapterMarkers", frozenset()) == "chapters"
    assert tab_for_key("MetadataPassthru", frozenset()) == "summary"
    assert tab_for_key("PictureDenoiseFilter", frozenset({"PictureDenoiseFilter"})) == "filters"
    assert tab_for_key("PictureWidth", frozenset()) == "dimensions"
    assert tab_for_key("AudioCopyMask", frozenset()) == "audio"
    assert tab_for_key("SubtitleAddCC", frozenset()) == "subtitles"
    assert tab_for_key("VideoPreset", frozenset()) == "video"


def test_overlay_constants():
    assert len(ARM_OWNED_KEYS) == 11
    assert {"PresetName", "VideoEncoder", "FileFormat", "VideoHWDecode"} <= ARM_OWNED_KEYS
    assert ENCODER_SPECIFIC_KEYS == {
        "VideoPreset",
        "VideoTune",
        "VideoProfile",
        "VideoLevel",
        "VideoOptionExtra",
        "VideoQualitySlider",
        "VideoMultiPass",
        "VideoTurboMultiPass",
        "x264UseAdvancedOptions",
        "x264Option",
    }
    assert FLAG_KEYS["VideoOptionExtra"] == "--encopts"
    assert TURBO_FAMILIES == {"x264", "x265"}
    assert STATIC_ENUMS["VideoFramerateMode"] == ("vfr", "cfr", "pfr")
    assert FILTER_TAB_KEYS <= set(KEY_OVERLAY)


def test_overlay_covers_every_non_owned_template_key(hb_schema):
    unknown = {k for k, v in hb_schema.keys.items() if not v.known}
    assert unknown == set()


def test_static_and_bound_sources(hb_schema):
    keys = hb_schema.keys
    assert keys["VideoFramerateMode"].source.kind == "static"
    assert keys["VideoFramerateMode"].source.ref == "VideoFramerateMode"
    assert keys["VideoFramerate"].source.kind == "schema_list"
    assert keys["PictureDenoisePreset"].source.kind == "filter_presets"
    assert keys["PictureDenoiseTune"].source.kind == "filter_tunes"
    assert keys["PictureDeblockTune"].source.kind == "filter_tunes"
    assert keys["Optimize"].source is None


def test_key_missing_from_overlay_is_still_a_setting(hb_raw, caplog):
    caplog.set_level(logging.INFO)
    raw = copy.deepcopy(hb_raw)
    raw["preset_template"]["BrandNewKey"] = True
    schema = load_schema(raw)
    assert schema.keys["BrandNewKey"].known is False
    assert schema.keys["BrandNewKey"].type == "bool"
    assert schema.keys["BrandNewKey"].group == "Other"
    assert schema.keys["BrandNewKey"].label == "Brand new key"
    assert schema.keys["BrandNewKey"].tab == "summary"
    assert "BrandNewKey" in caplog.text


def test_overlay_entry_for_vanished_key_is_ignored(hb_raw, caplog):
    caplog.set_level(logging.INFO)
    raw = copy.deepcopy(hb_raw)
    del raw["preset_template"]["PictureDeblockTune"]
    schema = load_schema(raw)
    assert "PictureDeblockTune" not in schema.keys
    assert "PictureDeblockTune" in caplog.text


def test_clean_load_logs_nothing_missing(hb_raw, caplog):
    caplog.set_level(logging.INFO)
    load_schema(hb_raw)
    assert "missing" not in caplog.text


def test_content_hash_is_stable_and_order_independent(hb_raw):
    assert content_hash(hb_raw) == content_hash(json.loads(json.dumps(hb_raw, sort_keys=False)))
    changed = copy.deepcopy(hb_raw)
    changed["handbrake_tag"] = "other"
    assert content_hash(changed) != content_hash(hb_raw)


def test_keys_follow_overlay_row_order_with_unknown_keys_last(hb_schema):
    from arm_common.handbrake_schema.overlay import KEY_OVERLAY

    names = list(hb_schema.keys)
    known = [n for n in names if n in KEY_OVERLAY]
    assert known == [n for n in KEY_OVERLAY if n in hb_schema.keys]
    assert names[: len(known)] == known


def test_dimensions_keys_are_grouped_in_purpose_order(hb_schema):
    dimensions = [k for k in hb_schema.keys.values() if k.tab == "dimensions"]
    groups = list(dict.fromkeys(k.group for k in dimensions))
    assert groups == ["Size", "Cropping", "Pixel aspect", "Padding", "Orientation"]
    sides = ("Top", "Bottom", "Left", "Right")
    crop = [k.name for k in dimensions if k.name in {f"Picture{s}Crop" for s in sides}]
    assert crop == [f"Picture{s}Crop" for s in sides]
