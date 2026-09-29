"""Cross-disc continuity (spec 6.3) and season ranking, incl. neu defects 1 and 2."""

from arm_backend.identity.episodes.continuity import SiblingDisc, rank_seasons, start_anchor
from arm_backend.identity.episodes.matcher import align
from arm_backend.identity.episodes.model import Episode, TitleIn


def season(n: int, runtime: int = 3000, number: int = 1) -> list[Episode]:
    return [Episode(season=number, number=i + 1, runtime_s=runtime) for i in range(n)]


def five_titles() -> list[TitleIn]:
    return [TitleIn(ref=str(i), seconds=3000) for i in range(5)]


def run(disc: int | None, total: int | None, siblings: list[SiblingDisc], n: int = 20) -> list[int]:
    remaining, anchor = start_anchor(season(n), disc_number=disc, disc_total=total, n_titles=5, siblings=siblings)
    return [m.episode for m in align(five_titles(), remaining, anchor=anchor).matches]


def test_kolchak_disc_positions_from_total() -> None:
    assert run(2, 4, []) == [6, 7, 8, 9, 10]
    assert run(4, 4, []) == [16, 17, 18, 19, 20]


def test_single_disc_total_starts_at_beginning() -> None:
    # disc_total == 1: the only disc always starts at the top of the season
    assert run(1, 1, []) == [1, 2, 3, 4, 5]


def test_mrs_bradley_last_disc() -> None:
    remaining, anchor = start_anchor(season(5), disc_number=2, disc_total=2, n_titles=2, siblings=[])
    got = align([TitleIn("0", 3000), TitleIn("1", 3000)], remaining, anchor=anchor)
    assert [m.episode for m in got.matches] == [4, 5]


def test_unknown_total_is_not_treated_as_last_disc() -> None:
    # neu defect 2
    assert run(1, None, []) == [1, 2, 3, 4, 5]
    assert run(2, None, []) == [6, 7, 8, 9, 10]


def test_exclusion_does_not_shift_the_window() -> None:
    # neu defect 1: disc 1 already holds E1-5
    assert run(2, 4, [SiblingDisc(1, frozenset(range(1, 6)))]) == [6, 7, 8, 9, 10]
    assert run(3, 4, [SiblingDisc(1, frozenset(range(1, 6))), SiblingDisc(2, frozenset(range(6, 11)))]) == [
        11,
        12,
        13,
        14,
        15,
    ]


def test_sibling_after_this_disc_only_excludes() -> None:
    # disc 3 ripped first (E11-15); disc 1 still starts at E1
    assert run(1, 4, [SiblingDisc(3, frozenset(range(11, 16)))]) == [1, 2, 3, 4, 5]


def test_unknown_disc_number_free_start_after_claims() -> None:
    assert run(None, None, [SiblingDisc(None, frozenset(range(1, 6)))]) == [6, 7, 8, 9, 10]


def test_anchor_past_end_is_clamped() -> None:
    remaining, anchor = start_anchor(
        season(5), disc_number=2, disc_total=None, n_titles=5, siblings=[SiblingDisc(1, frozenset(range(1, 6)))]
    )
    assert remaining == [] and anchor == 0


def test_lower_sibling_sentinel_is_len_remaining_not_minus_one() -> None:
    # fix round 1: the "nothing remaining reaches the target" sentinel is
    # len(remaining), not len(remaining) - 1 - regression with a NON-empty
    # remaining list (season(10) minus {8, 9, 10} leaves 7 episodes).
    remaining, anchor = start_anchor(
        season(10), disc_number=2, disc_total=None, n_titles=5, siblings=[SiblingDisc(1, frozenset({8, 9, 10}))]
    )
    assert len(remaining) == 7
    assert anchor == 7 == len(remaining)


def test_lower_sibling_sentinel_anchor_keeps_title_unmatched() -> None:
    # Same setup: a title too long for any remaining episode should be
    # skipped at the anchor-past-end position, not dragged backward onto E7.
    remaining, anchor = start_anchor(
        season(10), disc_number=2, disc_total=None, n_titles=5, siblings=[SiblingDisc(1, frozenset({8, 9, 10}))]
    )
    result = align([TitleIn("0", 3280)], remaining, anchor=anchor)
    assert result.matches == ()
    assert result.skipped == ("0",)


def test_proportional_sentinel_is_len_remaining_not_minus_one() -> None:
    # Same fix, proportional (non-lower-sibling) branch: a sibling with
    # unknown disc_number claims E5 only (so it doesn't count toward
    # "lower"), leaving 4 remaining episodes; disc 3 of an unknown-total set
    # targets a position past all of them.
    remaining, anchor = start_anchor(
        season(5), disc_number=3, disc_total=None, n_titles=5, siblings=[SiblingDisc(None, frozenset({5}))]
    )
    assert len(remaining) == 4
    assert anchor == 4 == len(remaining)


def test_empty_season_with_known_disc_number_is_free_start() -> None:
    assert start_anchor([], disc_number=2, disc_total=4, n_titles=5, siblings=[]) == ([], None)


def test_sibling_with_empty_episodes_is_ignored() -> None:
    with_empty_sibling = start_anchor(
        season(10), disc_number=2, disc_total=4, n_titles=5, siblings=[SiblingDisc(1, frozenset())]
    )
    without_sibling = start_anchor(season(10), disc_number=2, disc_total=4, n_titles=5, siblings=[])
    assert with_empty_sibling == without_sibling


def test_rank_seasons_prefers_coverage_then_cost() -> None:
    good = align(five_titles(), season(10, number=2))
    worse = align(five_titles(), season(10, runtime=3200, number=1))
    none = align(five_titles(), season(10, runtime=9000, number=3))
    ranked = rank_seasons({1: worse, 2: good, 3: none})
    assert [s for s, _ in ranked] == [2, 1, 3]
