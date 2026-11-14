"""The hold policy: why a season's fit is stored as a suggestion instead of applied on its own."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from arm_backend.identity.episodes.model import MatchResult

# Suggestion thresholds.
MIN_COVERAGE = 0.5
MIN_MEAN_CONFIDENCE = 0.4
NEAR_TIE_COST_RATIO = 0.1
# A scanned season wins thinly when the runner-up's mean cost is within
# max(THIN_WIN_RATIO * runner-up, THIN_WIN_MIN_S) seconds of the best.
THIN_WIN_RATIO = 0.1
THIN_WIN_MIN_S = 30


@dataclass(frozen=True)
class SeasonFit:
    result: MatchResult
    nominal: bool
    sibling_conflict: bool


def _mean_cost(result: MatchResult) -> float:
    return result.cost / max(1, len(result.matches))


def _near_tie(first: MatchResult, second: MatchResult) -> bool:
    if first.coverage != second.coverage or len(first.matches) != len(second.matches):
        return False
    a, b = _mean_cost(first), _mean_cost(second)
    return abs(a - b) <= NEAR_TIE_COST_RATIO * max(a, b)


def _thin_win(best: MatchResult, runner_up: MatchResult) -> bool:
    gap = _mean_cost(runner_up) - _mean_cost(best)
    return gap < max(THIN_WIN_RATIO * _mean_cost(runner_up), THIN_WIN_MIN_S)


def hold_reasons(
    fit: SeasonFit, ranked: Sequence[tuple[int, MatchResult]], *, scanned: bool, auto_apply: bool
) -> list[str]:
    """Why `fit` (the best-ranked season's) is held as a suggestion, in a
    fixed order; empty when it applies on its own. `near_tie` and `thin_win`
    compare against the runner-up in `ranked`; `thin_win` only for a scanned
    season."""
    result = fit.result
    runner_up = ranked[1][1] if len(ranked) > 1 else None
    mean_conf = sum(m.confidence for m in result.matches) / max(1, len(result.matches))
    checks = (
        ("auto_apply_off", not auto_apply),
        ("ambiguous", result.ambiguous),
        ("low_coverage", result.coverage < MIN_COVERAGE),
        ("low_confidence", mean_conf < MIN_MEAN_CONFIDENCE),
        ("near_tie", runner_up is not None and _near_tie(result, runner_up)),
        ("thin_win", scanned and runner_up is not None and _thin_win(result, runner_up)),
        ("nominal_runtimes", fit.nominal),
        ("sibling_conflict", fit.sibling_conflict),
    )
    return [code for code, held in checks if held]
