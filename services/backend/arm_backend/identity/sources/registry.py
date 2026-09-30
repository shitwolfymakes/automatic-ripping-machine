"""Tier and default rank per identity source id (1 is the highest tier).
PR 4 replaces the defaults with the operator's settings through the
accessors below: `episode_sources_setting`/`enabled_episode_source_ids`,
`hint_sources_setting`/`enabled_hint_sources`, `disabled_source_ids`,
`source_ranks`, `episode_tolerance`, and `episode_auto_apply`."""

from collections.abc import Mapping, Sequence

from arm_backend.identity.sources.base import TIER_BY_CAPABILITY, Capability, Source
from arm_backend.identity.sources.bd_title import BD_TITLE
from arm_backend.identity.sources.label_hints import LABEL
from arm_common import Config

SOURCE_TIERS: dict[str, int] = {
    "manual": TIER_BY_CAPABILITY[Capability.MANUAL],
    "thediscdb": TIER_BY_CAPABILITY[Capability.DISC_MAP],
    "episodes_tmdb": TIER_BY_CAPABILITY[Capability.EPISODE_MATCH],
    "episodes_tvmaze": TIER_BY_CAPABILITY[Capability.EPISODE_MATCH],
    "episodes_tvdb": TIER_BY_CAPABILITY[Capability.EPISODE_MATCH],
    "bd_title": TIER_BY_CAPABILITY[Capability.DISC_HINT],
    "label": TIER_BY_CAPABILITY[Capability.DISC_HINT],
    "preset": TIER_BY_CAPABILITY[Capability.PRESET],
}

# Within a tier, lower rank wins. Spec 4.5 default for disc_hint_sources.
DEFAULT_RANKS: dict[str, int] = {
    "bd_title": 0,
    "label": 1,
    "episodes_tmdb": 0,
    "episodes_tvmaze": 1,
    "episodes_tvdb": 2,
}

# Disc-hint sources in default rank order (PR 4 makes this the operator's setting).
HINT_SOURCES: tuple[Source, ...] = (BD_TITLE, LABEL)

# Episode-match source id per operator-facing provider setting name.
EPISODE_SOURCE_BY_SETTING: dict[str, str] = {
    "tmdb": "episodes_tmdb",
    "tvmaze": "episodes_tvmaze",
    "tvdb": "episodes_tvdb",
}

# Episode-match provider settings in default rank order (spec 4.5 default;
# PR 4 makes this the operator's setting).
DEFAULT_EPISODE_SOURCES: tuple[str, ...] = ("tmdb", "tvmaze", "tvdb")

# Episode-stage defaults, used when a Config row has no value (legacy/in-memory rows).
# Matcher runtime tolerance in seconds.
EPISODE_TOLERANCE_S = 300
# False: every episode-stage result is stored as a suggestion, never applied.
EPISODE_AUTO_APPLY = True
# Stop trying further episode sources once one applies at this coverage (spec 5: 80%).
COVERAGE_STOP = 0.8
# Most seasons scanned when the job's season is unknown.
MAX_SEASON_SCAN = 10

# Disc-hint sources by setting value (spec 4.5 `disc_hint_sources`).
HINT_SOURCE_BY_SETTING: dict[str, Source] = {BD_TITLE.id: BD_TITLE, LABEL.id: LABEL}
_DEFAULT_HINT_SETTING: tuple[str, ...] = tuple(s.id for s in HINT_SOURCES)


def _ranked(values: Sequence[str] | None, known: Mapping[str, object], default: tuple[str, ...]) -> tuple[str, ...]:
    """The operator's ranked list, keeping known values in order, deduplicated;
    the default when the column is missing (a legacy or in-memory row)."""
    if values is None:
        return default
    seen: list[str] = []
    for v in values:
        if v in known and v not in seen:
            seen.append(v)
    return tuple(seen)


def episode_sources_setting(cfg: Config | None) -> tuple[str, ...]:
    return _ranked(getattr(cfg, "episode_sources", None), EPISODE_SOURCE_BY_SETTING, DEFAULT_EPISODE_SOURCES)


def enabled_episode_source_ids(cfg: Config | None) -> tuple[str, ...]:
    return tuple(EPISODE_SOURCE_BY_SETTING[s] for s in episode_sources_setting(cfg))


def hint_sources_setting(cfg: Config | None) -> tuple[str, ...]:
    return _ranked(getattr(cfg, "disc_hint_sources", None), HINT_SOURCE_BY_SETTING, _DEFAULT_HINT_SETTING)


def enabled_hint_sources(cfg: Config | None) -> tuple[Source, ...]:
    return tuple(HINT_SOURCE_BY_SETTING[s] for s in hint_sources_setting(cfg))


def disabled_source_ids(cfg: Config | None) -> frozenset[str]:
    """Ranked-capability sources the operator unchecked (spec 4.5: membership = enabled)."""
    every = set(EPISODE_SOURCE_BY_SETTING.values()) | set(HINT_SOURCE_BY_SETTING)
    enabled = set(enabled_episode_source_ids(cfg)) | {s.id for s in enabled_hint_sources(cfg)}
    return frozenset(every - enabled)


def source_ranks(cfg: Config | None) -> dict[str, int]:
    """Within-tier rank per enabled source: its position in the operator's list."""
    ranks = {sid: i for i, sid in enumerate(enabled_episode_source_ids(cfg))}
    ranks.update({s.id: i for i, s in enumerate(enabled_hint_sources(cfg))})
    return ranks


def episode_tolerance(cfg: Config | None) -> int:
    value = getattr(cfg, "episode_match_tolerance_seconds", None)
    return EPISODE_TOLERANCE_S if value is None else int(value)


def episode_auto_apply(cfg: Config | None) -> bool:
    value = getattr(cfg, "episode_auto_apply", None)
    return EPISODE_AUTO_APPLY if value is None else bool(value)
