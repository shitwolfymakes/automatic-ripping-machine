"""The one-preset file a HandBrake encode imports when its preset carries HandBrake settings.

Deciding whether a preset has settings, checking them against the image's
baked schema, materialising the file and flags, and writing the file
are separate functions; `main` owns the temp directory and the launch.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from arm_common.encoders import EncoderSpec
from arm_common.handbrake_schema.materialise import Materialised, materialise
from arm_common.handbrake_schema.reach import base_families
from arm_common.handbrake_schema.types import HandbrakeSchema
from arm_common.handbrake_schema.validate import validate_common, validate_family
from arm_common.schemas import TranscodePresetView
from arm_common.schemas.handbrake import HandbrakeSettings, SettingIssue

from arm_transcode.schema_file import load_baked_schema

PRESET_FILE_NAME = "arm-preset.json"
NO_SCHEMA_MESSAGE = "this transcode image has no HandBrake schema; rebuild or pull it"


class SettingsRejected(RuntimeError):
    """The preset's settings are invalid against this image's schema; raised before HandBrake launches."""

    def __init__(self, issues: list[SettingIssue]) -> None:
        super().__init__("HandBrake settings rejected: " + "; ".join(issue.message for issue in issues))


def settings_of(preset: TranscodePresetView) -> HandbrakeSettings | None:
    """The preset's HandBrake settings when it carries any (it then runs from a materialised file); else None."""
    settings = preset.handbrake_settings
    return None if settings is None or settings.is_empty() else settings


def family_of(schema: HandbrakeSchema, spec: EncoderSpec | None, preset_ref: str | None) -> str | None:
    """The family whose block applies: the resolved spec's; for the preset's own encoder (no spec), its base's.

    None for the preset's own encoder without a base. Raises `UnknownBasePreset` for a bad `preset_ref`.
    """
    if spec is not None:
        return spec.engine_encoder
    return next(iter(base_families(schema, preset_ref)), None)


def require_baked_schema() -> HandbrakeSchema:
    """The image's baked schema; a settings run cannot proceed without one."""
    schema = load_baked_schema()
    if schema is None:
        raise RuntimeError(NO_SCHEMA_MESSAGE)
    return schema


def _family_issues(
    schema: HandbrakeSchema, family: str | None, preset_ref: str | None, settings: HandbrakeSettings
) -> list[SettingIssue]:
    """Rules for the resolved family's block; none without a family (the preset's own encoder, no base)."""
    if family is None:
        return []
    return validate_family(schema, family=family, preset_ref=preset_ref, settings=settings)


def check_settings(
    schema: HandbrakeSchema, family: str | None, preset_ref: str | None, settings: HandbrakeSettings
) -> None:
    """Raise `SettingsRejected` when `common` or the family's block is invalid against this image's schema.

    `UnknownBasePreset` from either check propagates unchanged.
    """
    issues = validate_common(schema, preset_ref, settings.common)
    issues += _family_issues(schema, family, preset_ref, settings)
    if issues:
        raise SettingsRejected(issues)


def materialise_for_encode(
    preset: TranscodePresetView, settings: HandbrakeSettings, spec: EncoderSpec | None
) -> Materialised:
    """Validate `settings` for the resolved family, then build the preset file and encoder flags.

    Raises `SettingsRejected`, `UnknownBasePreset`, or `RuntimeError` when the image has no schema.
    """
    schema = require_baked_schema()
    family = family_of(schema, spec, preset.preset_ref)
    check_settings(schema, family, preset.preset_ref, settings)
    # The preset's own encoder (no spec) keeps the base's encoder: no --encoder.
    return materialise(schema, preset.preset_ref, settings, family, preset.container, emit_encoder=spec is not None)


def write_preset_file(work_dir: Path, preset_file: dict[str, Any]) -> Path:
    """Write the preset file as `arm-preset.json` in `work_dir` and return its path."""
    path = work_dir / PRESET_FILE_NAME
    path.write_text(json.dumps(preset_file))
    return path
