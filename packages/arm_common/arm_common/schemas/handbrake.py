"""Wire models of a transcode preset's HandBrake settings and of the issues validation reports."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from arm_common.enums import ContainerFormat

IssueCode = Literal[
    "unknown_key",
    "not_allowed_here",
    "wrong_type",
    "not_in_list",
    "out_of_range",
    "encoder_not_reachable",
    "engine_ignores_settings",
    "not_supported_by_encoder",
]


class SettingIssue(BaseModel):
    """One reason a setting is rejected. ``encoder`` names the block it sits in; None for ``common``."""

    key: str
    encoder: str | None = None
    code: IssueCode
    message: str


class HandbrakeSettings(BaseModel):
    """Settings every encoder shares (``common``) plus one block per encoder family (``encoders``)."""

    common: dict[str, Any] = Field(default_factory=dict)
    encoders: dict[str, dict[str, Any]] = Field(default_factory=dict)

    def is_empty(self) -> bool:
        return not self.common and not any(self.encoders.values())


class ImportProposal(BaseModel):
    """The preset an import would create from one HandBrake export entry."""

    name: str
    container: ContainerFormat
    encoder: str
    handbrake_settings: HandbrakeSettings


class ImportedPresetView(BaseModel):
    """One export entry as the review step shows it: the proposal plus everything the import changed."""

    path: list[str]
    name: str
    proposal: ImportProposal | None
    source_encoder: str
    dropped_keys: list[str]
    not_imported: list[str]
    copied_depth_to: list[str]
    eight_bit_only: list[str]
    warnings: list[str]
    issues: list[SettingIssue]
    importable: bool
    reason: str | None = None


class ImportParseResponse(BaseModel):
    handbrake_version: dict[str, str]
    presets: list[ImportedPresetView]


class SlimSource(BaseModel):
    kind: str
    ref: str


class SlimKey(BaseModel):
    name: str
    type: str
    default: Any
    tab: str
    group: str
    label: str
    source: SlimSource | None
    limits: tuple[float, float] | None
    known: bool
    option_labels: dict[str, str] | None = None


class SlimQuality(BaseModel):
    name: str
    low: float
    high: float
    step: float


class SlimVariant(BaseModel):
    encoder: str
    depth: int
    presets: list[str]
    tunes: list[str]
    profiles: list[str]
    levels: list[str]
    quality: SlimQuality


class SlimFamily(BaseModel):
    name: str
    codec_id: int
    multipass: bool
    turbo: bool
    rate_controls: list[int]
    variants: list[SlimVariant]


class SlimFilter(BaseModel):
    presets: list[str]
    tunes: list[str]


class HandbrakeSchemaSlimView(BaseModel):
    """What the UI needs to render the settings sidebar; no built-in preset values."""

    handbrake_tag: str
    preset_version: str
    content_hash: str
    keys: list[SlimKey]
    audio_item_keys: list[SlimKey]
    families: list[SlimFamily]
    lists: dict[str, list[Any]]
    audio_mixdowns_by_encoder: dict[str, list[str]]
    filters: dict[str, SlimFilter]
    builtin_names: list[str]
    static_enums: dict[str, list[Any]]
    source_extras: dict[str, list[Any]]
    selector_filter_aliases: dict[str, str]
    # Keys ARM sets itself (never stored as settings) and keys that live in a per-encoder block.
    arm_owned_keys: list[str]
    encoder_specific_keys: list[str]
    hidden_keys: list[str]
