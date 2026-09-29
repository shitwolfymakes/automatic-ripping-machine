"""Cross-disc continuity (spec 6.3): which episodes are still unclaimed and
where this disc should start, plus ranking of per-season match results.

`start_anchor`'s sentinel for "no remaining episode reaches the target
position" is `len(remaining)` (one past the last remaining episode), not
`len(remaining) - 1` — `align()`'s DP indexes episodes 0..n inclusive, so an
anchor of `len(remaining)` is a valid, meaningful position (it pulls the free
trailing rule toward "nothing here matches, skip the title")."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from arm_backend.identity.episodes.model import Episode, MatchResult


@dataclass(frozen=True)
class SiblingDisc:
    disc_number: int | None
    episodes: frozenset[int]


def _index_at_or_above(remaining: Sequence[Episode], number: int, *, strictly_above: bool) -> int:
    for idx, ep in enumerate(remaining):
        if ep.number > number or (not strictly_above and ep.number >= number):
            return idx
    return len(remaining)


def start_anchor(
    season: Sequence[Episode],
    *,
    disc_number: int | None,
    disc_total: int | None,
    n_titles: int,
    siblings: Sequence[SiblingDisc],
) -> tuple[list[Episode], int | None]:
    claimed = frozenset().union(*(s.episodes for s in siblings)) if siblings else frozenset()
    remaining = [e for e in season if e.number not in claimed]

    lower = [
        max(s.episodes)
        for s in siblings
        if s.episodes and disc_number is not None and s.disc_number is not None and s.disc_number < disc_number
    ]
    if lower:
        idx = _index_at_or_above(remaining, max(lower), strictly_above=True)
        return remaining, min(idx, len(remaining))

    if disc_number is not None and season:
        n = len(season)
        if disc_total is not None and disc_total > 1:
            pos = round((disc_number - 1) * (n - n_titles) / (disc_total - 1))
        elif disc_total == 1:
            pos = 0
        else:
            pos = (disc_number - 1) * n_titles
        pos = min(max(pos, 0), n - 1)
        idx = _index_at_or_above(remaining, season[pos].number, strictly_above=False)
        return remaining, min(idx, len(remaining))

    return remaining, None


def rank_seasons(results: Mapping[int, MatchResult]) -> list[tuple[int, MatchResult]]:
    return sorted(
        results.items(),
        key=lambda item: (-item[1].coverage, item[1].cost / max(1, len(item[1].matches)), item[0]),
    )
