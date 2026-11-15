"""The slim view of the HandBrake schema: what the UI renders from, without the built-in preset values."""

from __future__ import annotations

from typing import Any

from arm_common.handbrake_schema.overlay import (
    ARM_OWNED_KEYS,
    HIDDEN_KEYS,
    ENCODER_SPECIFIC_KEYS,
    OPTION_LABELS,
    SELECTOR_FILTER_ALIASES,
    SOURCE_EXTRAS,
    STATIC_ENUMS,
)
from arm_common.handbrake_schema.types import (
    EncoderFamily,
    EncoderVariant,
    FilterSpec,
    HandbrakeSchema,
    KeySpec,
)
from arm_common.schemas.handbrake import (
    HandbrakeSchemaSlimView,
    SlimFamily,
    SlimFilter,
    SlimKey,
    SlimQuality,
    SlimSource,
    SlimVariant,
)

_MIXDOWNS_LIST = "audio_mixdowns_by_encoder"


def _option_labels(name: str) -> dict[str, str] | None:
    labels = OPTION_LABELS.get(name)
    if labels is None:
        return None
    allowed = {str(v) for v in (*STATIC_ENUMS.get(name, ()), *SOURCE_EXTRAS.get(name, ()))}
    return {value: label for value, label in labels.items() if value in allowed}


def _slim_key(spec: KeySpec) -> SlimKey:
    source = SlimSource(kind=spec.source.kind, ref=spec.source.ref) if spec.source else None
    return SlimKey(
        name=spec.name,
        type=spec.type,
        default=spec.default,
        tab=spec.tab,
        group=spec.group,
        label=spec.label,
        source=source,
        limits=spec.limits,
        known=spec.known,
        option_labels=_option_labels(spec.name),
    )


def _slim_variant(variant: EncoderVariant) -> SlimVariant:
    q = variant.quality
    return SlimVariant(
        encoder=variant.encoder,
        depth=variant.depth,
        presets=list(variant.presets),
        tunes=list(variant.tunes),
        profiles=list(variant.profiles),
        levels=list(variant.levels),
        quality=SlimQuality(name=q.name, low=q.low, high=q.high, step=q.step),
    )


def _slim_family(family: EncoderFamily) -> SlimFamily:
    return SlimFamily(
        name=family.name,
        codec_id=family.codec_id,
        multipass=family.multipass,
        turbo=family.turbo,
        rate_controls=sorted(family.rate_controls),
        variants=[_slim_variant(v) for v in family.variants.values()],
    )


def _slim_filter(spec: FilterSpec) -> SlimFilter:
    return SlimFilter(presets=list(spec.presets), tunes=list(spec.tunes))


def _slim_lists(lists: dict[str, Any]) -> dict[str, list[Any]]:
    return {name: list(values) for name, values in lists.items() if name != _MIXDOWNS_LIST}


def _slim_mixdowns(lists: dict[str, Any]) -> dict[str, list[str]]:
    return {encoder: list(names) for encoder, names in lists[_MIXDOWNS_LIST].items()}


def _slim_static_enums() -> dict[str, list[Any]]:
    return {name: list(values) for name, values in STATIC_ENUMS.items()}


def _slim_source_extras() -> dict[str, list[Any]]:
    return {name: list(values) for name, values in SOURCE_EXTRAS.items()}


def _version_string(version: tuple[int, int, int]) -> str:
    return ".".join(str(part) for part in version)


def slim_view(schema: HandbrakeSchema) -> HandbrakeSchemaSlimView:
    return HandbrakeSchemaSlimView(
        handbrake_tag=schema.handbrake_tag,
        preset_version=_version_string(schema.preset_version),
        content_hash=schema.content_hash,
        keys=[_slim_key(k) for k in schema.keys.values()],
        audio_item_keys=[_slim_key(k) for k in schema.audio_item_keys.values()],
        families=[_slim_family(f) for f in schema.families.values()],
        lists=_slim_lists(schema.lists),
        audio_mixdowns_by_encoder=_slim_mixdowns(schema.lists),
        filters={name: _slim_filter(f) for name, f in schema.filters.items()},
        builtin_names=list(schema.builtin_presets),
        static_enums=_slim_static_enums(),
        source_extras=_slim_source_extras(),
        selector_filter_aliases=dict(SELECTOR_FILTER_ALIASES),
        arm_owned_keys=sorted(ARM_OWNED_KEYS),
        encoder_specific_keys=sorted(ENCODER_SPECIFIC_KEYS),
        hidden_keys=sorted(HIDDEN_KEYS),
    )
