"""Types of the loaded HandBrake schema. Plain frozen dataclasses; no behaviour."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

KeyType = Literal["bool", "int", "float", "str", "list_str", "list_obj"]
SourceKind = Literal["static", "schema_list", "filter_presets", "filter_tunes", "audio_mixdowns"]


@dataclass(frozen=True)
class QualityLimits:
    low: float
    high: float
    step: float
    name: str


@dataclass(frozen=True)
class EncoderVariant:
    """One HandBrake encoder: a family at one bit depth."""

    encoder: str
    depth: int
    presets: tuple[str, ...]
    tunes: tuple[str, ...]
    profiles: tuple[str, ...]
    levels: tuple[str, ...]
    quality: QualityLimits


@dataclass(frozen=True)
class EncoderFamily:
    name: str
    codec_id: int
    variants: dict[int, EncoderVariant]
    multipass: bool
    turbo: bool
    rate_controls: frozenset[int]


@dataclass(frozen=True)
class ValueSource:
    """Where a key's allowed values come from.

    ``static``: ``ref`` names a STATIC_ENUMS entry. ``schema_list``: ``ref`` names an entry of
    ``HandbrakeSchema.lists``. ``filter_presets`` / ``filter_tunes``: ``ref`` is a filter name, or the
    key that selects the filter. ``audio_mixdowns``: ``ref`` is the key naming the audio encoder.
    """

    kind: SourceKind
    ref: str


@dataclass(frozen=True)
class KeySpec:
    name: str
    type: KeyType
    default: Any
    tab: str
    group: str
    label: str
    source: ValueSource | None
    limits: tuple[float, float] | None
    known: bool  # False: missing from the overlay, shown under "Other"


@dataclass(frozen=True)
class FilterSpec:
    presets: tuple[str, ...]
    tunes: tuple[str, ...]


@dataclass(frozen=True)
class HandbrakeSchema:
    handbrake_tag: str
    preset_version: tuple[int, int, int]
    keys: dict[str, KeySpec]
    audio_item_keys: dict[str, KeySpec]
    families: dict[str, EncoderFamily]
    lists: dict[str, Any]
    filters: dict[str, FilterSpec]
    builtin_presets: dict[str, dict[str, Any]]
    content_hash: str
