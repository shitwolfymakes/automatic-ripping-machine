"""The slim HandBrake schema view served to the UI."""

from __future__ import annotations

from arm_common.handbrake_schema.overlay import ARM_OWNED_KEYS, ENCODER_SPECIFIC_KEYS
from arm_common.handbrake_schema.slim import slim_view


def test_slim_has_no_builtin_values(hb_schema):
    view = slim_view(hb_schema)
    assert len(view.builtin_names) == 106
    assert all(isinstance(n, str) for n in view.builtin_names)
    assert not any(isinstance(k.default, dict) and "PresetName" in k.default for k in view.keys)
    assert "PresetList" not in view.model_dump_json()


def test_slim_size_under_60kb(hb_schema):
    assert len(slim_view(hb_schema).model_dump_json()) < 60_000


def test_slim_family_carries_quality_name(hb_schema):
    family = next(f for f in slim_view(hb_schema).families if f.name == "nvenc_h264")
    variant = next(v for v in family.variants if v.depth == 8)
    assert variant.quality.name == "CQ"


def test_slim_mirrors_the_schema(hb_schema):
    view = slim_view(hb_schema)
    assert view.preset_version == "72.0.0"
    assert [k.name for k in view.keys] == list(hb_schema.keys)
    assert [k.name for k in view.audio_item_keys] == list(hb_schema.audio_item_keys)
    assert any(k.source is not None for k in view.keys)
    assert any(k.source is None for k in view.keys)
    assert view.audio_mixdowns_by_encoder
    assert "audio_mixdowns_by_encoder" not in view.lists
    assert set(view.filters) == set(hb_schema.filters)
    assert all(isinstance(f.rate_controls, list) for f in view.families)


def test_slim_carries_static_enums_and_source_extras(hb_schema):
    view = slim_view(hb_schema)
    assert view.static_enums["AudioTrackSelectionBehavior"] == ["none", "first", "all"]
    assert "VideoFramerateMode" in view.static_enums
    assert "auto" in view.source_extras["AudioSamplerate"]
    assert view.source_extras["AudioBitrate"] == [-1]
    used = {k.source.ref for k in view.keys if k.source and k.source.kind == "static"}
    assert used <= set(view.static_enums)


def test_slim_carries_selector_filter_aliases(hb_schema):
    assert slim_view(hb_schema).selector_filter_aliases == {"deinterlace": "yadif"}


def test_slim_carries_arm_owned_and_encoder_specific_keys(hb_schema):
    view = slim_view(hb_schema)
    assert view.arm_owned_keys == sorted(ARM_OWNED_KEYS)
    assert view.encoder_specific_keys == sorted(ENCODER_SPECIFIC_KEYS)
    assert "VideoHWDecode" in view.arm_owned_keys
    assert "VideoQualitySlider" in view.encoder_specific_keys


def _key(hb_schema, name):
    return next(k for k in slim_view(hb_schema).keys if k.name == name)


def test_slim_quality_type_labels(hb_schema):
    assert _key(hb_schema, "VideoQualityType").option_labels == {"1": "Average bitrate", "2": "Constant quality"}


def test_slim_framerate_labels(hb_schema):
    assert _key(hb_schema, "VideoFramerate").option_labels["auto"] == "Same as source"
    assert _key(hb_schema, "VideoFramerateMode").option_labels == {
        "cfr": "Constant",
        "vfr": "Variable",
        "pfr": "Peak",
    }


def test_slim_color_range_and_hdr_labels(hb_schema):
    assert _key(hb_schema, "VideoColorRange").option_labels == {
        "auto": "Same as source",
        "limited": "Limited",
        "full": "Full",
    }
    hdr = _key(hb_schema, "VideoPasshtruHDRDynamicMetadata").option_labels
    assert hdr["all"] == "Pass through all"
    assert hdr["off"] == "Off"


def test_slim_picker_keys_are_selects_with_labels(hb_schema):
    for name, values in (
        ("PictureModulus", (2, 4, 8, 16)),
        ("VideoColorMatrixCodeOverride", (0, 1, 2, 3, 4)),
        ("PicturePadColor", ("black", "white", "gray", "red", "green", "blue")),
    ):
        key = _key(hb_schema, name)
        assert (key.source.kind, key.source.ref) == ("static", name)
        assert tuple(slim_view(hb_schema).static_enums[name]) == values
    assert _key(hb_schema, "VideoColorMatrixCodeOverride").option_labels["0"] == "No override"
    assert _key(hb_schema, "PicturePadColor").option_labels["gray"] == "Gray"
    assert _key(hb_schema, "PictureModulus").option_labels is None


def test_slim_key_without_labels_is_none(hb_schema):
    assert _key(hb_schema, "PictureWidth").option_labels is None


def test_slim_labels_only_for_allowed_values(hb_schema, monkeypatch):
    from arm_common.handbrake_schema import slim

    monkeypatch.setitem(slim.OPTION_LABELS, "VideoFramerateMode", {"cfr": "Constant", "bogus": "Nope"})
    assert _key(hb_schema, "VideoFramerateMode").option_labels == {"cfr": "Constant"}
    for key in slim_view(hb_schema).keys:
        if key.option_labels:
            allowed = {str(v) for v in (*slim.STATIC_ENUMS.get(key.name, ()), *slim.SOURCE_EXTRAS.get(key.name, ()))}
            assert set(key.option_labels) <= allowed


def test_slim_exposes_hidden_keys(hb_schema):
    assert slim_view(hb_schema).hidden_keys == ["VideoScaler"]
    assert _key(hb_schema, "VideoScaler").source is None
    assert _key(hb_schema, "VideoScaler").option_labels is None
