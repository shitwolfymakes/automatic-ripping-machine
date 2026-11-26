"""Ordered alignment of disc titles to a season's episodes.

Both sequences stay monotone: disc order maps to episode order. A title can
match one episode, two consecutive episodes (a double-length title), or be
skipped (extras, trailers); an episode can be skipped between matches (it
lives on another disc or was not ripped). Leading and trailing episodes are
free to skip, so the disc may sit anywhere in the season; `anchor` pulls the
start toward the position cross-disc continuity predicts.

When shifting the single-episode matches one position either way fits about as
well, the result is flagged `ambiguous`: its positions came from the anchor or
list order, not from runtimes.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterator, Sequence
from enum import Enum
from typing import NamedTuple

from arm_backend.identity.episodes.model import Episode, MatchResult, TitleIn, TitleMatch

DOUBLE_PENALTY = 60
ANCHOR_WEIGHT = 30
FREE_START_WEIGHT = 1
# A title this close to the sum of exactly two other titles is a play-all.
PLAY_ALL_PAIR_WINDOW_S = 10
# A shifted mapping whose total delta is this close to the chosen one is as plausible.
AMBIGUITY_WINDOW_S = 60
# The operator's `episode_match_tolerance_seconds` setting is a ceiling, not the
# window itself: the effective tolerance always narrows to a tenth of the
# reference runtime, floored so short references (or runtime-less episodes)
# still get a usable window.
EFFECTIVE_TOL_FLOOR_S = 60
EFFECTIVE_TOL_FRACTION = 10
_INF = float("inf")


def _known(runtime: int | None) -> int | None:
    return runtime if runtime is not None and runtime > 0 else None


def effective_tolerance(reference: int, tolerance: int) -> int:
    """Effective tolerance: clamp to [EFFECTIVE_TOL_FLOOR_S, tolerance], narrowed
    to a tenth of the reference runtime."""
    return min(tolerance, max(EFFECTIVE_TOL_FLOOR_S, reference // EFFECTIVE_TOL_FRACTION))


def _matches_consecutive_sum(seconds: int, runtimes: Sequence[int], tolerance: int) -> bool:
    """True when the title matches the sum of 3+ consecutive episode runtimes."""
    for start in range(len(runtimes)):
        total = 0
        for k in range(start, len(runtimes)):
            rt = runtimes[k]
            total += rt
            if k - start + 1 >= 3 and abs(seconds - total) <= effective_tolerance(total, tolerance):
                return True
            if total > seconds + effective_tolerance(total, tolerance):
                break
    return False


def _matches_other_titles_sum(seconds: int, titles: Sequence[TitleIn], title_idx: int, tolerance: int) -> bool:
    """True when the title matches the sum of the other titles: within tolerance for 3+ others,
    within PLAY_ALL_PAIR_WINDOW_S for exactly 2."""
    # Rule C: play-all if 3+ other titles and title length matches sum of other titles
    other_titles = [t for i, t in enumerate(titles) if i != title_idx]
    if len(other_titles) >= 3:
        sum_others = sum(t.seconds for t in other_titles)
        if abs(seconds - sum_others) <= effective_tolerance(sum_others, tolerance):
            return True
    elif len(other_titles) == 2 and abs(seconds - sum(t.seconds for t in other_titles)) < PLAY_ALL_PAIR_WINDOW_S:
        return True
    return False


def _is_play_all(
    seconds: int, episodes: Sequence[Episode], tolerance: int, ref_rt: int, titles: Sequence[TitleIn], title_idx: int
) -> bool:
    """Check if a title is play-all: matches sum of 3+ consecutive episodes, or sum of the other titles
    (within tolerance for 3+ others; within PLAY_ALL_PAIR_WINDOW_S for exactly 2, where a genuine two-part
    title is otherwise just as likely)."""
    # Rule B: in play-all scan, treat unknown runtime as ref_rt
    runtimes = [_known(e.runtime_s) or ref_rt for e in episodes]
    return _matches_consecutive_sum(seconds, runtimes, tolerance) or _matches_other_titles_sum(
        seconds, titles, title_idx, tolerance
    )


def _one_cost(seconds: int, runtime: int | None, tolerance: int, ref_rt: int) -> float | None:
    """Cost for matching a single episode. Handles unknown runtimes."""
    rt = _known(runtime)
    if rt is None:
        # Unknown runtime: check plausibility against ref_rt
        if abs(seconds - ref_rt) <= effective_tolerance(ref_rt, tolerance):
            return tolerance / 2
        return None
    delta = abs(seconds - rt)
    eff = effective_tolerance(rt, tolerance)
    return float(delta) if delta <= eff else None


def _is_ambiguous(
    singles: Sequence[tuple[int, int]],
    doubles: frozenset[int],
    episodes: Sequence[Episode],
    tolerance: int,
    ref_rt: int,
) -> bool:
    """True when shifting every single-episode match (list position, title seconds)
    by -1 or +1 is also valid and its total delta is no worse than AMBIGUITY_WINDOW_S
    over the chosen one (one-sided: a shift that fits as well or better is just as
    ambiguous as one a little worse). Unknown runtimes count as the reference-runtime
    delta."""
    if not singles:
        return False

    def delta(seconds: int, ep: Episode) -> int:
        return abs(seconds - (_known(ep.runtime_s) or ref_rt))

    chosen_total = sum(delta(sec, episodes[j]) for j, sec in singles)
    for shift in (-1, 1):
        shifted_total = 0
        for j, sec in singles:
            k = j + shift
            if (
                not 0 <= k < len(episodes)
                or k in doubles
                or episodes[k].season != episodes[j].season
                or _one_cost(sec, episodes[k].runtime_s, tolerance, ref_rt) is None
            ):
                break
            shifted_total += delta(sec, episodes[k])
        else:
            if shifted_total <= chosen_total + AMBIGUITY_WINDOW_S:
                return True
    return False


def _confidence(delta: int | None, eff_tol: int) -> float:
    """Confidence based on delta and effective tolerance."""
    if delta is None:
        return 0.5
    return round(min(1.0, max(0.0, 1 - delta / eff_tol)), 3)


def _check_inputs(titles: Sequence[TitleIn], tolerance: int) -> None:
    """Rule E: raise ValueError for a tolerance below 1 or duplicate title refs."""
    # Rule E: raise ValueError for invalid tolerance
    if tolerance < 1:
        raise ValueError("tolerance must be >= 1")

    # Rule E: raise ValueError for duplicate refs
    refs = [t.ref for t in titles]
    if len(refs) != len(set(refs)):
        raise ValueError("title refs must be unique")


def _reference_runtime(titles: Sequence[TitleIn], episodes: Sequence[Episode]) -> int:
    """Rule B: the median of the known episode runtimes, else the median of all title lengths, else 0."""
    known_runtimes_list: list[int] = [rt for e in episodes if (rt := _known(e.runtime_s)) is not None]
    if known_runtimes_list:
        return int(statistics.median_low(known_runtimes_list))
    all_lengths = [t.seconds for t in titles]
    return int(statistics.median_low(all_lengths)) if all_lengths else 0


def _play_all_refs(
    titles: Sequence[TitleIn], episodes: Sequence[Episode], tolerance: int, ref_rt: int
) -> tuple[str, ...]:
    """Rule C: the refs of the titles that look like play-all titles, in title order."""
    return tuple(t.ref for i, t in enumerate(titles) if _is_play_all(t.seconds, episodes, tolerance, ref_rt, titles, i))


def _single_match(title: TitleIn, ep: Episode, tolerance: int, ref_rt: int) -> TitleMatch:
    """The match of a title to one episode; an unknown runtime has no delta and is judged against the
    reference runtime's tolerance."""
    rt = _known(ep.runtime_s)
    if rt is not None:
        delta_val: int | None = abs(title.seconds - rt)
        eff = effective_tolerance(rt, tolerance)
    else:
        delta_val = None
        eff = effective_tolerance(ref_rt, tolerance)
    return TitleMatch(title.ref, ep.season, ep.number, None, ep.name, delta_val, _confidence(delta_val, eff))


def _double_match(title: TitleIn, first: Episode, second: Episode, tolerance: int) -> TitleMatch:
    """The match of a title to two consecutive episodes."""
    delta_val = abs(title.seconds - ((first.runtime_s or 0) + (second.runtime_s or 0)))
    eff = effective_tolerance((first.runtime_s or 0) + (second.runtime_s or 0), tolerance)
    return TitleMatch(
        title.ref,
        first.season,
        first.number,
        second.number,
        first.name,
        delta_val,
        _confidence(delta_val, eff),
    )


class _Move(Enum):
    """The DP move that reached a table cell."""

    START = "start"
    SKIP_TITLE = "skip_title"
    SKIP_EP = "skip_ep"
    ONE = "one"
    TWO = "two"


class _Step(NamedTuple):
    """A back-pointer: the move that reached a cell and the cell (i, j) it moved from.
    A start step points at its own cell."""

    kind: _Move
    i: int
    j: int


class _AlignTable:
    """The alignment DP table: the cheapest cost and back-pointer for each
    (eligible title, episode) cell, filled by the skip and match moves."""

    def __init__(
        self, elig: Sequence[TitleIn], episodes: Sequence[Episode], tolerance: int, ref_rt: int, anchor: int | None
    ) -> None:
        self.elig = elig
        self.episodes = episodes
        self.tolerance = tolerance
        self.ref_rt = ref_rt
        self.m, self.n = len(elig), len(episodes)

        # Rule D: skip_title cost = tolerance + 2; skip_ep = tolerance + 1
        self.skip_title_cost = tolerance + 2
        self.skip_ep_cost = tolerance + 1

        self.dp = [[_INF] * (self.n + 1) for _ in range(self.m + 1)]
        self.back: list[list[_Step | None]] = [[None] * (self.n + 1) for _ in range(self.m + 1)]
        for j in range(self.n + 1):
            self.dp[0][j] = ANCHOR_WEIGHT * abs(j - anchor) if anchor is not None else FREE_START_WEIGHT * j
            self.back[0][j] = _Step(_Move.START, 0, j)

    def relax(self, i: int, j: int, cost: float, step: _Step) -> None:
        """Lower cell (i, j) to `cost`, reached by `step`, when that is cheaper."""
        if cost < self.dp[i][j]:
            self.dp[i][j] = cost
            self.back[i][j] = step

    def fill(self) -> None:
        """Relax every cell's moves, row by row."""
        for i in range(self.m + 1):
            for j in range(self.n + 1):
                cur = self.dp[i][j]
                if i < self.m:
                    self.relax(i + 1, j, cur + self.skip_title_cost, _Step(_Move.SKIP_TITLE, i, j))
                if i > 0 and j < self.n:
                    self.relax(i, j + 1, cur + self.skip_ep_cost, _Step(_Move.SKIP_EP, i, j))
                self._relax_one(i, j, cur)
                self._relax_two(i, j, cur)

    def _relax_one(self, i: int, j: int, cur: float) -> None:
        """The one-episode move: title i matches episode j alone when its runtime fits."""
        if i < self.m and j < self.n:
            one = _one_cost(self.elig[i].seconds, self.episodes[j].runtime_s, self.tolerance, self.ref_rt)
            if one is not None:
                self.relax(i + 1, j + 1, cur + one, _Step(_Move.ONE, i, j))

    def _relax_two(self, i: int, j: int, cur: float) -> None:
        """The two-episode move: title i matches consecutive episodes j and j + 1 of one season when
        their summed known runtimes fit, at DOUBLE_PENALTY extra."""
        if (
            i < self.m
            and j + 1 < self.n
            and self.episodes[j].season == self.episodes[j + 1].season
            and self.episodes[j + 1].number == self.episodes[j].number + 1
        ):
            a, b = _known(self.episodes[j].runtime_s), _known(self.episodes[j + 1].runtime_s)
            if a is not None and b is not None:
                delta = abs(self.elig[i].seconds - (a + b))
                eff = effective_tolerance(a + b, self.tolerance)
                if delta <= eff:
                    self.relax(i + 1, j + 2, cur + delta + DOUBLE_PENALTY, _Step(_Move.TWO, i, j))

    def path(self, j: int) -> Iterator[_Step]:
        """The steps of the cheapest path ending at cell (m, j), last step first."""
        i = self.m
        step = self.back[i][j]
        while step is not None and step.kind is not _Move.START:
            yield step
            i, j = step.i, step.j
            step = self.back[i][j]


def align(
    titles: Sequence[TitleIn],
    episodes: Sequence[Episode],
    *,
    tolerance: int = 300,
    anchor: int | None = None,
) -> MatchResult:
    _check_inputs(titles, tolerance)
    ref_rt = _reference_runtime(titles, episodes)
    play_all = _play_all_refs(titles, episodes, tolerance, ref_rt)
    elig = [t for t in titles if t.ref not in play_all]
    m, n = len(elig), len(episodes)

    table = _AlignTable(elig, episodes, tolerance, ref_rt, anchor)
    table.fill()
    dp = table.dp

    best_j = min(range(n + 1), key=lambda j: (dp[m][j], j))
    matches: list[TitleMatch] = []
    skipped: list[str] = []
    singles: list[tuple[int, int]] = []
    doubles: set[int] = set()
    for kind, pi, pj in table.path(best_j):
        if kind is _Move.SKIP_TITLE:
            skipped.append(elig[pi].ref)
        elif kind is _Move.ONE:
            singles.append((pj, elig[pi].seconds))
            matches.append(_single_match(elig[pi], episodes[pj], tolerance, ref_rt))
        elif kind is _Move.TWO:
            doubles.update((pj, pj + 1))
            matches.append(_double_match(elig[pi], episodes[pj], episodes[pj + 1], tolerance))
    matches.reverse()
    skipped.reverse()
    coverage = len(matches) / m if m else 0.0
    ambiguous = _is_ambiguous(singles, frozenset(doubles), episodes, tolerance, ref_rt)
    return MatchResult(tuple(matches), tuple(skipped), play_all, dp[m][best_j], coverage, ambiguous)
