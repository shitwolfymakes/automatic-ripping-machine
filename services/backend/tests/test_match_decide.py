from arm_common.enums import MediaType

from arm_backend.metadata.match.decide import DEFAULT_THRESHOLDS, Decision, decide, text_disagrees
from arm_backend.metadata.match.score import Candidate, ScoredCandidate, ScoreParts


def _scored(title: str, score: float, t: float = 1.0, year: int = 2000, rank: int = 0) -> ScoredCandidate:
    candidate = Candidate(title=title, kind=MediaType.MOVIE, year=year, provider_rank=rank)
    return ScoredCandidate(candidate, score, ScoreParts(0, 0, 0, 0, 0), t, ())


def test_accept_needs_score_margin_and_title() -> None:
    verdict = decide([_scored("A", 80), _scored("B", 60)])
    assert verdict.decision is Decision.ACCEPT
    assert verdict.winner is not None
    assert verdict.winner.candidate.title == "A"
    assert verdict.shortlist == ()
    assert verdict.runner_up_score == 60


def test_a_lone_candidate_has_runner_up_zero() -> None:
    verdict = decide([_scored("A", 65)])
    assert verdict.decision is Decision.ACCEPT
    assert verdict.runner_up_score == 0


def test_accept_boundaries() -> None:
    assert decide([_scored("A", 65), _scored("B", 55)]).decision is Decision.ACCEPT
    assert decide([_scored("A", 65), _scored("B", 55.1)]).decision is Decision.SHORTLIST
    assert decide([_scored("A", 64.9)]).decision is Decision.SHORTLIST


def test_title_floor_blocks_accept() -> None:
    verdict = decide([_scored("A", 90, t=0.69)])
    assert verdict.decision is Decision.SHORTLIST
    assert decide([_scored("A", 90, t=0.7)]).decision is Decision.ACCEPT


def test_shortlist_keeps_up_to_five_within_the_band() -> None:
    scored = [_scored(f"C{i}", s) for i, s in enumerate([70, 69, 68, 67, 66, 65, 64])]
    verdict = decide(scored)
    assert verdict.decision is Decision.SHORTLIST
    assert [c.candidate.title for c in verdict.shortlist] == ["C0", "C1", "C2", "C3", "C4"]


def test_shortlist_cut_is_floor_and_band() -> None:
    verdict = decide([_scored("A", 72), _scored("B", 70), _scored("C", 47), _scored("D", 46.9), _scored("E", 39.9)])
    assert [c.candidate.title for c in verdict.shortlist] == ["A", "B", "C"]
    verdict = decide([_scored("A", 50), _scored("B", 45), _scored("C", 39.9)])
    assert [c.candidate.title for c in verdict.shortlist] == ["A", "B"]


def test_no_match_below_the_floor() -> None:
    verdict = decide([_scored("A", 39.9), _scored("B", 10)])
    assert verdict.decision is Decision.NO_MATCH
    assert verdict.winner is None
    assert verdict.shortlist == ()
    assert decide([_scored("A", 40)]).decision is Decision.SHORTLIST


def test_nothing_scored_is_no_match() -> None:
    verdict = decide([])
    assert verdict.decision is Decision.NO_MATCH
    assert verdict.runner_up_score is None


def test_decide_ranks_its_input() -> None:
    verdict = decide([_scored("B", 60), _scored("A", 80)])
    assert verdict.winner is not None
    assert verdict.winner.candidate.title == "A"


def test_text_disagrees_below_twenty() -> None:
    assert text_disagrees(_scored("A", 19.9))
    assert not text_disagrees(_scored("A", 20))


def test_thresholds_are_the_approved_constants() -> None:
    t = DEFAULT_THRESHOLDS
    assert (t.accept, t.margin, t.floor, t.title_min, t.max_shortlist, t.band) == (65, 10, 40, 0.7, 5, 25)
