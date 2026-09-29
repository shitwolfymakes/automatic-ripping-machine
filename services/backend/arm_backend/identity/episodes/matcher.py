"""Ordered alignment of disc titles to a season's episodes (spec 6.2).

Both sequences stay monotone: disc order maps to episode order. A title can
match one episode, two consecutive episodes (a double-length title), or be
skipped (extras, trailers); an episode can be skipped between matches (it
lives on another disc or was not ripped). Leading and trailing episodes are
free to skip, so the disc may sit anywhere in the season; `anchor` pulls the
start toward the position cross-disc continuity predicts.

A match made after an earlier title's match pays for every episode number
missing between it and the list entry before it (claimed by a sibling disc or
absent from the provider), so a run does not jump a hole for free. When
shifting the single-episode matches one position either way fits about as well,
the result is flagged `ambiguous`: its positions came from the anchor or list
order, not from runtimes.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from typing import cast

from arm_backend.identity.episodes.model import Episode, MatchResult, TitleIn, TitleMatch

DOUBLE_PENALTY = 60
ANCHOR_WEIGHT = 30
FREE_START_WEIGHT = 1
# A title this close to the sum of exactly two other titles is a play-all.
PLAY_ALL_PAIR_WINDOW_S = 10
# A shifted mapping whose total delta is this close to the chosen one is as plausible.
AMBIGUITY_WINDOW_S = 60
_INF = float("inf")


def _known(runtime: int | None) -> int | None:
    return runtime if runtime is not None and runtime > 0 else None


def _eff_tol(reference: int, tolerance: int) -> int:
    """Effective tolerance: clamp to [60, tolerance] based on reference."""
    return min(tolerance, max(60, reference // 10))


def _is_play_all(
    seconds: int, episodes: Sequence[Episode], tolerance: int, ref_rt: int, titles: Sequence[TitleIn], title_idx: int
) -> bool:
    """Check if a title is play-all: matches sum of 3+ consecutive episodes, or sum of the other titles
    (within tolerance for 3+ others; within PLAY_ALL_PAIR_WINDOW_S for exactly 2, where a genuine two-part
    title is otherwise just as likely)."""
    # Rule B: in play-all scan, treat unknown runtime as ref_rt
    runtimes = [_known(e.runtime_s) or ref_rt for e in episodes]

    # Check if title matches sum of 3+ consecutive episodes
    for start in range(len(runtimes)):
        total = 0
        for k in range(start, len(runtimes)):
            rt = runtimes[k]
            total += rt
            if k - start + 1 >= 3 and abs(seconds - total) <= _eff_tol(total, tolerance):
                return True
            if total > seconds + _eff_tol(total, tolerance):
                break

    # Rule C: play-all if 3+ other titles and title length matches sum of other titles
    other_titles = [t for i, t in enumerate(titles) if i != title_idx]
    if len(other_titles) >= 3:
        sum_others = sum(t.seconds for t in other_titles)
        if abs(seconds - sum_others) <= _eff_tol(sum_others, tolerance):
            return True
    elif len(other_titles) == 2 and abs(seconds - sum(t.seconds for t in other_titles)) < PLAY_ALL_PAIR_WINDOW_S:
        return True

    return False


def _one_cost(seconds: int, runtime: int | None, tolerance: int, ref_rt: int) -> float | None:
    """Cost for matching a single episode. Handles unknown runtimes."""
    rt = _known(runtime)
    if rt is None:
        # Unknown runtime: check plausibility against ref_rt
        if abs(seconds - ref_rt) <= _eff_tol(ref_rt, tolerance):
            return tolerance / 2
        return None
    delta = abs(seconds - rt)
    eff = _eff_tol(rt, tolerance)
    return float(delta) if delta <= eff else None


def _hole(episodes: Sequence[Episode], j: int) -> int:
    """Episode numbers missing between list entries j-1 and j of the same season."""
    if j == 0 or episodes[j - 1].season != episodes[j].season:
        return 0
    return max(0, episodes[j].number - episodes[j - 1].number - 1)


def _is_ambiguous(
    singles: Sequence[tuple[int, int]],
    doubles: frozenset[int],
    episodes: Sequence[Episode],
    tolerance: int,
    ref_rt: int,
) -> bool:
    """True when shifting every single-episode match (list position, title seconds)
    by -1 or +1 is also valid and its total delta is within AMBIGUITY_WINDOW_S of
    the chosen one. Unknown runtimes count as the reference-runtime delta."""
    if not singles:
        return False

    def delta(seconds: int, ep: Episode) -> int:
        return abs(seconds - (_known(ep.runtime_s) or ref_rt))

    chosen = sum(delta(sec, episodes[j]) for j, sec in singles)
    for shift in (-1, 1):
        total = 0
        for j, sec in singles:
            k = j + shift
            if (
                not 0 <= k < len(episodes)
                or k in doubles
                or episodes[k].season != episodes[j].season
                or _one_cost(sec, episodes[k].runtime_s, tolerance, ref_rt) is None
            ):
                break
            total += delta(sec, episodes[k])
        else:
            if abs(total - chosen) <= AMBIGUITY_WINDOW_S:
                return True
    return False


def _confidence(delta: int | None, eff_tol: int) -> float:
    """Confidence based on delta and effective tolerance."""
    if delta is None:
        return 0.5
    return round(min(1.0, max(0.0, 1 - delta / eff_tol)), 3)


def align(
    titles: Sequence[TitleIn],
    episodes: Sequence[Episode],
    *,
    tolerance: int = 300,
    anchor: int | None = None,
) -> MatchResult:
    # Rule E: raise ValueError for invalid tolerance
    if tolerance < 1:
        raise ValueError("tolerance must be >= 1")

    # Rule E: raise ValueError for duplicate refs
    refs = [t.ref for t in titles]
    if len(refs) != len(set(refs)):
        raise ValueError("title refs must be unique")

    # Rule B: compute ref_rt = median of known runtimes, or median of all title lengths
    known_runtimes_list: list[int] = [rt for e in episodes if (rt := _known(e.runtime_s)) is not None]
    if known_runtimes_list:
        ref_rt = int(statistics.median_low(known_runtimes_list))
    else:
        all_lengths = [t.seconds for t in titles]
        ref_rt = int(statistics.median_low(all_lengths)) if all_lengths else 0

    # Rule C: play-all detection (now with ref_rt and other-titles support)
    play_all = tuple(
        t.ref for i, t in enumerate(titles) if _is_play_all(t.seconds, episodes, tolerance, ref_rt, titles, i)
    )
    elig = [t for t in titles if t.ref not in play_all]
    m, n = len(elig), len(episodes)

    # Rule D: skip_title cost = tolerance + 2; skip_ep = tolerance + 1
    skip_title_cost = tolerance + 2
    skip_ep_cost = tolerance + 1

    dp = [[_INF] * (n + 1) for _ in range(m + 1)]
    back: list[list[tuple[object, ...] | None]] = [[None] * (n + 1) for _ in range(m + 1)]
    for j in range(n + 1):
        dp[0][j] = ANCHOR_WEIGHT * abs(j - anchor) if anchor is not None else FREE_START_WEIGHT * j
        back[0][j] = ("start",)

    def relax(i: int, j: int, cost: float, step: tuple[object, ...]) -> None:
        if cost < dp[i][j]:
            dp[i][j] = cost
            back[i][j] = step

    for i in range(m + 1):
        for j in range(n + 1):
            cur = dp[i][j]
            # A match here follows an earlier title (i > 0): pay for every
            # episode number the run would jump between list entries j-1 and j.
            hole_cost = (tolerance + 1) * _hole(episodes, j) if i > 0 and j < n else 0
            if i < m:
                relax(i + 1, j, cur + skip_title_cost, ("skip_title", i, j))
            if i > 0 and j < n:
                relax(i, j + 1, cur + skip_ep_cost, ("skip_ep", i, j))
            if i < m and j < n:
                one = _one_cost(elig[i].seconds, episodes[j].runtime_s, tolerance, ref_rt)
                if one is not None:
                    relax(i + 1, j + 1, cur + one + hole_cost, ("one", i, j))
            if (
                i < m
                and j + 1 < n
                and episodes[j].season == episodes[j + 1].season
                and episodes[j + 1].number == episodes[j].number + 1
            ):
                a, b = _known(episodes[j].runtime_s), _known(episodes[j + 1].runtime_s)
                if a is not None and b is not None:
                    delta = abs(elig[i].seconds - (a + b))
                    eff = _eff_tol(a + b, tolerance)
                    if delta <= eff:
                        relax(i + 1, j + 2, cur + delta + DOUBLE_PENALTY + hole_cost, ("two", i, j))

    best_j = min(range(n + 1), key=lambda j: (dp[m][j], j))
    matches: list[TitleMatch] = []
    skipped: list[str] = []
    singles: list[tuple[int, int]] = []
    doubles: set[int] = set()
    i, j = m, best_j
    while (step := back[i][j]) is not None:
        if step[0] == "start":
            break
        kind = cast(str, step[0])
        pi = cast(int, step[1]) if len(step) > 1 else 0
        pj = cast(int, step[2]) if len(step) > 2 else 0
        if kind == "skip_title":
            skipped.append(elig[pi].ref)
        elif kind == "one":
            title = elig[pi]
            ep = episodes[pj]
            singles.append((pj, title.seconds))
            rt = _known(ep.runtime_s)
            if rt is not None:
                delta_val: int | None = abs(title.seconds - rt)
                eff = _eff_tol(rt, tolerance)
            else:
                delta_val = None
                eff = _eff_tol(ref_rt, tolerance)
            matches.append(
                TitleMatch(title.ref, ep.season, ep.number, None, ep.name, delta_val, _confidence(delta_val, eff))
            )
        elif kind == "two":
            title = elig[pi]
            first, second = episodes[pj], episodes[pj + 1]
            doubles.update((pj, pj + 1))
            delta_val = abs(title.seconds - ((first.runtime_s or 0) + (second.runtime_s or 0)))
            eff = _eff_tol((first.runtime_s or 0) + (second.runtime_s or 0), tolerance)
            matches.append(
                TitleMatch(
                    title.ref,
                    first.season,
                    first.number,
                    second.number,
                    first.name,
                    delta_val,
                    _confidence(delta_val, eff),
                )
            )
        i, j = pi, pj
    matches.reverse()
    skipped.reverse()
    coverage = len(matches) / m if m else 0.0
    ambiguous = _is_ambiguous(singles, frozenset(doubles), episodes, tolerance, ref_rt)
    return MatchResult(tuple(matches), tuple(skipped), play_all, dp[m][best_j], coverage, ambiguous)
