"""Which online sources answer a lookup, a search or a fingerprint, in order, from the operator's settings."""

import logging
from collections.abc import Mapping
from typing import TYPE_CHECKING

from arm_backend.identity.sources.registry import (
    crc64service_enabled,
    episode_sources_setting,
    movie_sources_setting,
    music_sources_setting,
    search_provider_setting,
)
from arm_common import Config

if TYPE_CHECKING:
    from arm_backend.metadata.sources import OnlineSource

logger = logging.getLogger(__name__)

# Step 2 fingerprint sources, gated as a whole by `crc64service_enabled`.
DEFAULT_FINGERPRINT_SOURCES: tuple[str, ...] = ("arm_server",)


def online_source_ids(cfg: Config | None, media_type: str) -> tuple[str, ...]:
    """Source ids for `media_type` in the order they are tried: the operator's
    ranked list per type. The TV list is the episode list; ids whose
    adapter does not exist yet are dropped by `sources_for`."""
    if media_type == "movie":
        return movie_sources_setting(cfg)
    if media_type == "tv":
        return episode_sources_setting(cfg)
    if media_type == "music":
        return music_sources_setting(cfg)
    return ()


def sources_for(
    cfg: Config | None, media_type: str, registry: Mapping[str, "OnlineSource"]
) -> tuple["OnlineSource", ...]:
    """The sources to try for `media_type`, in order: listed, present in the
    registry, serving that media type, and configured. The only function that
    decides AUTOMATIC online order or enablement; the job page's search box
    adds the operator's explicit per-type provider on top (`search_source`)."""
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
    """The source behind the job page's search box for `media_type`: the
    operator's `search_provider_<type>` whenever that source is registered,
    serves the type and is configured, else the first usable source from the
    ranked automatic list.

    The chosen provider does NOT have to be on that ranked list — the two
    settings are independent. `search_provider_tv` offers OMDb, which the
    automatic TV order (`episode_sources`) deliberately does not
    carry, and a music search box still answers after `music_sources` is
    cleared to stop automatic CD lookups. Matching against the ranked list
    alone silently ignored both choices. A provider that genuinely cannot be
    used (no key, or no adapter yet) falls back and is logged, since the job
    page shows the operator's choice as a badge either way."""
    preferred = search_provider_setting(cfg, media_type)
    chosen = registry.get(preferred) if preferred else None
    if chosen is None:
        unusable = f"no adapter named {preferred}"
    elif media_type not in chosen.media_types:
        unusable = f"{preferred} does not search {media_type}"
    else:
        unusable = chosen.configured(cfg) or ""
        if not unusable:
            return chosen
    ranked = sources_for(cfg, media_type, registry)
    fallback = ranked[0] if ranked else None
    if preferred and fallback is not None:
        logger.info("search provider %s unusable (%s); using %s for %s", preferred, unusable, fallback.id, media_type)
    return fallback


def lookup_sources(
    cfg: Config | None, media_type: str, registry: Mapping[str, "OnlineSource"]
) -> tuple["OnlineSource", ...]:
    """`sources_for` with the Search card's preferred source first (the
    operator's chosen provider answers an exact-id lookup before the rest)."""
    ranked = sources_for(cfg, media_type, registry)
    preferred = search_source(cfg, media_type, registry)
    if preferred is None:
        return ranked
    return (preferred, *(s for s in ranked if s is not preferred))


def fingerprint_sources(cfg: Config | None, registry: Mapping[str, "OnlineSource"]) -> tuple["OnlineSource", ...]:
    """Step 2 sources that answer a disc fingerprint, in order; none when the
    `crc64service_enabled` switch is off (it gates the whole fingerprint walk)."""
    if not crc64service_enabled(cfg):
        return ()
    out: list[OnlineSource] = []
    for sid in DEFAULT_FINGERPRINT_SOURCES:
        source = registry.get(sid)
        if source is not None and source.configured(cfg) is None:
            out.append(source)
    return tuple(out)


def known_source_ids(media_type: str, registry: Mapping[str, "OnlineSource"]) -> tuple[str, ...]:
    """Every registered source id that serves `media_type` (validation lists)."""
    return tuple(sid for sid, source in registry.items() if media_type in source.media_types)
