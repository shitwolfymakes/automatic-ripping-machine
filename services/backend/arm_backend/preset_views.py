"""The read side of a transcode preset: the settings normaliser, the host note and the view with its issues.

Pure functions: the router loads the schema and the GPU rows, these decide.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from arm_common import Gpu, GpuVendor, TranscodePreset
from arm_common.encoders import get_encoder, gpu_is_eligible
from arm_common.handbrake_schema.types import HandbrakeSchema
from arm_common.handbrake_schema.validate import validate_settings
from arm_common.schemas import HandbrakeSettings, SettingIssue, TranscodePresetView


def normalise_settings(settings: HandbrakeSettings | None) -> dict[str, Any] | None:
    """The stored form of a preset's settings: empty encoder blocks dropped; None for none or for settings
    with no value in them."""
    if settings is None or settings.is_empty():
        return None
    stored = settings.model_dump()
    stored["encoders"] = {family: block for family, block in stored["encoders"].items() if block}
    return stored


def host_notes(preset: TranscodePreset, gpus: Sequence[Gpu]) -> list[str]:
    """`encodes_on_cpu_here` when the preset has settings, may use a GPU (`any_<codec>`), and no verified
    non-AMD device on this host can take its codec (AMD devices run ffmpeg and ignore the settings)."""
    if not preset.handbrake_settings:
        return []
    spec = get_encoder(preset.encoder)
    if spec.kind != "any" or spec.codec is None:
        return []
    codec = spec.codec
    if any(gpu.vendor != GpuVendor.VAAPI and gpu_is_eligible(gpu, codec) for gpu in gpus):
        return []
    return ["encodes_on_cpu_here"]


def _issues(preset: TranscodePreset, schema: HandbrakeSchema | None) -> list[SettingIssue]:
    if schema is None or not preset.handbrake_settings:
        return []
    return validate_settings(
        schema,
        tool=preset.tool,
        encoder_id=preset.encoder,
        preset_ref=preset.preset_ref,
        settings=HandbrakeSettings.model_validate(preset.handbrake_settings),
    )


def preset_view(preset: TranscodePreset, schema: HandbrakeSchema | None, gpus: Sequence[Gpu]) -> TranscodePresetView:
    """The wire view of a stored preset, with its issues against `schema` (none without one) and its host note."""
    view = TranscodePresetView.model_validate(preset)
    return view.model_copy(update={"issues": _issues(preset, schema), "host_notes": host_notes(preset, gpus)})
