from arm_common.enums import MediaType
from arm_common.schemas import JobMetadata

from arm_backend.metadata.match.decide import DEFAULT_THRESHOLDS, Decision
from arm_backend.metadata.match.explain import build_match, log_line
from arm_backend.metadata.match.retrieve import Budget
from arm_backend.metadata.match.evidence import DiscEvidence
from arm_backend.metadata.match.queries import build_queries
from arm_backend.metadata.match.score import Candidate, ScoredCandidate, rank_candidates
from tests._provider_fakes import br2049_evidence


def _ranked() -> tuple[DiscEvidence, list[ScoredCandidate]]:
    ev = br2049_evidence()
    return ev, rank_candidates(
        ev,
        [
            Candidate(
                "Blade Runner 2049", _movie(), 2017, None, 164, ("tmdb", "omdb"), 0, {"tmdb": "1", "imdb": "tt1"}
            ),
            Candidate("Blade Runner", _movie(), 1982, None, None, ("tmdb",), 0, {"tmdb": "2"}),
        ],
    )


def _movie() -> MediaType:
    return MediaType.MOVIE


def test_the_breakdown_records_evidence_queries_calls_and_rounded_parts() -> None:
    ev, ranked = _ranked()
    budget = Budget(list_calls=2, detail_calls=1, cached=0)
    match = build_match(
        decision=Decision.ACCEPT,
        ev=ev,
        queries=[(q, ["movie"]) for q in build_queries(ev)],
        budget=budget,
        ranked=ranked,
        shortlist=0,
        runner_up=ranked[1].score,
        thresholds=DEFAULT_THRESHOLDS,
    )
    assert match.decision == "accept" and match.exact is None
    assert [t.source for t in match.evidence.titles] == ["bd_title", "iso_name"]
    assert match.evidence.titles[0].core == "Blade Runner 2049"
    assert match.evidence.titles[0].optional == ["3d", "bluray", "tm"]
    assert match.evidence.numbers == ["2049"]
    assert [(y.year, y.sources) for y in match.evidence.years] == [(2017, ["iso_name"])]
    assert match.evidence.runtime_source == "structure" and match.evidence.runtime_min == [163.0]
    assert [(q.text, q.kinds) for q in match.queries] == [("Blade Runner 2049", ["movie"])]
    assert (match.calls.list, match.calls.detail, match.calls.cached) == (2, 1, 0)
    top = match.candidates[0]
    assert (top.title, top.provider, top.providers, top.ids) == (
        "Blade Runner 2049",
        "tmdb",
        ["tmdb", "omdb"],
        {"tmdb": "1", "imdb": "tt1"},
    )
    assert top.parts.title == 45.0 and top.parts.runtime == 20.0
    assert round(sum(top.parts.model_dump().values()), 1) == top.score
    assert (match.thresholds.accept, match.thresholds.margin, match.thresholds.floor) == (65, 10, 40)


def test_at_most_five_candidates_are_stored() -> None:
    ev, ranked = _ranked()
    many = ranked * 4
    match = build_match(
        decision=Decision.SHORTLIST,
        ev=ev,
        queries=[],
        budget=Budget(),
        ranked=many,
        shortlist=5,
        runner_up=1.0,
        thresholds=DEFAULT_THRESHOLDS,
    )
    assert len(match.candidates) == 5 and match.shortlist == 5


def test_the_section_round_trips_through_the_job_metadata_schema() -> None:
    ev, ranked = _ranked()
    match = build_match(
        decision=None,
        ev=ev,
        queries=[],
        budget=Budget(),
        ranked=ranked[:1],
        shortlist=0,
        runner_up=None,
        thresholds=DEFAULT_THRESHOLDS,
        exact="fingerprint",
        text_disagrees=True,
    )
    dumped = match.model_dump(mode="json", exclude_none=True)
    meta = JobMetadata.model_validate({"identify_match": dumped})
    assert meta.identify_match is not None
    assert (meta.identify_match.decision, meta.identify_match.exact) == ("exact", "fingerprint")
    assert meta.identify_match.candidates[0].flags[-1] == "text_disagrees"


def test_the_log_line_names_the_winner_score_runner_up_parts_and_calls() -> None:
    ev, ranked = _ranked()
    match = build_match(
        decision=Decision.ACCEPT,
        ev=ev,
        queries=[],
        budget=Budget(list_calls=2, detail_calls=1),
        ranked=ranked,
        shortlist=0,
        runner_up=24.7,
        thresholds=DEFAULT_THRESHOLDS,
    )
    line = log_line("job_1", match)
    assert line.startswith('identify match job_id=job_1 decision=accept winner="Blade Runner 2049 (2017)" score=')
    assert "runner_up=24.7 parts=t45.0 y13.5 r20.0 k7.0 a6.0 calls=2+1" in line


def test_the_log_line_for_a_miss_names_no_winner() -> None:
    ev, ranked = _ranked()
    match = build_match(
        decision=Decision.NO_MATCH,
        ev=ev,
        queries=[],
        budget=Budget(list_calls=3),
        ranked=ranked[1:],
        shortlist=0,
        runner_up=0.0,
        thresholds=DEFAULT_THRESHOLDS,
    )
    assert "decision=no_match winner=- " in log_line("job_1", match)
    assert log_line("job_2", match).endswith("calls=3+0")
