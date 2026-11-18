"""The import pipeline: parse, flatten, map, validate a HandBrake GUI export."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from arm_common.enums import ContainerFormat
from arm_common.handbrake_schema.importer import (
    ExportNotRecognised,
    flatten_presets,
    import_export,
    map_preset,
    parse_export,
)


def _export(plex_export: Any, **keys: Any) -> dict[str, Any]:
    """The Plex export with the given preset keys overridden."""
    body = copy.deepcopy(plex_export)
    body["PresetList"][0].update(keys)
    return body


def _only(hb_schema: Any, body: Any) -> Any:
    return import_export(hb_schema, body).presets[0]


def test_plex_fixture_maps(hb_schema, plex_export):
    p = import_export(hb_schema, plex_export).presets[0]
    assert p.proposal.encoder == "any_h264" and p.proposal.container == ContainerFormat.MKV
    blocks = p.proposal.handbrake_settings.encoders
    assert blocks["nvenc_h264"] == {
        "bit_depth": 8,
        "VideoPreset": "slower",
        "VideoProfile": "main",
        "VideoLevel": "4.0",
        "VideoQualitySlider": 18,
    }
    assert blocks["x264"] == {"bit_depth": 8} and blocks["qsv_h264"] == {"bit_depth": 8}
    assert p.dropped_keys == ["VideoColorMatrixCode"]
    assert set(p.not_imported) == {"VideoMultiPass", "VideoTurboMultiPass", "x264UseAdvancedOptions"}
    assert p.copied_depth_to == ["qsv_h264", "x264"] and p.eight_bit_only == []
    common = p.proposal.handbrake_settings.common
    assert "VideoHWDecode" not in common and "VideoEncoder" not in common
    assert p.issues == [] and p.importable
    assert p.name == p.proposal.name == "Custom_Plex_720p" and p.path == [] and p.warnings == []


def test_response_reports_versions(hb_schema, plex_export):
    assert import_export(hb_schema, plex_export).handbrake_version == {"export": "72.0.0", "schema": "72.0.0"}


def test_ten_bit_export_lists_eight_bit_only_families(hb_schema, plex_export):
    p = _only(hb_schema, _export(plex_export, VideoEncoder="x265_10bit"))
    assert p.proposal.encoder == "any_h265"
    blocks = p.proposal.handbrake_settings.encoders
    assert blocks["x265"]["bit_depth"] == 10 and blocks["nvenc_h265"] == {"bit_depth": 10}
    assert blocks["qsv_h265"] == {"bit_depth": 10}
    assert p.copied_depth_to == ["nvenc_h265", "qsv_h265"] and p.eight_bit_only == []


def test_ten_bit_h264_export_has_eight_bit_only_families(hb_schema, plex_export):
    p = _only(hb_schema, _export(plex_export, VideoEncoder="x264_10bit"))
    blocks = p.proposal.handbrake_settings.encoders
    assert set(blocks) == {"x264"}
    assert p.copied_depth_to == [] and p.eight_bit_only == ["nvenc_h264", "qsv_h264"]


def test_multi_preset_list_and_nested_folders(hb_schema, plex_export):
    leaf = copy.deepcopy(plex_export["PresetList"][0])
    top = {**copy.deepcopy(leaf), "PresetName": "Top"}
    sub = {"Folder": True, "PresetName": "Sub", "ChildrenArray": [{**copy.deepcopy(leaf), "PresetName": "Deep"}]}
    folder = {"Folder": True, "PresetName": "Folder", "ChildrenArray": [sub]}
    body = {"PresetList": [top, folder], "VersionMajor": 72, "VersionMinor": 0, "VersionMicro": 0}
    presets = import_export(hb_schema, body).presets
    assert [(p.path, p.name) for p in presets] == [([], "Top"), (["Folder", "Sub"], "Deep")]


def test_bare_preset_object(hb_schema, plex_export):
    resp = import_export(hb_schema, plex_export["PresetList"][0])
    assert len(resp.presets) == 1 and resp.handbrake_version["export"] == "unknown"
    assert resp.presets[0].warnings == []


def test_version_mismatch_warns(hb_schema, plex_export):
    body = {**plex_export, "VersionMajor": 60}
    p = _only(hb_schema, body)
    assert p.importable and len(p.warnings) == 1
    assert "60.0.0" in p.warnings[0] and "renamed" in p.warnings[0]


def test_unmappable_encoder(hb_schema, plex_export):
    p = _only(hb_schema, _export(plex_export, VideoEncoder="VP9"))
    assert not p.importable and p.proposal is None and "VP9" in p.reason and p.source_encoder == "VP9"


@pytest.mark.parametrize("encoder", ["vt_h264", "mf_h265", "ffv1", "not_an_encoder"])
def test_other_unmappable_encoders(hb_schema, plex_export, encoder):
    p = _only(hb_schema, _export(plex_export, VideoEncoder=encoder))
    assert not p.importable and encoder in p.reason


def test_missing_encoder_not_importable(hb_schema, plex_export):
    body = _export(plex_export)
    del body["PresetList"][0]["VideoEncoder"]
    p = _only(hb_schema, body)
    assert not p.importable and p.source_encoder == "" and "(none)" in p.reason


def test_vce_encoder_drops_block_with_warning(hb_schema, plex_export):
    p = _only(hb_schema, _export(plex_export, VideoEncoder="vce_h265"))
    assert p.importable and p.proposal.encoder == "any_h265"
    assert not any(name.startswith("vce") for name in p.proposal.handbrake_settings.encoders)
    assert any("#602" in w for w in p.warnings)
    assert p.proposal.handbrake_settings.common["PictureWidth"] == 1280


def test_av_mov_maps_to_mkv_with_warning(hb_schema, plex_export):
    p = _only(hb_schema, _export(plex_export, FileFormat="av_mov"))
    assert p.proposal.container == ContainerFormat.MKV and any("av_mov" in w for w in p.warnings)


@pytest.mark.parametrize(("fmt", "expected"), [("av_mp4", ContainerFormat.MP4), ("av_webm", ContainerFormat.WEBM)])
def test_other_containers(hb_schema, plex_export, fmt, expected):
    assert _only(hb_schema, _export(plex_export, FileFormat=fmt)).proposal.container == expected


@pytest.mark.parametrize("body", [[], "x", {}, {"PresetList": "no"}, None])
def test_not_an_export(hb_schema, body):
    with pytest.raises(ExportNotRecognised, match="not a HandBrake preset export"):
        import_export(hb_schema, body)


def test_empty_list_has_no_presets(hb_schema):
    with pytest.raises(ExportNotRecognised, match="no presets"):
        import_export(hb_schema, {"PresetList": [], "VersionMajor": 72})


def test_empty_folder_has_no_presets(hb_schema):
    with pytest.raises(ExportNotRecognised, match="no presets"):
        import_export(hb_schema, {"PresetList": [{"Folder": True, "PresetName": "F"}]})


def test_parse_export_skips_non_dict_entries_and_reads_version():
    entries, version = parse_export({"PresetList": [1, {"PresetName": "a"}], "VersionMajor": 72, "VersionMinor": "x"})
    assert entries == [{"PresetName": "a"}] and version == (72, 0, 0)


def test_flatten_never_returns_folders():
    folder = {"Folder": True, "PresetName": "F", "ChildrenArray": [{"PresetName": "a"}]}
    assert flatten_presets([folder]) == [(("F",), {"PresetName": "a"})]


def test_values_invalid_for_encoder_become_issues(hb_schema, plex_export):
    p = _only(hb_schema, _export(plex_export, VideoEncoder="x264", VideoPreset="slowest"))
    assert p.importable and p.proposal.handbrake_settings.encoders["x264"]["VideoPreset"] == "slowest"
    assert [(i.key, i.encoder, i.code) for i in p.issues] == [("VideoPreset", "x264", "not_in_list")]
    assert "VideoMultiPass" not in p.not_imported


def test_x264_keeps_its_own_flags(hb_schema, plex_export):
    p = _only(hb_schema, _export(plex_export, VideoEncoder="x264", x264UseAdvancedOptions=True, VideoMultiPass=True))
    block = p.proposal.handbrake_settings.encoders["x264"]
    assert block["x264UseAdvancedOptions"] is True and block["VideoMultiPass"] is True
    assert p.not_imported == []


def test_x264_option_is_an_x264_block_key(hb_schema, plex_export):
    p = _only(hb_schema, _export(plex_export, VideoEncoder="x264", x264Option="ref=4"))
    assert p.proposal.handbrake_settings.encoders["x264"]["x264Option"] == "ref=4"
    assert "x264Option" not in p.proposal.handbrake_settings.common
    p = _only(hb_schema, _export(plex_export, VideoEncoder="x265", x264Option="ref=4"))
    assert "x264Option" in p.not_imported
    assert "x264Option" not in p.proposal.handbrake_settings.common


def test_empty_encoder_strings_are_not_stored(hb_schema, plex_export):
    block = _only(hb_schema, _export(plex_export, VideoEncoder="x264", VideoTune="")).proposal.handbrake_settings
    assert "VideoTune" not in block.encoders["x264"] and "VideoOptionExtra" not in block.encoders["x264"]


def test_every_present_key_kept_even_at_default(hb_schema, plex_export):
    p = _only(hb_schema, plex_export)
    assert p.proposal.handbrake_settings.common["PicturePadTop"] == 0


def test_map_preset_is_pure_per_entry(hb_schema, plex_export):
    preset = plex_export["PresetList"][0]
    before = copy.deepcopy(preset)
    view = map_preset(hb_schema, ("A",), preset)
    assert view.path == ["A"] and preset == before


@pytest.mark.parametrize("children", [[1, "x", None], "x", 5, None, {"a": 1}])
def test_malformed_folder_children_are_ignored(hb_schema, children):
    body = {"PresetList": [{"Folder": True, "PresetName": "F", "ChildrenArray": children}]}
    with pytest.raises(ExportNotRecognised, match="no presets"):
        import_export(hb_schema, body)


def test_malformed_children_keep_valid_siblings(hb_schema, plex_export):
    leaf = plex_export["PresetList"][0]
    body = {"PresetList": [{"Folder": True, "PresetName": "F", "ChildrenArray": [1, leaf]}]}
    assert [p.path for p in import_export(hb_schema, body).presets] == [["F"]]


@pytest.mark.parametrize("fmt", [["av_mkv"], {"a": 1}, 5, None])
def test_non_string_file_format_falls_back_to_mkv(hb_schema, plex_export, fmt):
    p = _only(hb_schema, _export(plex_export, FileFormat=fmt))
    assert p.proposal.container == ContainerFormat.MKV and len(p.warnings) == 1


@pytest.mark.parametrize("encoder", [["x264"], {"a": 1}, 5, None])
def test_non_string_encoder_is_not_importable(hb_schema, plex_export, encoder):
    p = _only(hb_schema, _export(plex_export, VideoEncoder=encoder))
    assert not p.importable and p.reason.startswith("The encoder ")


@pytest.mark.parametrize("name", [["a"], {"a": 1}, 5, None])
def test_non_string_preset_name_becomes_text(hb_schema, plex_export, name):
    p = _only(hb_schema, _export(plex_export, PresetName=name))
    assert p.importable and p.name == str(name)
