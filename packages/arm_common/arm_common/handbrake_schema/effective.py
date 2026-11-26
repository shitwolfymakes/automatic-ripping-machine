"""Which value a setting has once a preset is layered onto its base: common, then base, then template."""

from __future__ import annotations

from typing import Any

from arm_common.handbrake_schema.types import HandbrakeSchema
from arm_common.schemas.handbrake import HandbrakeSettings


class UnknownBasePreset(ValueError):
    def __init__(self, tag: str, name: str) -> None:
        super().__init__(f"HandBrake {tag} has no built-in preset named {name!r}")


def base_preset(schema: HandbrakeSchema, preset_ref: str | None) -> dict[str, Any]:
    """The built-in preset named ``preset_ref``; an empty dict when the preset has no base."""
    if preset_ref is None:
        return {}
    try:
        return schema.builtin_presets[preset_ref]
    except KeyError:
        raise UnknownBasePreset(schema.handbrake_tag, preset_ref) from None


def effective_value(schema: HandbrakeSchema, preset_ref: str | None, settings: HandbrakeSettings, key: str) -> Any:
    if key in settings.common:
        return settings.common[key]
    base = base_preset(schema, preset_ref)
    if key in base:
        return base[key]
    return schema.keys[key].default
