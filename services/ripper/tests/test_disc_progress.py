"""Disc-wide progress across the per-title rips of a disc."""

import pytest

from arm_ripper.rip.disc_progress import DiscProgress, disc_progress


@pytest.mark.parametrize(
    ("done", "current", "fraction", "total", "expected"),
    [
        (0, 50, 0.0, 100, 0.0),
        (25, 50, 0.5, 100, 0.5),
        (50, 50, 1.0, 100, 1.0),
        (50, 50, 1.7, 100, 1.0),
        (10, 50, -1.0, 100, 0.1),
        (0, 0, 0.5, 0, 0.0),
        (120, 0, 0.0, 100, 1.0),
    ],
)
def test_disc_progress(done: int, current: int, fraction: float, total: int, expected: float) -> None:
    assert disc_progress(done, current, fraction, total) == pytest.approx(expected)


def test_progress_is_monotonic_across_three_titles() -> None:
    disc = DiscProgress({0: 10, 1: 30, 2: 60}, settled=())
    seen: list[float] = []
    for title in (0, 1, 2):
        for f in (0.0, 0.5, 1.0):
            seen.append(disc.fraction(title, f))
        disc.settle(title)
    assert seen == sorted(seen)
    assert seen[0] == 0.0
    assert seen[-1] == pytest.approx(1.0)
    # Title 1 at the half way point: title 0's 10 plus half of 30, over 100.
    assert seen[4] == pytest.approx(0.25)


def test_a_retry_from_zero_does_not_pull_the_figure_back() -> None:
    disc = DiscProgress({0: 50, 1: 50}, settled=())
    assert disc.fraction(0, 0.8) == pytest.approx(0.4)
    assert disc.fraction(0, 0.0) == pytest.approx(0.4)
    assert disc.fraction(0, 0.9) == pytest.approx(0.45)


def test_titles_settled_before_the_pass_count_as_done() -> None:
    disc = DiscProgress({0: 50, 1: 50}, settled=(0, 7))
    assert disc.fraction(1, 0.0) == pytest.approx(0.5)


def test_titles_weigh_the_same_when_any_size_is_unknown() -> None:
    disc = DiscProgress({0: 1000, 1: None, 2: 5}, settled=())
    assert disc.fraction(0, 1.0) == pytest.approx(1 / 3)
    disc.settle(0)
    assert disc.fraction(1, 0.5) == pytest.approx(0.5)
