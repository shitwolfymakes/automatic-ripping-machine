"""Tier and default rank per identity source id (1 is the highest tier).
PR 4 replaces DEFAULT_RANKS with the operator's ranked settings."""

from arm_backend.identity.sources.base import TIER_BY_CAPABILITY, Capability, Source
from arm_backend.identity.sources.bd_title import BD_TITLE
from arm_backend.identity.sources.label_hints import LABEL

SOURCE_TIERS: dict[str, int] = {
    "manual": TIER_BY_CAPABILITY[Capability.MANUAL],
    "thediscdb": TIER_BY_CAPABILITY[Capability.DISC_MAP],
    "bd_title": TIER_BY_CAPABILITY[Capability.DISC_HINT],
    "label": TIER_BY_CAPABILITY[Capability.DISC_HINT],
    "preset": TIER_BY_CAPABILITY[Capability.PRESET],
}

# Within a tier, lower rank wins. Spec 4.5 default for disc_hint_sources.
DEFAULT_RANKS: dict[str, int] = {"bd_title": 0, "label": 1}

# Disc-hint sources in default rank order (PR 4 makes this the operator's setting).
HINT_SOURCES: tuple[Source, ...] = (BD_TITLE, LABEL)
