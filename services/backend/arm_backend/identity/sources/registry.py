"""Tier and default rank per identity source id (1 is the highest tier).
PR 4 replaces DEFAULT_RANKS with the operator's ranked settings."""

from arm_backend.identity.sources.base import TIER_BY_CAPABILITY, Capability

SOURCE_TIERS: dict[str, int] = {
    "manual": TIER_BY_CAPABILITY[Capability.MANUAL],
    "thediscdb": TIER_BY_CAPABILITY[Capability.DISC_MAP],
    "bd_title": TIER_BY_CAPABILITY[Capability.DISC_HINT],
    "label": TIER_BY_CAPABILITY[Capability.DISC_HINT],
    "preset": TIER_BY_CAPABILITY[Capability.PRESET],
}

# Within a tier, lower rank wins. Spec 4.5 default for disc_hint_sources.
DEFAULT_RANKS: dict[str, int] = {"bd_title": 0, "label": 1}
