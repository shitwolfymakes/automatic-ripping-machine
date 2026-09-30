"""Tier and default rank per identity source id (1 is the highest tier).
PR 4 replaces DEFAULT_RANKS with the operator's ranked settings."""

from arm_backend.identity.sources.base import TIER_BY_CAPABILITY, Capability, Source
from arm_backend.identity.sources.bd_title import BD_TITLE
from arm_backend.identity.sources.label_hints import LABEL

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

# Episode-stage settings until PR 4 adds them to Config.
# Matcher runtime tolerance in seconds.
EPISODE_TOLERANCE_S = 300
# False: every episode-stage result is stored as a suggestion, never applied.
EPISODE_AUTO_APPLY = True
# Stop trying further episode sources once one applies at this coverage (spec 5: 80%).
COVERAGE_STOP = 0.8
# Most seasons scanned when the job's season is unknown.
MAX_SEASON_SCAN = 10
