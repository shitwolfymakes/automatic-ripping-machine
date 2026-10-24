"""Regression floor for the episode matcher over the TheDiscDB corpus: no
scenario may lose correct placements against the numbers the design doc
recorded before the season-selection work."""

from __future__ import annotations

from tests.thediscdb_corpus import load_corpus
from tests.tv_match_baseline import run_all

BEFORE = {  # correct placements from the design doc's baseline table, --min-seconds 60
    "nothing known, scan": 134,
    "season known": 242,
    "season + disc known": 248,
    "season + disc, lower discs held": 467,
    "season + disc, higher discs held": 198,
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
        assert tallies[name].correct >= floor, name


def test_deep_seasons_pick_the_right_season_as_often_as_shallow_ones() -> None:
    t = run_all(load_corpus(), 60)["nothing known, scan"]
    deep_rate = t.deep_wrong_season / max(1, t.deep_discs)
    shallow_rate = (t.wrong_season - t.deep_wrong_season) / max(1, t.discs - t.deep_discs)
    assert deep_rate <= shallow_rate + 0.10


def test_a_hand_placed_track_is_never_duplicated() -> None:
    assert run_all(load_corpus(), 60)["season known, one track placed by hand"].duplicates == 0
