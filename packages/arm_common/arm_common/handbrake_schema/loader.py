"""Turn libhb's raw schema dump plus the overlay into a HandbrakeSchema.

``load_schema`` is a pipeline of small builders, one per part of the result. All of it is pure; the
only side effect is one INFO log line per mismatch list between the dump and the overlay.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any

from arm_common.handbrake_schema.overlay import (
    ARM_OWNED_KEYS,
    DEFAULT_RATE_CONTROLS,
    FILTER_TAB_KEYS,
    KEY_OVERLAY,
    QSV_QUALITY_FALLBACK,
    TURBO_FAMILIES,
)
from arm_common.handbrake_schema.types import (
    EncoderFamily,
    EncoderVariant,
    FilterSpec,
    HandbrakeSchema,
    KeySpec,
    KeyType,
    QualityLimits,
)

logger = logging.getLogger("arm_common.handbrake_schema")

_DEPTH_SUFFIX = re.compile(r"_(\d+)bit$")
_WORD_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_OTHER_GROUP = "Other"

# First matching prefix wins; anything else lands on Summary.
_PREFIX_TABS: tuple[tuple[str, str], ...] = (
    ("Audio", "audio"),
    ("Subtitle", "subtitles"),
    ("Video", "video"),
    ("Picture", "dimensions"),
    ("Chapter", "chapters"),
)


def content_hash(raw: dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON form of the raw dump; identifies a schema."""
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def family_and_depth(encoder_name: str, libhb_depth: int) -> tuple[str, int]:
    """Split an encoder name into (family, bit depth). The ``_NNbit`` suffix beats libhb's depth,
    which reports 8 for ``vce_av1_10bit``."""
    suffix = _DEPTH_SUFFIX.search(encoder_name)
    if suffix is None:
        return encoder_name, libhb_depth
    return encoder_name[: suffix.start()], int(suffix.group(1))


def tab_for_key(key: str, filter_keys: frozenset[str]) -> str:
    """The prefix rule: the tab of a key the overlay has no row for."""
    if key in filter_keys:
        return "filters"
    return next((tab for prefix, tab in _PREFIX_TABS if key.startswith(prefix)), "summary")


def _key_type(default: Any) -> KeyType:
    if isinstance(default, bool):
        return "bool"
    if isinstance(default, list):
        return "list_obj" if any(isinstance(item, dict) for item in default) else "list_str"
    scalar: dict[type, KeyType] = {int: "int", float: "float", str: "str"}
    return scalar[type(default)]


def _label_from_key(key: str) -> str:
    words = _WORD_BOUNDARY.sub(" ", key).lower()
    return words[:1].upper() + words[1:]


def _key_spec(name: str, default: Any) -> KeySpec:
    overlay = KEY_OVERLAY.get(name)
    if overlay is None:
        return KeySpec(
            name=name,
            type=_key_type(default),
            default=default,
            tab=tab_for_key(name, FILTER_TAB_KEYS),
            group=_OTHER_GROUP,
            label=_label_from_key(name),
            source=None,
            limits=None,
            known=name in ARM_OWNED_KEYS,
        )
    return KeySpec(
        name=name,
        type=_key_type(default),
        default=default,
        tab=overlay.tab,
        group=overlay.group,
        label=overlay.label,
        source=overlay.source,
        limits=overlay.limits,
        known=True,
    )


def _build_keys(defaults: dict[str, Any]) -> dict[str, KeySpec]:
    """Overlay-known keys in overlay row order (tab, group, row), then the rest in dump order."""
    overlay_order = {name: index for index, name in enumerate(KEY_OVERLAY)}
    # sorted() is stable, so keys the overlay does not know keep the dump order after the known ones.
    names = sorted(defaults, key=lambda name: overlay_order.get(name, len(overlay_order)))
    return {name: _key_spec(name, defaults[name]) for name in names}


def _quality(item: dict[str, Any]) -> QualityLimits:
    quality = item["quality"]
    if quality is None:
        return QSV_QUALITY_FALLBACK
    return QualityLimits(quality["low"], quality["high"], quality["step"], quality["name"])


def _variant(item: dict[str, Any], depth: int) -> EncoderVariant:
    return EncoderVariant(
        encoder=item["name"],
        depth=depth,
        presets=tuple(item["presets"]),
        tunes=tuple(item["tunes"]),
        profiles=tuple(item["profiles"]),
        levels=tuple(item["levels"]),
        quality=_quality(item),
    )


def _group_encoders(encoders: list[dict[str, Any]]) -> dict[str, list[tuple[int, dict[str, Any]]]]:
    grouped: dict[str, list[tuple[int, dict[str, Any]]]] = {}
    for item in encoders:
        family, depth = family_and_depth(item["name"], item["depth"])
        grouped.setdefault(family, []).append((depth, item))
    return grouped


def _family(name: str, members: list[tuple[int, dict[str, Any]]]) -> EncoderFamily:
    return EncoderFamily(
        name=name,
        codec_id=members[0][1]["codec_id"],
        variants={depth: _variant(item, depth) for depth, item in members},
        multipass=any(item["multipass"] for _, item in members),
        turbo=name in TURBO_FAMILIES,
        rate_controls=DEFAULT_RATE_CONTROLS,
    )


def _build_families(encoders: list[dict[str, Any]]) -> dict[str, EncoderFamily]:
    return {name: _family(name, members) for name, members in _group_encoders(encoders).items()}


def _names(items: list[dict[str, Any]]) -> tuple[str, ...]:
    return tuple(item["name"] for item in items)


def _samplerate_spelling(hertz: int) -> str:
    """A sample rate as presets store it: kHz without trailing zeros (48000 -> "48", 44100 -> "44.1")."""
    return f"{hertz / 1000:g}"


def _build_lists(raw: dict[str, Any]) -> dict[str, Any]:
    encoders = raw["audio_encoders"]
    return {
        "audio_encoders": _names(encoders),
        "mixdowns": _names(raw["mixdowns"]),
        "audio_samplerates": tuple(
            _samplerate_spelling(rate) for rate in sorted({r for enc in encoders for r in enc["samplerates"]})
        ),
        "audio_bitrates": tuple(raw["audio_bitrates"]),
        "audio_dithers": _names(raw["audio_dithers"]),
        "video_framerates": _names(raw["video_framerates"]),
        "containers": _names(raw["containers"]),
        "audio_mixdowns_by_encoder": {enc["name"]: tuple(enc["mixdowns"]) for enc in encoders},
    }


def _build_filters(filters: dict[str, Any]) -> dict[str, FilterSpec]:
    return {
        name: FilterSpec(presets=tuple(spec["presets"]), tunes=tuple(spec["tunes"])) for name, spec in filters.items()
    }


def _log_overlay_mismatch(dump_keys: set[str]) -> None:
    unlabelled = sorted(dump_keys - set(KEY_OVERLAY) - ARM_OWNED_KEYS)
    vanished = sorted(set(KEY_OVERLAY) - dump_keys)
    if unlabelled:
        logger.info("HandBrake schema: keys missing from the overlay, shown under Other: %s", unlabelled)
    if vanished:
        logger.info("HandBrake schema: overlay keys missing from the dump, ignored: %s", vanished)


def load_schema(raw: dict[str, Any]) -> HandbrakeSchema:
    keys = _build_keys(raw["preset_template"])
    audio_item_keys = _build_keys(raw["template_audio_item"])
    _log_overlay_mismatch(set(keys) | set(audio_item_keys))
    return HandbrakeSchema(
        handbrake_tag=raw["handbrake_tag"],
        preset_version=tuple(raw["preset_version"]),
        keys=keys,
        audio_item_keys=audio_item_keys,
        families=_build_families(raw["video_encoders"]),
        lists=_build_lists(raw),
        filters=_build_filters(raw["filters"]),
        builtin_presets=raw["builtin_presets"],
        content_hash=content_hash(raw),
    )
