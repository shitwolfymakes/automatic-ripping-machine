"""Tier and default rank per identity source id (1 is the highest tier).
The operator's settings replace the defaults through the
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

# Within a tier, lower rank wins. The default for disc_hint_sources. This
# is the rank map for the *default* settings only, kept as the oracle
# `source_ranks(None)` is tested against; production code computes ranks from
# the operator's config through `source_ranks()`, never by reading this map.
DEFAULT_RANKS: dict[str, int] = {
    "bd_title": 0,
    "label": 1,
    "episodes_tmdb": 0,
    "episodes_tvmaze": 1,
    "episodes_tvdb": 2,
}

# Disc-hint sources in their fixed rank order; the operator's setting only
# switches each one on or off (`hint_sources_setting`).
HINT_SOURCES: tuple[Source, ...] = (BD_TITLE, LABEL)

# Episode-match source id per operator-facing provider setting name.
EPISODE_SOURCE_BY_SETTING: dict[str, str] = {
    "tmdb": "episodes_tmdb",
    "tvmaze": "episodes_tvmaze",
    "tvdb": "episodes_tvdb",
}
# Every episode-match source id, in the settings map's order.
EPISODE_SOURCE_IDS: tuple[str, ...] = tuple(EPISODE_SOURCE_BY_SETTING.values())

# Episode-match provider settings in default rank order (the operator's
# setting overrides it).
DEFAULT_EPISODE_SOURCES: tuple[str, ...] = ("tmdb", "tvmaze", "tvdb")

# Episode-stage defaults, used when a Config row has no value (legacy/in-memory rows).
# Matcher runtime tolerance in seconds.
EPISODE_TOLERANCE_S = 300
# False: every episode-stage result is stored as a suggestion, never applied.
EPISODE_AUTO_APPLY = True
# Stop trying further episode sources once one applies at this coverage (80%).
COVERAGE_STOP = 0.8

# Disc-hint sources by setting value (`disc_hint_sources`).
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
    """The enabled disc hints, always in `HINT_SOURCES` order: the setting is a
    set (membership = enabled), and the disc's own metadata beats its label
    whatever order the list was saved in."""
    values = getattr(cfg, "disc_hint_sources", None)
    if values is None:
        return _DEFAULT_HINT_SETTING
    stored = set(values)
    return tuple(sid for sid in _DEFAULT_HINT_SETTING if sid in stored)


def enabled_hint_sources(cfg: Config | None) -> tuple[Source, ...]:
    return tuple(HINT_SOURCE_BY_SETTING[s] for s in hint_sources_setting(cfg))


def disabled_source_ids(cfg: Config | None) -> frozenset[str]:
    """Ranked-capability sources the operator unchecked (membership = enabled)."""
    every = set(EPISODE_SOURCE_IDS) | set(HINT_SOURCE_BY_SETTING)
    enabled = set(enabled_episode_source_ids(cfg)) | {s.id for s in enabled_hint_sources(cfg)}
    return frozenset(every - enabled)


def source_ranks(cfg: Config | None) -> dict[str, int]:
    """Within-tier rank per enabled source: its position in the operator's list
    (episode sources) or in the fixed `HINT_SOURCES` order (disc hints)."""
    ranks = {sid: i for i, sid in enumerate(enabled_episode_source_ids(cfg))}
    ranks.update({s.id: i for i, s in enumerate(enabled_hint_sources(cfg))})
    return ranks


def episode_tolerance(cfg: Config | None) -> int:
    value = getattr(cfg, "episode_match_tolerance_seconds", None)
    return EPISODE_TOLERANCE_S if value is None else int(value)


def _flag(cfg: Config | None, name: str, default: bool) -> bool:
    """A boolean Config column, or `default` when the row has no value (a legacy or in-memory row)."""
    value = getattr(cfg, name, None)
    return default if value is None else bool(value)


def episode_auto_apply(cfg: Config | None) -> bool:
    return _flag(cfg, "episode_auto_apply", EPISODE_AUTO_APPLY)


# ---------------------------------------------------------------------------
# Online sources. `metadata.source_selection.online_source_ids`
# reads the operator's `movie_sources` / `episode_sources` / `music_sources`
# columns; the tuples below are the defaults it falls back to for a row that
# has no value.
# ---------------------------------------------------------------------------

DEFAULT_MOVIE_SOURCES: tuple[str, ...] = ("tmdb", "omdb")
DEFAULT_MUSIC_SOURCES: tuple[str, ...] = ("musicbrainz",)
DEFAULT_SEARCH_PROVIDERS: dict[str, str] = {"movie": "tmdb", "tv": "tmdb", "music": "musicbrainz"}
# ids a search-provider select or a ranked online list may name, by media type;
# a test pins them to the field metadata.
ONLINE_SOURCE_VALUES: dict[str, tuple[str, ...]] = {
    "movie": ("tmdb", "omdb"),
    "tv": ("tmdb", "omdb", "tvmaze", "tvdb"),
    "music": ("musicbrainz",),
}
_MOVIE_KNOWN = {sid: sid for sid in ONLINE_SOURCE_VALUES["movie"]}
_MUSIC_KNOWN = {sid: sid for sid in ONLINE_SOURCE_VALUES["music"]}


def movie_sources_setting(cfg: Config | None) -> tuple[str, ...]:
    return _ranked(getattr(cfg, "movie_sources", None), _MOVIE_KNOWN, DEFAULT_MOVIE_SOURCES)


def music_sources_setting(cfg: Config | None) -> tuple[str, ...]:
    return _ranked(getattr(cfg, "music_sources", None), _MUSIC_KNOWN, DEFAULT_MUSIC_SOURCES)


def search_provider_setting(cfg: Config | None, media_type: str) -> str:
    """The job page's search provider for `media_type` ("" for an unknown type)."""
    default = DEFAULT_SEARCH_PROVIDERS.get(media_type, "")
    value = getattr(cfg, f"search_provider_{media_type}", None)
    return str(value) if value else default


def movie_auto_apply(cfg: Config | None) -> bool:
    return _flag(cfg, "movie_auto_apply", True)


def music_auto_apply(cfg: Config | None) -> bool:
    return _flag(cfg, "music_auto_apply", True)


def auto_apply_for(cfg: Config | None, kind: str) -> bool:
    """Whether a confident match of this kind is applied by identify (one
    switch per media type; TV shares the episode switch). An
    unknown kind applies: identify never holds a hit it cannot classify."""
    if kind == "movie":
        return movie_auto_apply(cfg)
    if kind == "tv":
        return episode_auto_apply(cfg)
    if kind == "music":
        return music_auto_apply(cfg)
    return True


def crc64service_enabled(cfg: Config | None) -> bool:
    return _flag(cfg, "crc64service_enabled", True)
