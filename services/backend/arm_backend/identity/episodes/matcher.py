"""Ordered alignment of disc titles to a season's episodes (spec 6.2).

Both sequences stay monotone: disc order maps to episode order. A title can
match one episode, two consecutive episodes (a double-length title), or be
skipped (extras, trailers); an episode can be skipped between matches (it
lives on another disc or was not ripped). Leading and trailing episodes are
free to skip, so the disc may sit anywhere in the season; `anchor` pulls the
start toward the position cross-disc continuity predicts.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import cast

from arm_backend.identity.episodes.model import Episode, MatchResult, TitleIn, TitleMatch

DOUBLE_PENALTY = 60
ANCHOR_WEIGHT = 30
FREE_START_WEIGHT = 1
_INF = float("inf")


def _known(runtime: int | None) -> int | None:
    return runtime if runtime is not None and runtime > 0 else None


def _is_play_all(seconds: int, episodes: Sequence[Episode], tolerance: int) -> bool:
    runtimes = [_known(e.runtime_s) for e in episodes]
    for start in range(len(runtimes)):
        total = 0
        for k in range(start, len(runtimes)):
            rt = runtimes[k]
            if rt is None:
                break
            total += rt
            if k - start + 1 >= 3 and abs(seconds - total) <= tolerance:
                return True
            if total > seconds + tolerance:
                break
    return False


def _one_cost(seconds: int, runtime: int | None, tolerance: int) -> float | None:
    rt = _known(runtime)
    if rt is None:
        return tolerance / 2
    delta = abs(seconds - rt)
    return float(delta) if delta <= tolerance else None


def _confidence(delta: int | None, tolerance: int) -> float:
    if delta is None:
        return 0.5
    return round(min(1.0, max(0.0, 1 - delta / tolerance)), 3)


def align(
    titles: Sequence[TitleIn],
    episodes: Sequence[Episode],
    *,
    tolerance: int = 300,
    anchor: int | None = None,
) -> MatchResult:
    play_all = tuple(t.ref for t in titles if _is_play_all(t.seconds, episodes, tolerance))
    elig = [t for t in titles if t.ref not in play_all]
    m, n = len(elig), len(episodes)
    skip_cost = tolerance + 1

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
            if cur == _INF:
                continue
            if i < m:
                relax(i + 1, j, cur + skip_cost, ("skip_title", i, j))
            if i > 0 and j < n:
                relax(i, j + 1, cur + skip_cost, ("skip_ep", i, j))
            if i < m and j < n:
                one = _one_cost(elig[i].seconds, episodes[j].runtime_s, tolerance)
                if one is not None:
                    relax(i + 1, j + 1, cur + one, ("one", i, j))
            if i < m and j + 1 < n and episodes[j].season == episodes[j + 1].season:
                a, b = _known(episodes[j].runtime_s), _known(episodes[j + 1].runtime_s)
                if a is not None and b is not None:
                    delta = abs(elig[i].seconds - (a + b))
                    if delta <= tolerance:
                        relax(i + 1, j + 2, cur + delta + DOUBLE_PENALTY, ("two", i, j))

    best_j = min(range(n + 1), key=lambda j: (dp[m][j], j))
    matches: list[TitleMatch] = []
    skipped: list[str] = []
    i, j = m, best_j
    while (step := back[i][j]) is not None and step[0] != "start":
        kind = cast(str, step[0])
        pi = cast(int, step[1]) if len(step) > 1 else 0
        pj = cast(int, step[2]) if len(step) > 2 else 0
        if kind == "skip_title":
            skipped.append(elig[pi].ref)
        elif kind == "one":
            title = elig[pi]
            ep = episodes[pj]
            rt = _known(ep.runtime_s)
            delta_val: int | None = abs(title.seconds - rt) if rt is not None else None
            matches.append(
                TitleMatch(title.ref, ep.season, ep.number, None, ep.name, delta_val, _confidence(delta_val, tolerance))
            )
        elif kind == "two":
            title = elig[pi]
            first, second = episodes[pj], episodes[pj + 1]
            delta_val = abs(title.seconds - ((first.runtime_s or 0) + (second.runtime_s or 0)))
            matches.append(
                TitleMatch(
                    title.ref,
                    first.season,
                    first.number,
                    second.number,
                    first.name,
                    delta_val,
                    _confidence(delta_val, tolerance),
                )
            )
        i, j = pi, pj
    matches.reverse()
    skipped.reverse()
    coverage = len(matches) / m if m else 0.0
    return MatchResult(tuple(matches), tuple(skipped), play_all, dp[m][best_j] if n or m else 0.0, coverage)
