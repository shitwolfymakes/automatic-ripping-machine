"""Which HandBrake encoder families a preset's catalog encoder id can resolve to. Does no I/O."""

from __future__ import annotations

from collections.abc import Callable

from arm_common.encoders import ENCODERS, VENDOR_RANK, EncoderSpec, cpu_encoder_for, get_encoder
from arm_common.handbrake_schema.effective import base_preset
from arm_common.handbrake_schema.types import HandbrakeSchema


def _handbrake_family(spec: EncoderSpec) -> list[str]:
    """The one family of a spec HandBrake runs; none for the ffmpeg VAAPI engine."""
    if spec.engine != "handbrake" or spec.engine_encoder is None:
        return []
    return [spec.engine_encoder]


def _pinned(schema: HandbrakeSchema, spec: EncoderSpec, preset_ref: str | None) -> list[str]:
    return _handbrake_family(spec)


def _any_codec(schema: HandbrakeSchema, spec: EncoderSpec, preset_ref: str | None) -> list[str]:
    """Every HandBrake GPU family of the codec in vendor-rank order, then the CPU family."""
    gpus = [s for s in ENCODERS.values() if s.kind == "gpu" and s.codec == spec.codec and s.vendor is not None]
    gpus.sort(key=lambda s: VENDOR_RANK[s.vendor])  # type: ignore[index]
    families = [family for gpu in gpus for family in _handbrake_family(gpu)]
    return [*families, *_handbrake_family(cpu_encoder_for(spec.codec or ""))]


def family_of_variant(schema: HandbrakeSchema, encoder: str) -> list[str]:
    """Names of the families that have a variant whose HandBrake encoder is ``encoder`` (e.g. ``x265_10bit``)."""
    return [f.name for f in schema.families.values() if any(v.encoder == encoder for v in f.variants.values())]


def base_families(schema: HandbrakeSchema, preset_ref: str | None) -> list[str]:
    """The family of the base built-in's own encoder; none without a base. Raises UnknownBasePreset."""
    encoder = base_preset(schema, preset_ref).get("VideoEncoder")
    if encoder is None:
        return []
    return family_of_variant(schema, encoder)


def _from_base(schema: HandbrakeSchema, spec: EncoderSpec, preset_ref: str | None) -> list[str]:
    return base_families(schema, preset_ref)


_REACHABLE: dict[str, Callable[[HandbrakeSchema, EncoderSpec, str | None], list[str]]] = {
    "preset": _from_base,
    "cpu": _pinned,
    "gpu": _pinned,
    "any": _any_codec,
}


def reachable_families(schema: HandbrakeSchema, encoder_id: str, preset_ref: str | None) -> list[str]:
    """Families the catalog id can resolve to, in claim order. Raises UnknownBasePreset for a bad ``preset_ref``."""
    spec = get_encoder(encoder_id)
    return _REACHABLE[spec.kind](schema, spec, preset_ref)
