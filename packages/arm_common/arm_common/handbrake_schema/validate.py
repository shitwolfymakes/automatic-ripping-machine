"""Pure validation of a preset's HandBrake settings against the loaded schema. Does no I/O.

Each rule is one function returning an issue or None; ``_VALUE_RULES`` runs them in order and the first
issue wins, so a key is reported once.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from arm_common.enums import TranscodeTool
from arm_common.encoders import get_encoder
from arm_common.handbrake_schema.effective import UnknownBasePreset, base_preset, effective_value
from arm_common.handbrake_schema.overlay import (
    ARM_OWNED_KEYS,
    ENCODER_SPECIFIC_KEYS,
    OPEN_ENUMS,
    SELECTOR_FILTER_ALIASES,
    SOURCE_EXTRAS,
    STATIC_ENUMS,
)
from arm_common.handbrake_schema.materialise import resolve_depth
from arm_common.handbrake_schema.reach import reachable_families
from arm_common.handbrake_schema.types import EncoderFamily, EncoderVariant, HandbrakeSchema, KeySpec
from arm_common.schemas.handbrake import HandbrakeSettings, IssueCode, SettingIssue

_LIST_ITEM = "{list}[{index}].{key}"


@dataclass(frozen=True)
class _Target:
    """One value to check: its spec, the name to report it under, and a lookup for sibling keys."""

    schema: HandbrakeSchema
    spec: KeySpec
    name: str
    value: Any
    sibling: Callable[[str], Any]


def _issue(name: str, code: IssueCode, message: str) -> SettingIssue:
    return SettingIssue(key=name, code=code, message=message)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


_TYPE_CHECKS: dict[str, Callable[[Any], bool]] = {
    "bool": lambda v: isinstance(v, bool),
    "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "float": _is_number,
    "str": lambda v: isinstance(v, str),
    "list_str": lambda v: isinstance(v, list) and all(isinstance(i, str) for i in v),
    "list_obj": lambda v: isinstance(v, list) and all(isinstance(i, dict) for i in v),
}


def _check_known(keys: dict[str, KeySpec], name: str) -> SettingIssue | None:
    if name in keys:
        return None
    return _issue(name, "unknown_key", f"{name} is not a HandBrake setting")


def _check_placement(name: str) -> SettingIssue | None:
    if name in ARM_OWNED_KEYS:
        return _issue(name, "not_allowed_here", f"{name} is set by ARM and cannot be stored")
    if name in ENCODER_SPECIFIC_KEYS:
        return _issue(name, "not_allowed_here", f"{name} depends on the encoder, so it belongs in an encoder block")
    return None


def _check_type(target: _Target) -> SettingIssue | None:
    if _TYPE_CHECKS[target.spec.type](target.value):
        return None
    return _issue(target.name, "wrong_type", f"{target.value!r} is not a valid {target.spec.type} value")


def _selected_filter(target: _Target, selector: str) -> str | None:
    """The libhb filter a selector key currently names, or None when it names none (for example off)."""
    selected = target.sibling(selector)
    if not isinstance(selected, str):
        return None  # the selector itself is reported wrong_type
    name = SELECTOR_FILTER_ALIASES.get(selected, selected)
    return name if name in target.schema.filters else None


def _filter_values(target: _Target, attr: str) -> tuple[str, ...] | None:
    ref = target.spec.source.ref  # type: ignore[union-attr]
    name = ref if ref in target.schema.filters else _selected_filter(target, ref)
    if name is None:
        return None
    # A filter with no such list (hqdn3d has no tunes) accepts the template's "none" and leaves the rest alone.
    return getattr(target.schema.filters[name], attr) or None


def _mixdown_values(target: _Target) -> tuple[str, ...] | None:
    encoder = target.sibling(target.spec.source.ref)  # type: ignore[union-attr]
    if not isinstance(encoder, str):
        return None  # the encoder itself is reported wrong_type
    mixdowns: dict[str, tuple[str, ...]] = target.schema.lists["audio_mixdowns_by_encoder"]
    return mixdowns.get(encoder)


def _allowed_values(target: _Target) -> tuple[Any, ...] | None:
    """The values the key's source allows, or None when the source does not constrain it right now."""
    source = target.spec.source
    if source is None:
        return None
    resolvers: dict[str, Callable[[], tuple[Any, ...] | None]] = {
        "static": lambda: STATIC_ENUMS[source.ref],
        "schema_list": lambda: tuple(target.schema.lists[source.ref]),
        "filter_presets": lambda: _filter_values(target, "presets"),
        "filter_tunes": lambda: _filter_values(target, "tunes"),
        "audio_mixdowns": lambda: _mixdown_values(target),
    }
    allowed = resolvers[source.kind]()
    if allowed is None:
        return None
    return (*allowed, *SOURCE_EXTRAS.get(target.spec.name, ()))


def _check_source(target: _Target) -> SettingIssue | None:
    allowed = _allowed_values(target)
    if allowed is None or (target.spec.name in OPEN_ENUMS and isinstance(target.value, str)):
        return None
    values = target.value if isinstance(target.value, list) else [target.value]
    for value in values:
        if value not in allowed:
            listed = ", ".join(str(a) for a in allowed)
            return _issue(target.name, "not_in_list", f"{value!r} is not one of {listed}")
    return None


def _check_limits(target: _Target) -> SettingIssue | None:
    limits = target.spec.limits
    if limits is None or not _is_number(target.value) or limits[0] <= target.value <= limits[1]:
        return None
    return _issue(target.name, "out_of_range", f"{target.value} is outside {limits[0]} to {limits[1]}")


_VALUE_RULES: tuple[Callable[[_Target], SettingIssue | None], ...] = (_check_type, _check_source, _check_limits)


def _first_issue(target: _Target) -> list[SettingIssue]:
    for rule in _VALUE_RULES:
        found = rule(target)
        if found is not None:
            return [found]
    return []


def _check_item(schema: HandbrakeSchema, list_name: str, index: int, item: dict[str, Any]) -> list[SettingIssue]:
    issues: list[SettingIssue] = []

    def sibling(key: str) -> Any:
        return item[key] if key in item else schema.audio_item_keys[key].default

    for key, value in item.items():
        name = _LIST_ITEM.format(list=list_name, index=index, key=key)
        unknown = _check_known(schema.audio_item_keys, key)
        if unknown is not None:
            issues.append(unknown.model_copy(update={"key": name}))
            continue
        issues += _first_issue(_Target(schema, schema.audio_item_keys[key], name, value, sibling))
    return issues


def _check_value(target: _Target) -> list[SettingIssue]:
    issues = _first_issue(target)
    if issues or target.spec.type != "list_obj":
        return issues
    return [i for n, item in enumerate(target.value) for i in _check_item(target.schema, target.name, n, item)]


def validate_common(schema: HandbrakeSchema, preset_ref: str | None, common: dict[str, Any]) -> list[SettingIssue]:
    """Rules 1 to 5 for the ``common`` settings, layered onto the built-in ``preset_ref``."""
    base_preset(schema, preset_ref)  # raises UnknownBasePreset early
    settings = HandbrakeSettings(common=common)

    def sibling(key: str) -> Any:
        return effective_value(schema, preset_ref, settings, key)

    issues: list[SettingIssue] = []
    for key, value in common.items():
        early = _check_known(schema.keys, key) or _check_placement(key)
        if early is not None:
            issues.append(early)
            continue
        issues += _check_value(_Target(schema, schema.keys[key], key, value, sibling))
    return issues


# ---------------------------------------------------------------------------------------------------------------
# Rules 6 to 11: the per-encoder blocks. Each rule takes a _Block and returns its issues.
# ---------------------------------------------------------------------------------------------------------------

_WHOLE = "handbrake_settings"


@dataclass(frozen=True)
class _Block:
    """One family's block in context: the family, its block, and the preset it layers onto."""

    schema: HandbrakeSchema
    family: EncoderFamily
    block: dict[str, Any]
    preset_ref: str | None
    settings: HandbrakeSettings


def _block_issue(name: str, key: str, code: IssueCode, message: str) -> SettingIssue:
    return SettingIssue(key=key, encoder=name, code=code, message=message)


def _variant(ctx: _Block) -> EncoderVariant | None:
    """The family's variant at the block's depth; None when the depth is not one the family has."""
    depth = resolve_depth(ctx.schema, ctx.family.name, ctx.preset_ref, ctx.block)
    for have, variant in ctx.family.variants.items():
        if have == depth and not isinstance(depth, bool):
            return variant
    return None


def _check_unknown_block_keys(ctx: _Block) -> list[SettingIssue]:
    return [
        _block_issue(ctx.family.name, key, "unknown_key", f"{key} is not an encoder setting")
        for key in ctx.block
        if key != "bit_depth" and key not in ENCODER_SPECIFIC_KEYS
    ]


def _check_bit_depth(ctx: _Block) -> list[SettingIssue]:
    """Rule 7."""
    if "bit_depth" not in ctx.block or _variant(ctx) is not None:
        return []
    have = ", ".join(str(d) for d in ctx.family.variants)
    message = f"{ctx.block['bit_depth']!r} is not a bit depth of {ctx.family.name} (it has {have})"
    return [_block_issue(ctx.family.name, "bit_depth", "not_in_list", message)]


# HandBrake writes VideoTune as null for "no tune"; every other block value must match its schema type.
_NULLABLE_BLOCK_KEYS = frozenset({"VideoTune"})


def _block_type_issue(ctx: _Block, key: str) -> SettingIssue | None:
    """A wrong_type issue when the block's value for `key` is not its schema type; None for a key the schema lacks."""
    spec = ctx.schema.keys.get(key)
    value = ctx.block[key]
    if spec is None or (value is None and key in _NULLABLE_BLOCK_KEYS) or _TYPE_CHECKS[spec.type](value):
        return None
    return _block_issue(ctx.family.name, key, "wrong_type", f"{value!r} is not a valid {spec.type} value")


def _check_block_types(ctx: _Block) -> list[SettingIssue]:
    """Rule 8a: every encoder key in the block holds its schema type, read from the schema so a key added to
    ENCODER_SPECIFIC_KEYS is checked too."""
    found = [_block_type_issue(ctx, key) for key in ctx.block if key in ENCODER_SPECIFIC_KEYS]
    return [issue for issue in found if issue is not None]


def _well_typed(ctx: _Block, key: str) -> bool:
    """The block sets `key` with a value of its type; rule 8a reports the others, so later rules skip them."""
    return key in ctx.block and _block_type_issue(ctx, key) is None


_LISTED_KEYS: dict[str, str] = {
    "VideoPreset": "presets",
    "VideoTune": "tunes",
    "VideoProfile": "profiles",
    "VideoLevel": "levels",
}


def _listed_values(key: str, value: Any) -> list[Any]:
    """A tune names several values joined by commas; the others name one."""
    if key == "VideoTune" and isinstance(value, str):
        return [part.strip() for part in value.split(",")]
    return [value]


def _check_listed_key(ctx: _Block, variant: EncoderVariant, key: str) -> SettingIssue | None:
    value = ctx.block[key]
    if key == "VideoTune" and value in (None, ""):
        return None  # HandBrake's own spelling of "no tune"
    allowed = getattr(variant, _LISTED_KEYS[key])
    if all(item in allowed for item in _listed_values(key, value)):
        return None
    listed = ", ".join(allowed)
    return _block_issue(ctx.family.name, key, "not_in_list", f"{value!r} is not one of {listed} for {ctx.family.name}")


def _check_quality(ctx: _Block, variant: EncoderVariant) -> SettingIssue | None:
    value = ctx.block["VideoQualitySlider"]
    limits = variant.quality
    name = ctx.family.name
    on_step = float(round((value - limits.low) / limits.step, 6)).is_integer()
    if limits.low <= value <= limits.high and on_step:
        return None
    message = f"{value} is outside {limits.low} to {limits.high} in steps of {limits.step} ({limits.name})"
    return _block_issue(name, "VideoQualitySlider", "out_of_range", message)


def _check_block_values(ctx: _Block) -> list[SettingIssue]:
    """Rule 8: lists of the (family, depth) and the quality scale. VideoOptionExtra is free."""
    variant = _variant(ctx)
    if variant is None:
        return []  # rule 7 reports the depth
    found = [_check_listed_key(ctx, variant, key) for key in _LISTED_KEYS if _well_typed(ctx, key)]
    if _well_typed(ctx, "VideoQualitySlider"):
        found.append(_check_quality(ctx, variant))
    return [issue for issue in found if issue is not None]


def _check_inherited_quality(ctx: _Block) -> list[SettingIssue]:
    """4.4: a quality inherited from the base or template must fit this family's scale."""
    variant = _variant(ctx)
    if variant is None or "VideoQualitySlider" in ctx.block:
        return []
    value = effective_value(ctx.schema, ctx.preset_ref, ctx.settings, "VideoQualitySlider")
    limits = variant.quality
    if not _is_number(value) or limits.low <= value <= limits.high:
        return []
    message = (
        f"inherited quality {value} is outside {limits.low} to {limits.high} ({limits.name}); set one for this encoder"
    )
    return [_block_issue(ctx.family.name, "VideoQualitySlider", "out_of_range", message)]


def _check_rate_control(ctx: _Block) -> list[SettingIssue]:
    """Rule 10."""
    value = effective_value(ctx.schema, ctx.preset_ref, ctx.settings, "VideoQualityType")
    if value in tuple(ctx.family.rate_controls):
        return []
    message = f"{ctx.family.name} does not support rate control {value!r}"
    return [_block_issue(ctx.family.name, "VideoQualityType", "not_supported_by_encoder", message)]


_FLAG_SUPPORT: dict[str, Callable[[EncoderFamily], bool]] = {
    "VideoMultiPass": lambda family: family.multipass,
    "VideoTurboMultiPass": lambda family: family.turbo,
    "x264UseAdvancedOptions": lambda family: family.name == "x264",
    "x264Option": lambda family: family.name == "x264",
}


def _check_flag_support(ctx: _Block) -> list[SettingIssue]:
    """Rule 11."""
    return [
        _block_issue(ctx.family.name, key, "not_supported_by_encoder", f"{ctx.family.name} does not use {key}")
        for key, supported in _FLAG_SUPPORT.items()
        if key in ctx.block and not supported(ctx.family)
    ]


_CLAIM_RULES: tuple[Callable[[_Block], list[SettingIssue]], ...] = (
    _check_block_types,
    _check_bit_depth,
    _check_block_values,
    _check_inherited_quality,
    _check_rate_control,
    _check_flag_support,
)
_SAVE_RULES = (_check_unknown_block_keys, *_CLAIM_RULES)


def _run_rules(
    rules: tuple[Callable[[_Block], list[SettingIssue]], ...],
    schema: HandbrakeSchema,
    name: str,
    preset_ref: str | None,
    settings: HandbrakeSettings,
) -> list[SettingIssue]:
    family = schema.families.get(name)
    if family is None:
        return [_block_issue(name, name, "encoder_not_reachable", f"this HandBrake build has no {name} encoder")]
    ctx = _Block(schema, family, settings.encoders.get(name, {}), preset_ref, settings)
    return [issue for rule in rules for issue in rule(ctx)]


def validate_family(
    schema: HandbrakeSchema, *, family: str, preset_ref: str | None, settings: HandbrakeSettings
) -> list[SettingIssue]:
    """Rules 7, 8, 8a, 10, 11 for one family at claim and encode time. A family without a block is valid."""
    return _run_rules(_CLAIM_RULES, schema, family, preset_ref, settings)


def _check_engine(tool: TranscodeTool, encoder_id: str) -> list[SettingIssue]:
    """Rule 9, and the same for a tool that is not HandBrake: such a preset may not carry settings."""
    if tool == TranscodeTool.HANDBRAKE and get_encoder(encoder_id).engine == "handbrake":
        return []
    return [_issue(_WHOLE, "engine_ignores_settings", "this preset's encoder does not use HandBrake settings")]


def _unreachable_blocks(settings: HandbrakeSettings, reachable: list[str]) -> list[SettingIssue]:
    """Rule 6."""
    return [
        _block_issue(name, name, "encoder_not_reachable", f"the preset's encoder can never use {name}")
        for name in settings.encoders
        if name not in reachable
    ]


def _unknown_base(error: UnknownBasePreset) -> list[SettingIssue]:
    return [_issue("preset_ref", "not_in_list", str(error))]


def _validate_against_base(
    schema: HandbrakeSchema, encoder_id: str, preset_ref: str | None, settings: HandbrakeSettings
) -> list[SettingIssue]:
    reachable = reachable_families(schema, encoder_id, preset_ref)
    base_checked = validate_common(schema, preset_ref, settings.common)
    blocks = [i for name in reachable for i in _run_rules(_SAVE_RULES, schema, name, preset_ref, settings)]
    return [*base_checked, *_unreachable_blocks(settings, reachable), *blocks]


def validate_settings(
    schema: HandbrakeSchema,
    *,
    tool: TranscodeTool,
    encoder_id: str,
    preset_ref: str | None,
    settings: HandbrakeSettings | None,
) -> list[SettingIssue]:
    """Every rule, across all reachable families, for save and read. Never raises on a bad ``preset_ref``."""
    if settings is None or settings.is_empty():
        return []
    engine = _check_engine(tool, encoder_id)
    if engine:
        return engine
    try:
        return _validate_against_base(schema, encoder_id, preset_ref, settings)
    except UnknownBasePreset as error:
        return _unknown_base(error)
