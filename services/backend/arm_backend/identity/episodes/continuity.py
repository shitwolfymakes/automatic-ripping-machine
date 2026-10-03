"""Cross-disc continuity (spec 6.3): which episodes are still unclaimed and
where this disc should start, plus ranking of per-season match results.

`start_anchor`'s sentinel for "no remaining episode reaches the target
position" is `len(remaining)` (one past the last remaining episode), not
`len(remaining) - 1` — `align()`'s DP indexes episodes 0..n inclusive, so an
anchor of `len(remaining)` is a valid, meaningful position (it pulls the free
trailing rule toward "nothing here matches, skip the title")."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace

from arm_backend.identity.episodes.matcher import align
from arm_backend.identity.episodes.model import Episode, MatchResult, TitleIn


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
        key=lambda item: (
            -item[1].coverage,
            -len(item[1].matches),
            item[1].cost / max(1, len(item[1].matches)),
            item[0],
        ),
    )


def _runs(remaining: Sequence[Episode], claimed: frozenset[int]) -> list[tuple[int, list[Episode]]]:
    """Split into (start index, episodes) runs at sibling-held numbers, within
    the single season `align_runs` requires of `remaining`."""
    runs: list[tuple[int, list[Episode]]] = []
    for idx, ep in enumerate(remaining):
        prev = remaining[idx - 1] if idx else None
        breaks = prev is None or any(prev.number < c < ep.number for c in claimed)
        if breaks:
            runs.append((idx, [ep]))
        else:
            runs[-1][1].append(ep)
    return runs


def align_runs(
    titles: Sequence[TitleIn],
    remaining: Sequence[Episode],
    *,
    claimed: frozenset[int],
    tolerance: int = 300,
    anchor: int | None = None,
) -> MatchResult:
    """Align within each run of episodes no sibling disc holds (spec 6.3): a
    disc can never span another disc's episodes, while plain gaps in the
    provider's numbering stay inside one run.

    `remaining` must be a single season (raises `ValueError` otherwise);
    `claimed` is that season's sibling-held episode numbers."""
    if len({e.season for e in remaining}) > 1:
        raise ValueError("align_runs requires remaining to hold a single season")
    runs = _runs(remaining, claimed) or [(0, [])]
    last = len(runs) - 1
    results = []
    for order, (start, eps) in enumerate(runs):
        local = (
            anchor - start
            if anchor is not None
            and (start <= anchor < start + len(eps) or (order == last and anchor == start + len(eps)))
            else None
        )
        results.append((order, align(titles, eps, tolerance=tolerance, anchor=local)))
    ranked = sorted(results, key=lambda r: (-r[1].coverage, -len(r[1].matches), r[1].cost, r[0]))
    best = ranked[0][1]
    if len(ranked) > 1:
        second = ranked[1][1]
        if (
            second.coverage == best.coverage
            and len(second.matches) == len(best.matches)
            and abs(second.cost - best.cost) <= 60
            and best.matches
        ):
            return replace(best, ambiguous=True)
    return best
