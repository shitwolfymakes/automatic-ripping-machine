"""Tier and default rank per identity source id (1 is the highest tier).
PR 4 replaces the defaults with the operator's settings through the
accessors below: `episode_sources_setting`/`enabled_episode_source_ids`,
`hint_sources_setting`/`enabled_hint_sources`, `disabled_source_ids`,
`source_ranks`, `episode_tolerance`, and `episode_auto_apply`."""

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from arm_backend.identity.sources.base import TIER_BY_CAPABILITY, Capability, Source
from arm_backend.identity.sources.bd_title import BD_TITLE
from arm_backend.identity.sources.label_hints import LABEL
from arm_common import Config

if TYPE_CHECKING:
    from arm_backend.metadata.sources import OnlineSource

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

# Within a tier, lower rank wins. Spec 4.5 default for disc_hint_sources. This
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


# ---------------------------------------------------------------------------
# Online sources (spec §5.2). PR 2 makes `online_source_ids` read the operator's
# `movie_sources` / `episode_sources` / `music_sources` columns; until then the
# order is the one the dispatcher hard-coded before PR 0.
# ---------------------------------------------------------------------------

DEFAULT_ONLINE_SOURCES: dict[str, tuple[str, ...]] = {
    "movie": ("tmdb", "omdb"),
    "tv": ("tmdb", "omdb"),
    "music": ("musicbrainz",),
}
# Step 2 fingerprint sources (PR 1 adds the `crc64service_enabled` switch).
DEFAULT_FINGERPRINT_SOURCES: tuple[str, ...] = ("arm_server",)


def online_source_ids(cfg: Config | None, media_type: str) -> tuple[str, ...]:
    """Source ids for `media_type` in the order they are tried."""
    return DEFAULT_ONLINE_SOURCES.get(media_type, ())


def sources_for(
    cfg: Config | None, media_type: str, registry: Mapping[str, "OnlineSource"]
) -> tuple["OnlineSource", ...]:
    """The sources to try for `media_type`, in order: listed, present in the
    registry, serving that media type, and configured. The only function that
    decides online order or enablement."""
    out: list[OnlineSource] = []
    for sid in online_source_ids(cfg, media_type):
        source = registry.get(sid)
        if source is None or media_type not in source.media_types:
            continue
        if source.configured(cfg) is not None:
            continue
        out.append(source)
    return tuple(out)


def search_source(cfg: Config | None, media_type: str, registry: Mapping[str, "OnlineSource"]) -> "OnlineSource | None":
    """The source behind the job page's search box for `media_type`: the first
    usable listed source. Honours the legacy `metadata_provider` setting until
    PR 1 replaces it with `search_provider_*`."""
    ranked = sources_for(cfg, media_type, registry)
    preferred = getattr(cfg, "metadata_provider", None)
    if media_type in ("movie", "tv") and preferred is not None:
        for source in ranked:
            if source.id == preferred:
                return source
    return ranked[0] if ranked else None


def lookup_sources(
    cfg: Config | None, media_type: str, registry: Mapping[str, "OnlineSource"]
) -> tuple["OnlineSource", ...]:
    """`sources_for` with the Search card's preferred source first (spec: the
    operator's chosen provider answers an exact-id lookup before the rest)."""
    ranked = sources_for(cfg, media_type, registry)
    preferred = search_source(cfg, media_type, registry)
    if preferred is None:
        return ranked
    return (preferred, *(s for s in ranked if s is not preferred))


def fingerprint_sources(cfg: Config | None, registry: Mapping[str, "OnlineSource"]) -> tuple["OnlineSource", ...]:
    """Step 2 sources that answer a disc fingerprint, in order."""
    out: list[OnlineSource] = []
    for sid in DEFAULT_FINGERPRINT_SOURCES:
        source = registry.get(sid)
        if source is not None and source.configured(cfg) is None:
            out.append(source)
    return tuple(out)


def known_source_ids(media_type: str, registry: Mapping[str, "OnlineSource"]) -> tuple[str, ...]:
    """Every registered source id that serves `media_type` (validation lists)."""
    return tuple(sid for sid, source in registry.items() if media_type in source.media_types)
