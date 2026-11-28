import json
import random
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from arm_common.enums import MediaType
from arm_common.schemas import ScanTitle

from arm_backend.metadata.match.decide import Decision, decide
from arm_backend.metadata.match.evidence import DiscEvidence, YearEvidence, build_evidence
from arm_backend.metadata.match.score import (
    Candidate,
    agreement_score,
    kind_score,
    number_factor,
    rank_candidates,
    runtime_factor,
    score_candidate,
    title_score,
    year_factor,
    year_score,
)
from arm_backend.metadata.match.tokens import candidate_tokens, parse_title

FIXTURES = Path(__file__).parent / "fixtures" / "identify_match"
NOW = datetime(2026, 11, 27, tzinfo=UTC)
CASES = sorted(FIXTURES.glob("*.json"))


def _evidence(spec: dict[str, Any]) -> DiscEvidence:
    titles = [
        ScanTitle(
            index=i,
            duration_seconds=round(t["minutes"] * 60),
            segment_map=t.get("clips"),
            source_file=f"{i:05d}.mpls" if spec["structured"] else None,
        )
        for i, t in enumerate(spec["titles"])
    ]
    return build_evidence(
        bd_title=spec["bd_title"],
        iso_name=spec["iso_name"],
        label=spec["label"],
        titles=titles,
        structured=spec["structured"],
        set_number=None,
        num_sets=None,
        now=datetime.fromisoformat(spec["now"]).replace(tzinfo=UTC) if "now" in spec else NOW,
    )


def _candidate(spec: dict[str, Any]) -> Candidate:
    return Candidate(
        title=spec["title"],
        original_title=spec["original_title"],
        year=spec["year"],
        kind=MediaType(spec["kind"]),
        runtime_minutes=spec["runtime_minutes"],
        providers=tuple(spec["providers"]),
        provider_rank=spec["provider_rank"],
    )


def _label(candidate: Candidate) -> str:
    return f"{candidate.title} ({candidate.year})"


@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
def test_fixture_table(path: Path) -> None:
    case = json.loads(path.read_text())
    ev = _evidence(case["evidence"])
    ranked = rank_candidates(ev, [_candidate(c) for c in case["candidates"]])
    verdict = decide(ranked)
    expected = case["expected"]
    assert verdict.decision is Decision(expected["decision"])
    assert ranked[0].candidate.title + f" ({ranked[0].candidate.year})" == expected["winner"]
    scores = {_label(s.candidate): s.score for s in ranked}
    assert set(scores) == set(expected["scores"])
    for name, value in expected["scores"].items():
        assert scores[name] == pytest.approx(value, abs=0.1), name


@pytest.mark.parametrize("path", CASES, ids=[p.stem for p in CASES])
def test_ranking_ignores_input_order(path: Path) -> None:
    case = json.loads(path.read_text())
    ev = _evidence(case["evidence"])
    candidates = [_candidate(c) for c in case["candidates"]]
    baseline = [_label(s.candidate) for s in rank_candidates(ev, candidates)]
    rng = random.Random(7)
    for _ in range(5):
        shuffled = candidates[:]
        rng.shuffle(shuffled)
        assert [_label(s.candidate) for s in rank_candidates(ev, shuffled)] == baseline


def test_blade_runner_2099_scores_near_zero_and_never_wins() -> None:
    case = json.loads((FIXTURES / "blade_runner_2049_3d.json").read_text())
    ev = _evidence(case["evidence"])
    by_label = {_label(s.candidate): s for s in rank_candidates(ev, [_candidate(c) for c in case["candidates"]])}
    tv = by_label["Blade Runner 2099 (2026)"]
    assert 0 <= tv.score < 5
    assert tv.flags == ("numbers_differ",)
    assert by_label["Blade Runner 2049 (2017)"].parts.runtime == 20.0
    assert by_label["Blade Runner 2049 (2017)"].flags == ()


def test_blade_runner_2049_alone_is_accepted_with_its_parts() -> None:
    case = json.loads((FIXTURES / "blade_runner_2049_3d.json").read_text())
    ev = _evidence(case["evidence"])
    top = rank_candidates(ev, [_candidate(case["candidates"][0])])[0]
    parts = top.parts
    assert (parts.title, parts.year, parts.runtime, parts.kind, parts.agreement) == pytest.approx(
        (45.0, 13.5, 20.0, 7.0, 6.0)
    )
    assert top.score == pytest.approx(91.5)
    assert top.title_fit == 1.0


# --- title ------------------------------------------------------------------------------------------------------


def _fit(disc: str, candidate: str, *, truncated: bool = False) -> tuple[float, str | None]:
    parsed = parse_title(disc, now_year=2026, truncated=truncated)
    return title_score(parsed, candidate_tokens(candidate))


@pytest.mark.parametrize(
    ("disc", "candidate", "expected"),
    [
        ("Blade Runner 2049", "Blade Runner 2049", 1.0),
        ("THE_MATRIX_NTSC", "The Matrix", 1.0),
        ("THE_MATRIX_NTSC", "The Matrix Reloaded", 0.75),
        ("Indiana Jones and the Last Crusade", "Indiana Jones and the Temple of Doom", 0.1875),
        ("Blade Runner 2049", "Blade Runner", 0.2667),
        ("ROCKY_2", "Rocky II", 1.0),
        ("Uncut Gems", "Uncut Gems", 1.0),
        ("Uncut Gems", "Gems", 1.0),
        ("Fast & Furious", "Fast and Furious", 1.0),
        ("Amélie", "Amélie", 1.0),
        ("君の名は", "君の名は", 1.0),
        ("君の名は", "Your Name", 0.0),
        ("X", "", 0.0),
    ],
)
def test_title_score(disc: str, candidate: str, expected: float) -> None:
    assert _fit(disc, candidate)[0] == pytest.approx(expected, abs=1e-3)


def test_truncated_label_matches_the_last_token_by_prefix() -> None:
    label = "INDIANA_JONES_AND_THE_LAST_CRUSAD"
    assert _fit(label, "Indiana Jones and the Last Crusade", truncated=True)[0] == 1.0
    assert _fit(label, "Indiana Jones and the Last Crusade")[0] < 1.0
    assert _fit("ABC_DEFGHIJ", "Abc Def", truncated=True)[0] < 1.0
    assert _fit("ABC_DEFGHI_X", "Abc Defghij", truncated=True)[0] < 1.0


def test_prefix_needs_four_characters() -> None:
    assert _fit("MOVIE_STAR", "Movie Starlight", truncated=True)[0] == 1.0
    assert _fit("MOVIE_STA", "Movie Star", truncated=True)[0] < 1.0


# --- numbers -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("disc", "candidate", "factor", "flag"),
    [
        ("Blade Runner 2049", "Blade Runner 2099", 0.3, "numbers_differ"),
        ("Apollo 13 2", "Apollo 13 3", 0.6, "numbers_partial"),
        ("Apollo 13", "Apollo", 0.6, "disc_number_missing"),
        ("Alien", "Alien 3", 0.7, "candidate_sequel_number"),
        ("Alien", "Alien", 1.0, None),
        ("Apollo 13", "Apollo 13", 1.0, None),
        ("Rocky 4", "Rocky IV", 1.0, None),
        ("ALIEN_1979", "Alien 3", 0.7, "candidate_sequel_number"),
        ("WONDER_WOMAN_1984", "Wonder Woman 1984", 1.0, None),
        ("WONDER_WOMAN_1984", "Wonder Woman", 1.0, None),
    ],
)
def test_number_factor(disc: str, candidate: str, factor: float, flag: str | None) -> None:
    parsed = parse_title(disc, now_year=2026)
    assert number_factor(parsed, candidate_tokens(candidate)) == (factor, flag)


# --- year --------------------------------------------------------------------------------------------------------


def _year(year: int, r: float, *, bare: bool = False) -> YearEvidence:
    return YearEvidence(year, ("iso_name",), r, bare)


@pytest.mark.parametrize(("distance", "factor"), [(0, 1.0), (1, 0.5), (2, 0.0), (3, -1.0), (30, -1.0)])
def test_year_factor_movie(distance: int, factor: float) -> None:
    assert year_factor(distance, tv=False) == factor


@pytest.mark.parametrize(("distance", "factor"), [(0, 1.0), (1, 0.5), (2, 0.0), (3, 0.0), (30, 0.0)])
def test_year_factor_tv_is_never_negative(distance: int, factor: float) -> None:
    assert year_factor(distance, tv=True) == factor


def test_year_score_uses_the_strongest_year_and_its_reliability() -> None:
    years = (_year(2017, 0.9), _year(1999, 0.3))
    no_tokens: frozenset[str] = frozenset()
    assert year_score(years, 2017, no_tokens, tv=False) == pytest.approx(0.9)
    assert year_score(years, 2018, no_tokens, tv=False) == pytest.approx(0.45)
    assert year_score(years, 2000, no_tokens, tv=False) == pytest.approx(-0.9)
    assert year_score(years, 2000, no_tokens, tv=True) == 0.0
    assert year_score(years, None, no_tokens, tv=False) == 0.0
    assert year_score((), 2000, no_tokens, tv=False) == 0.0


def test_a_bare_year_the_candidate_title_contains_is_consumed() -> None:
    years = (_year(1984, 0.3, bare=True),)
    assert year_score(years, 2020, frozenset({"wonder", "woman", "1984"}), tv=False) == 0.0
    assert year_score(years, 2017, frozenset({"wonder", "woman"}), tv=False) == pytest.approx(-0.3)
    parenthesised = (_year(1984, 0.9),)
    assert year_score(parenthesised, 2020, frozenset({"1984"}), tv=False) == pytest.approx(-0.9)


def test_consumed_year_falls_back_to_the_next_candidate() -> None:
    years = (_year(1984, 0.5, bare=True), _year(2020, 0.3))
    assert year_score(years, 2020, frozenset({"1984"}), tv=False) == pytest.approx(0.3)


# --- runtime -----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("disc", "candidate", "factor"),
    [
        (100.0, 100.0, 1.0),
        (103.0, 100.0, 1.0),  # exactly 3 minutes
        (97.0, 100.0, 1.0),
        (104.0, 100.0, 1.0 - (0.04 - 0.03) / 0.07),
        (110.0, 100.0, 0.0),  # 10 %
        (200.0, 150.0, -1.0),
        (111.0, 100.0, -0.5 * (0.11 - 0.10) / 0.15),
        (125.0, 100.0, -0.5),  # 25 %
        (126.0, 100.0, -1.0),
        (206.0, 200.0, 1.0),  # 3 % of 200 is 6 minutes
        (207.0, 200.0, 1.0 - (0.035 - 0.03) / 0.07),
    ],
)
def test_runtime_factor_boundaries(disc: float, candidate: float, factor: float) -> None:
    assert runtime_factor((disc,), candidate, capped=False)[0] == pytest.approx(factor, abs=1e-3)


def test_runtime_factor_edition_cap() -> None:
    assert runtime_factor((126.0,), 100.0, capped=True) == (-0.5, True)
    assert runtime_factor((126.0,), 100.0, capped=False) == (-1.0, False)
    assert runtime_factor((100.0,), 100.0, capped=True) == (1.0, False)
    assert runtime_factor((111.0,), 100.0, capped=True)[1] is False


def test_runtime_factor_takes_the_nearest_disc_version() -> None:
    assert runtime_factor((117.0, 163.0), 164.0, capped=True)[0] == 1.0
    assert runtime_factor((117.0, 163.0), 118.0, capped=True)[0] == 1.0


def test_runtime_factor_short_candidates_do_not_divide_by_zero() -> None:
    assert runtime_factor((60.0,), 0.0, capped=False) == (0.0, False)
    assert runtime_factor((60.0,), 15.0, capped=False) == (-1.0, False)
    assert runtime_factor((20.0,), 18.0, capped=False)[0] == 1.0


def _movie(title: str = "Movie", runtime: float | None = None, year: int | None = None) -> Candidate:
    return Candidate(title=title, kind=MediaType.MOVIE, year=year, runtime_minutes=runtime, providers=("tmdb",))


def _tv(runtime: float | None) -> Candidate:
    return Candidate(title="Movie", kind=MediaType.TV, runtime_minutes=runtime, providers=("tmdb",))


def _disc(titles: list[ScanTitle], *, structured: bool = False, label: str = "MOVIE") -> DiscEvidence:
    return build_evidence(
        bd_title=None,
        iso_name=None,
        label=label,
        titles=titles,
        structured=structured,
        set_number=None,
        num_sets=None,
        now=NOW,
    )


def _feature(minutes: float) -> ScanTitle:
    return ScanTitle(index=0, duration_seconds=round(minutes * 60))


def test_unknown_runtime_scores_zero_either_side() -> None:
    assert score_candidate(_disc([_feature(120)]), _movie(runtime=None)).parts.runtime == 0.0
    assert score_candidate(_disc([]), _movie(runtime=120)).parts.runtime == 0.0


def test_dvd_runtime_is_weighted_by_its_reliability() -> None:
    assert score_candidate(_disc([_feature(120)]), _movie(runtime=120)).parts.runtime == pytest.approx(14.0)


def test_far_runtime_flags() -> None:
    far = score_candidate(_disc([_feature(120)]), _movie(runtime=60))
    assert far.parts.runtime == pytest.approx(-14.0)
    assert "runtime_far" in far.flags
    extended = build_evidence(
        bd_title=None,
        iso_name=None,
        label="ALIEN_DIRECTORS_CUT",
        titles=[_feature(120)],
        structured=False,
        set_number=None,
        num_sets=None,
        now=NOW,
    )
    capped = score_candidate(extended, _movie(runtime=60))
    assert capped.parts.runtime == pytest.approx(-7.0)
    assert "edition_tolerance" in capped.flags


def test_tv_runtime_rule_on_an_episodic_disc() -> None:
    episodes = [ScanTitle(index=i, duration_seconds=51 * 60) for i in range(5)]
    ev = _disc(episodes)
    assert ev.runtime is not None and ev.runtime.episode_minutes == 51.0
    assert score_candidate(ev, _tv(60)).parts.runtime == pytest.approx(10.0)  # 39 <= 51 <= 63
    assert score_candidate(ev, _tv(55)).parts.runtime == pytest.approx(10.0)  # 35.75 <= 51 <= 57.75
    assert score_candidate(ev, _tv(48)).parts.runtime == 0.0  # 51 is above 1.05 * 48
    assert score_candidate(ev, _tv(30)).parts.runtime == 0.0
    assert score_candidate(ev, _tv(120)).parts.runtime == 0.0
    assert score_candidate(ev, _tv(None)).parts.runtime == 0.0
    assert score_candidate(ev, _movie(runtime=51)).parts.runtime == 0.0


def test_tv_candidate_on_a_feature_disc_has_no_runtime_signal() -> None:
    assert score_candidate(_disc([_feature(120)]), _tv(60)).parts.runtime == 0.0


# --- kind and agreement ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("p_tv", "kind", "expected"),
    [(0.15, MediaType.MOVIE, 0.7), (0.15, MediaType.TV, -0.7), (0.9, MediaType.TV, 0.8), (0.9, MediaType.MOVIE, -0.8)],
)
def test_kind_score(p_tv: float, kind: MediaType, expected: float) -> None:
    assert kind_score(p_tv, kind) == pytest.approx(expected)


@pytest.mark.parametrize(("providers", "expected"), [(0, 0.0), (1, 0.0), (2, 0.6), (3, 1.0), (4, 1.0)])
def test_agreement_score(providers: int, expected: float) -> None:
    assert agreement_score(providers) == expected


def test_duplicate_provider_names_count_once() -> None:
    candidate = Candidate(title="Movie", kind=MediaType.MOVIE, providers=("tmdb", "tmdb"))
    assert score_candidate(_disc([]), candidate).parts.agreement == 0.0


# --- ranking -----------------------------------------------------------------------------------------------------


def test_ties_break_on_title_fit_then_provider_rank_then_title_then_year() -> None:
    ev = _disc([_feature(120)], label="MOVIE")
    same = [
        Candidate(title="Movie", kind=MediaType.MOVIE, year=2005, provider_rank=1, providers=("tmdb",)),
        Candidate(title="Movie", kind=MediaType.MOVIE, year=2001, provider_rank=1, providers=("tmdb",)),
        Candidate(title="Movie", kind=MediaType.MOVIE, year=2009, provider_rank=0, providers=("omdb",)),
    ]
    ranked = rank_candidates(ev, same)
    assert [(c.candidate.provider_rank, c.candidate.year) for c in ranked] == [(0, 2009), (1, 2001), (1, 2005)]


def test_original_title_can_match() -> None:
    ev = _disc([_feature(120)], label="AMELIE")
    candidate = Candidate(title="Amelie of Montmartre", original_title="Amelie", kind=MediaType.MOVIE)
    assert score_candidate(ev, candidate).title_fit == 1.0


def test_the_best_title_source_decides() -> None:
    ev = build_evidence(
        bd_title="Blade Runner 2049",
        iso_name=None,
        label="BR_2049",
        titles=[],
        structured=False,
        set_number=None,
        num_sets=None,
        now=NOW,
    )
    assert score_candidate(ev, _movie("Blade Runner 2049")).title_fit == 1.0


def test_no_title_evidence_scores_no_title() -> None:
    ev = _disc([_feature(120)], label="___")
    assert score_candidate(ev, _movie("Anything")).title_fit == 0.0


def test_year_mismatch_flag() -> None:
    ev = build_evidence(
        bd_title=None,
        iso_name="Movie (2017)",
        label=None,
        titles=[],
        structured=False,
        set_number=None,
        num_sets=None,
        now=NOW,
    )
    assert "year_mismatch" in score_candidate(ev, _movie("Movie", year=1982)).flags
    assert "year_mismatch" not in score_candidate(ev, _movie("Movie", year=2017)).flags
