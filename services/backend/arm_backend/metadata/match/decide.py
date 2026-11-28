"""Accept, shortlist or no match, from ranked candidate scores (D62).

    accept     S1 >= 65 and S1 - S2 >= 10 and T1 >= 0.7  (S2 = 0 when alone)
    shortlist  not accept and S1 >= 40: up to 5 candidates with S >= 40 and S >= S1 - 25
    no match   S1 < 40

`T1 >= 0.7` means runtime and year alone never pick a title. Pure; the constants are not settings.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from arm_backend.metadata.match.score import ScoredCandidate, ranking_key


class Decision(StrEnum):
    ACCEPT = "accept"
    SHORTLIST = "shortlist"
    NO_MATCH = "no_match"


@dataclass(frozen=True)
class Thresholds:
    accept: float = 65.0
    margin: float = 10.0
    floor: float = 40.0
    title_min: float = 0.7
    max_shortlist: int = 5
    band: float = 25.0
    # An exact hit whose text scores below this gets the `text_disagrees` note (D68).
    text_disagrees_below: float = 20.0


DEFAULT_THRESHOLDS = Thresholds()


@dataclass(frozen=True)
class Verdict:
    decision: Decision
    # The top candidate (accept and shortlist), else None.
    winner: ScoredCandidate | None
    # Up to `max_shortlist` candidates for the operator (shortlist only).
    shortlist: tuple[ScoredCandidate, ...]
    # The second candidate's score (0 when alone); None when nothing was scored.
    runner_up_score: float | None


def _shortlist(ranked: list[ScoredCandidate], t: Thresholds) -> tuple[ScoredCandidate, ...]:
    cut = max(t.floor, ranked[0].score - t.band)
    return tuple([s for s in ranked if s.score >= cut][: t.max_shortlist])


def decide(scored: Iterable[ScoredCandidate], thresholds: Thresholds = DEFAULT_THRESHOLDS) -> Verdict:
    ranked = sorted(scored, key=ranking_key)
    if not ranked:
        return Verdict(Decision.NO_MATCH, None, (), None)
    top = ranked[0]
    runner_up = ranked[1].score if len(ranked) > 1 else 0.0
    if top.score < thresholds.floor:
        return Verdict(Decision.NO_MATCH, None, (), runner_up)
    accepted = (
        top.score >= thresholds.accept
        and top.score - runner_up >= thresholds.margin
        and top.title_fit >= thresholds.title_min
    )
    if accepted:
        return Verdict(Decision.ACCEPT, top, (), runner_up)
    return Verdict(Decision.SHORTLIST, top, _shortlist(ranked, thresholds), runner_up)


def text_disagrees(scored: ScoredCandidate, thresholds: Thresholds = DEFAULT_THRESHOLDS) -> bool:
    """An exact hit (content hash, fingerprint) whose text, year and runtime score too low to agree with it."""
    return scored.score < thresholds.text_disagrees_below
