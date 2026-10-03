"""Disc structure as a movie-vs-TV signal: a disc of several episode-length
titles of similar length (and no feature) is a TV disc, whatever its label
says. Kolchak: The Night Stalker (an untouched BD-50 folder, label "Kolchak
The Night Stalker Disc 1") identified as a TMDb placeholder *movie* because
only a season number in the label made identify search TV first."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.identity.disc_shape import looks_episodic  # noqa: E402
from arm_common.schemas import ScanTitle  # noqa: E402


def _titles(*seconds: int) -> list[ScanTitle]:
    return [ScanTitle(index=i, duration_seconds=s) for i, s in enumerate(seconds)]


def test_kolchak_disc_1_is_episodic() -> None:
    # The real disc: five ~51 minute episodes and a 9 minute extra.
    assert looks_episodic(_titles(3093, 3033, 3092, 3070, 3078, 542)) is True


def test_a_movie_with_extras_is_not() -> None:
    assert looks_episodic(_titles(7260, 1320, 1150, 1290, 600)) is False


def test_a_tv_dvd_with_a_play_all_title_is_still_episodic() -> None:
    # Four 22-minute episodes plus "play all" (their sum) - common on TV DVDs.
    assert looks_episodic(_titles(1322, 1318, 1325, 1320, 5285)) is True


def test_two_episodes_are_not_enough() -> None:
    assert looks_episodic(_titles(2640, 2650)) is False


def test_episode_length_titles_of_very_different_lengths_are_not() -> None:
    # A documentary disc: unrelated featurettes.
    assert looks_episodic(_titles(1200, 2400, 3900)) is False


def test_titles_without_durations_are_not() -> None:
    assert looks_episodic([ScanTitle(index=0, duration_seconds=0)]) is False
    assert looks_episodic([]) is False
