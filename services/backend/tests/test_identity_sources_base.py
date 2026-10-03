"""Source protocol and capability tiers."""

from arm_backend.identity.sources.base import TIER_BY_CAPABILITY, Capability
from arm_backend.identity.sources.registry import DEFAULT_RANKS, SOURCE_TIERS


def test_tiers_follow_capabilities() -> None:
    assert SOURCE_TIERS["manual"] == TIER_BY_CAPABILITY[Capability.MANUAL]
    assert SOURCE_TIERS["thediscdb"] == TIER_BY_CAPABILITY[Capability.DISC_MAP]
    assert SOURCE_TIERS["bd_title"] == SOURCE_TIERS["label"] == TIER_BY_CAPABILITY[Capability.DISC_HINT]
    assert SOURCE_TIERS["preset"] == TIER_BY_CAPABILITY[Capability.PRESET]


def test_default_hint_ranks_prefer_bd_title() -> None:
    assert DEFAULT_RANKS["bd_title"] < DEFAULT_RANKS["label"]
