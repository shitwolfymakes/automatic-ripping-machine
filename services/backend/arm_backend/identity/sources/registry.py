"""Tier per identity source id; 1 is highest. Tiers 3 (episode match) and 4
(disc hints) are filled in by later sources."""

SOURCE_TIERS: dict[str, int] = {
    "manual": 1,
    "thediscdb": 2,
    "preset": 5,
}
