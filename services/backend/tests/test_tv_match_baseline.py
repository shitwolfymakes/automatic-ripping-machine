"""Regression floor for the episode matcher over the TheDiscDB corpus: no
scenario may lose correct placements against the numbers measured after the
season-selection work, on the seven series the design doc's table covers."""

from __future__ import annotations

from tests.thediscdb_corpus import load_corpus
from tests.tv_match_baseline import run_all

BEFORE = {  # correct placements on the seven series, --min-seconds 60
    "nothing known, scan": 164,
    "season known": 242,
    "season + disc known": 308,
    "season + disc, lower discs held": 467,
    "season + disc, higher discs held": 253,
    "season + disc, all others held": 381,
}
SEVEN = [
    "all-creatures-great-and-small",
    "breaking-bad",
    "star-trek-deep-space-nine",
    "supernatural",
    "doctor-who-2005",
    "futurama",
    "sherlock",
]


def test_no_scenario_loses_correct_placements() -> None:
    corpus = {k: v for k, v in load_corpus().items() if k in SEVEN}
    tallies = run_all(corpus, 60)
    for name, floor in BEFORE.items():
        assert tallies[name].discs > 0, name
        assert tallies[name].correct >= floor, name


def test_deep_seasons_pick_the_right_season_as_often_as_shallow_ones() -> None:
    t = run_all(load_corpus(), 60)["nothing known, scan"]
    deep_rate = t.deep_wrong_season / max(1, t.deep_discs)
    shallow_rate = (t.wrong_season - t.deep_wrong_season) / max(1, t.discs - t.deep_discs)
    assert t.discs > 0 and t.deep_discs > 0
    assert deep_rate <= shallow_rate + 0.0


def test_a_hand_placed_track_is_never_duplicated() -> None:
    t = run_all(load_corpus(), 60)["season known, one track placed by hand"]
    assert t.discs > 0
    assert t.hand_placed > 0
    assert t.duplicates == 0
