"""Turns a HandBrake GUI export into preset proposals: parse, flatten, map, validate. Does no I/O."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from arm_common.encoders import ENCODERS
from arm_common.enums import ContainerFormat, TranscodeTool
from arm_common.handbrake_schema.overlay import ARM_OWNED_KEYS, ENCODER_SPECIFIC_KEYS
from arm_common.handbrake_schema.reach import reachable_families
from arm_common.handbrake_schema.types import HandbrakeSchema
from arm_common.handbrake_schema.validate import validate_settings
from arm_common.schemas.handbrake import (
    HandbrakeSettings,
    ImportedPresetView,
    ImportParseResponse,
    ImportProposal,
    SettingIssue,
)

_CONTAINERS: dict[str, ContainerFormat] = {
    "av_mkv": ContainerFormat.MKV,
    "av_mp4": ContainerFormat.MP4,
    "av_webm": ContainerFormat.WEBM,
}
_VCE_CODECS: dict[str, str] = {"vce_h264": "h264", "vce_h265": "h265", "vce_av1": "av1"}
_UNKNOWN_VERSION = "unknown"


class ExportNotRecognised(ValueError):
    """The body is not a HandBrake export. The message is shown to the user."""


@dataclass
class _Split:
    common: dict[str, Any] = field(default_factory=dict)
    specific: dict[str, Any] = field(default_factory=dict)
    dropped: list[str] = field(default_factory=list)
    not_imported: list[str] = field(default_factory=list)


def _version_of(body: dict[str, Any]) -> tuple[int, int, int] | None:
    parts = [body.get(k) for k in ("VersionMajor", "VersionMinor", "VersionMicro")]
    if not isinstance(parts[0], int):
        return None
    return (parts[0], *(p if isinstance(p, int) else 0 for p in parts[1:]))  # type: ignore[return-value]


def parse_export(body: Any) -> tuple[list[dict[str, Any]], tuple[int, int, int] | None]:
    """Accept a ``PresetList`` export or one bare preset; return its entries and the export's version."""
    if isinstance(body, dict) and isinstance(body.get("PresetList"), list):
        entries = body["PresetList"]
    elif isinstance(body, dict) and "PresetName" in body:
        entries = [body]
    else:
        raise ExportNotRecognised("The file is not a HandBrake preset export")
    return _dict_entries(entries), _version_of(body)


def _dict_entries(value: Any) -> list[dict[str, Any]]:
    """The dict items of a list; anything else is empty."""
    return [e for e in value if isinstance(e, dict)] if isinstance(value, list) else []


def flatten_presets(
    entries: list[dict[str, Any]], path: tuple[str, ...] = ()
) -> list[tuple[tuple[str, ...], dict[str, Any]]]:
    """Every non-folder preset with the folder names above it. Folders are walked, never returned."""
    found: list[tuple[tuple[str, ...], dict[str, Any]]] = []
    for entry in entries:
        if entry.get("Folder"):
            children = _dict_entries(entry.get("ChildrenArray"))
            found.extend(flatten_presets(children, (*path, str(entry.get("PresetName", "")))))
        else:
            found.append((path, entry))
    return found


def _family_and_depth(schema: HandbrakeSchema, encoder: str) -> tuple[str, int] | None:
    for family in schema.families.values():
        for depth, variant in family.variants.items():
            if variant.encoder == encoder:
                return family.name, depth
    return None


def _codec_of(family: str) -> str | None:
    for spec in ENCODERS.values():
        if spec.engine == "handbrake" and spec.engine_encoder == family:
            return spec.codec
    return _VCE_CODECS.get(family)


def _map_container(file_format: Any) -> tuple[ContainerFormat, list[str]]:
    container = _CONTAINERS.get(file_format) if isinstance(file_format, str) else None
    if container is not None:
        return container, []
    return ContainerFormat.MKV, [f"File format {file_format} has no ARM container; the preset uses mkv."]


def _unused_flags(schema: HandbrakeSchema, family: str) -> set[str]:
    """Encoder-dependent keys this family does not use (rule 11)."""
    spec = schema.families[family]
    unused = {"VideoMultiPass"} if not spec.multipass else set()
    if not spec.turbo:
        unused.add("VideoTurboMultiPass")
    if family != "x264":
        unused |= {"x264UseAdvancedOptions", "x264Option"}
    return unused


def _is_unset(key: str, value: Any) -> bool:
    """An encoder-specific string left empty means "not set"; it is not stored."""
    return key in ENCODER_SPECIFIC_KEYS and value == ""


def _split_keys(schema: HandbrakeSchema, preset: dict[str, Any], family: str) -> _Split:
    """Sort the export's keys into common, encoder-specific, dropped and not-imported."""
    split = _Split()
    unused = _unused_flags(schema, family)
    for key, value in preset.items():
        if key in ARM_OWNED_KEYS or _is_unset(key, value):
            continue
        if key in unused:
            split.not_imported.append(key)
        elif key in ENCODER_SPECIFIC_KEYS:
            split.specific[key] = value
        elif key in schema.keys:
            split.common[key] = value
        else:
            split.dropped.append(key)
    split.dropped.sort()
    split.not_imported.sort()
    return split


def _own_block(
    family: str, depth: int, split: _Split, reachable: list[str]
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """The export family's block, or none and a warning when ARM cannot run that family yet (vce)."""
    if family in reachable:
        return {family: {"bit_depth": depth, **split.specific}}, []
    return {}, [f"{family} settings are not imported yet (see #602); the preset keeps its common settings."]


def _copy_depth(
    schema: HandbrakeSchema, reachable: list[str], family: str, depth: int
) -> tuple[dict[str, dict[str, Any]], list[str], list[str]]:
    """Depth-only blocks for the other reachable families (R3), and the families lacking that depth."""
    others = sorted(f for f in reachable if f != family)
    has_depth = [f for f in others if depth in schema.families[f].variants]
    lacking = [f for f in others if f not in has_depth]
    return {f: {"bit_depth": depth} for f in has_depth}, has_depth, lacking


def _validate_proposal(schema: HandbrakeSchema, proposal: ImportProposal) -> list[SettingIssue]:
    return validate_settings(
        schema,
        tool=TranscodeTool.HANDBRAKE,
        encoder_id=proposal.encoder,
        preset_ref=None,
        settings=proposal.handbrake_settings,
    )


def _not_importable(path: tuple[str, ...], preset: dict[str, Any], source: str, reason: str) -> ImportedPresetView:
    return ImportedPresetView(
        path=list(path),
        name=str(preset.get("PresetName", "")),
        proposal=None,
        source_encoder=source,
        dropped_keys=[],
        not_imported=[],
        copied_depth_to=[],
        eight_bit_only=[],
        warnings=[],
        issues=[],
        importable=False,
        reason=reason,
    )


def map_preset(schema: HandbrakeSchema, path: tuple[str, ...], preset: dict[str, Any]) -> ImportedPresetView:
    """One export entry to a proposal plus the review's lists. Never raises."""
    source = str(preset.get("VideoEncoder", ""))
    resolved = _family_and_depth(schema, source)
    codec = _codec_of(resolved[0]) if resolved else None
    if resolved is None or codec is None:
        return _not_importable(path, preset, source, f"The encoder {source or '(none)'} cannot be used by ARM")
    family, depth = resolved
    container, warnings = _map_container(preset.get("FileFormat"))
    encoder = f"any_{codec}"
    split = _split_keys(schema, preset, family)
    reachable = reachable_families(schema, encoder, None)
    blocks, own_warnings = _own_block(family, depth, split, reachable)
    copied, copied_to, eight_only = _copy_depth(schema, reachable, family, depth)
    proposal = ImportProposal(
        name=str(preset.get("PresetName", "")),
        container=container,
        encoder=encoder,
        handbrake_settings=HandbrakeSettings(common=split.common, encoders={**copied, **blocks}),
    )
    return ImportedPresetView(
        path=list(path),
        name=proposal.name,
        proposal=proposal,
        source_encoder=source,
        dropped_keys=split.dropped,
        not_imported=split.not_imported,
        copied_depth_to=copied_to,
        eight_bit_only=eight_only if depth > 8 else [],
        warnings=[*warnings, *own_warnings],
        issues=_validate_proposal(schema, proposal),
        importable=True,
    )


def _version_text(version: tuple[int, int, int] | None) -> str:
    return _UNKNOWN_VERSION if version is None else ".".join(str(p) for p in version)


def _mismatch_warning(schema: HandbrakeSchema, version: tuple[int, int, int] | None) -> list[str]:
    if version is None or version[0] == schema.preset_version[0]:
        return []
    return [
        f"This export is from preset format {_version_text(version)}; HandBrake {schema.handbrake_tag} uses "
        f"{_version_text(schema.preset_version)}. Keys renamed since then are dropped."
    ]


def import_export(schema: HandbrakeSchema, body: Any) -> ImportParseResponse:
    """Parse, flatten and map an export. Raises ExportNotRecognised for a body with no presets."""
    entries, version = parse_export(body)
    flat = flatten_presets(entries)
    if not flat:
        raise ExportNotRecognised("The file has no presets")
    mismatch = _mismatch_warning(schema, version)
    views = [map_preset(schema, path, preset) for path, preset in flat]
    for view in views:
        view.warnings.extend(mismatch)
    return ImportParseResponse(
        handbrake_version={"export": _version_text(version), "schema": _version_text(schema.preset_version)},
        presets=views,
    )
