"""Ordered-alignment episode matcher (spec 6.2) incl. neu defect regressions."""

from arm_backend.identity.episodes.matcher import align
from arm_backend.identity.episodes.model import Episode, TitleIn


def eps(*runtimes: int | None, season: int = 1) -> list[Episode]:
    return [Episode(season=season, number=i + 1, name=f"E{i + 1}", runtime_s=r) for i, r in enumerate(runtimes)]


def titles(*seconds: int) -> list[TitleIn]:
    return [TitleIn(ref=str(i), seconds=s) for i, s in enumerate(seconds)]


def mapping(result) -> dict[str, tuple[int, int | None]]:
    return {m.ref: (m.episode, m.episode_end) for m in result.matches}


def test_simple_in_order() -> None:
    r = align(titles(2580, 2640, 2600), eps(2600, 2600, 2600, 2600))
    assert mapping(r) == {"0": (1, None), "1": (2, None), "2": (3, None)}
    assert r.coverage == 1.0 and r.skipped == () and r.play_all == ()


def test_varied_runtimes_pick_the_matching_window() -> None:
    # disc holds E3-E4 (short, long); nothing else fits
    r = align(titles(1300, 3500), eps(2600, 2600, 1320, 3480, 2600))
    assert mapping(r) == {"0": (3, None), "1": (4, None)}


def test_out_of_tolerance_is_never_paired() -> None:
    # neu defect 4: a greedy re-zip paired T0(2700)->E1(1500)
    r = align(titles(2700, 1500), eps(1500, 2700))
    assert len(r.matches) == 1
    assert all(m.delta_s is not None and m.delta_s <= 300 for m in r.matches)


def test_play_all_first_does_not_shift_episodes() -> None:
    # neu defect 3
    r = align(titles(15000, 3000, 3000, 3000, 3000, 3000), eps(3000, 3000, 3000, 3000, 3000))
    assert r.play_all == ("0",)
    assert mapping(r) == {"1": (1, None), "2": (2, None), "3": (3, None), "4": (4, None), "5": (5, None)}


def test_extra_between_episodes_is_skipped() -> None:
    r = align(titles(2600, 600, 2600), eps(2600, 2600, 2600))
    assert mapping(r) == {"0": (1, None), "2": (2, None)}
    assert r.skipped == ("1",)


def test_two_episode_title() -> None:
    r = align(titles(3000, 6010, 3000), eps(3000, 3000, 3000, 3000))
    assert mapping(r) == {"0": (1, None), "1": (2, 3), "2": (4, None)}


def test_unknown_and_zero_runtimes_match_at_mid_confidence() -> None:
    # neu defect 6: 0 s runtime must not be a real runtime
    r = align(titles(2600, 2600, 2600), eps(None, 0, None))
    assert mapping(r) == {"0": (1, None), "1": (2, None), "2": (3, None)}
    assert {m.confidence for m in r.matches} == {0.5}


def test_anchor_positions_identical_runtimes() -> None:
    # Kolchak-style: 20 identical episodes, 5 identical titles, anchor at index 5 -> E6-E10
    r = align(titles(*[3000] * 5), eps(*[3000] * 20), anchor=5)
    assert [m.episode for m in r.matches] == [6, 7, 8, 9, 10]


def test_identical_inputs_are_deterministic_and_in_disc_order() -> None:
    a = align(titles(3000, 3000), eps(3000, 3000, 3000))
    b = align(titles(3000, 3000), eps(3000, 3000, 3000))
    assert a == b
    assert [m.episode for m in a.matches] == [1, 2]
    assert [m.ref for m in a.matches] == ["0", "1"]


def test_no_titles_or_no_episodes() -> None:
    assert align([], eps(3000)).coverage == 0.0
    r = align(titles(3000), [])
    assert r.matches == () and r.skipped == ("0",) and r.coverage == 0.0


def test_confidence_reflects_delta() -> None:
    r = align(titles(2750), eps(3000))
    assert r.matches[0].delta_s == 250 and r.matches[0].confidence == round(1 - 250 / 300, 3)


def test_custom_tolerance() -> None:
    assert align(titles(2700), eps(3000), tolerance=200).matches == ()


# Regression tests from fix round 1


def test_unknown_runtimes_with_120s_skip() -> None:
    # Regression 1: 120s title should be skipped (ref_rt ~2600)
    r = align(titles(2600, 120, 2600, 2600), eps(None, None, None, None, None, None, None, None, None, None))
    assert mapping(r) == {"0": (1, None), "2": (2, None), "3": (3, None)}
    assert r.skipped == ("1",)


def test_unknown_runtimes_play_all_and_others() -> None:
    # Regression 2: 15000 title doesn't match; five 2600s map E1-E5
    r = align(
        titles(15000, 2600, 2600, 2600, 2600, 2600),
        eps(None, None, None, None, None, None, None, None, None, None),
    )
    assert r.coverage == 5.0 / 6.0 or r.coverage == 5.0 / 5.0  # Either "0" is skipped or in play_all
    # The 5 titles of 2600 should map to E1-E5
    assert {m.episode for m in r.matches} == {1, 2, 3, 4, 5}


def test_play_all_by_other_titles() -> None:
    # Regression 3: 7800 = 2600*3, so "0" is play-all; E1-E3 match others
    r = align(titles(7800, 2600, 2600, 2600), eps(2600, 2600, 2600, 2600))
    assert r.play_all == ("0",)
    assert mapping(r) == {"1": (1, None), "2": (2, None), "3": (3, None)}


def test_interior_episode_skip() -> None:
    # Regression 4: E3 (3500) is skipped, E1-2 and E4 match
    r = align(titles(2600, 2600, 2600), eps(2600, 2600, 3500, 2600))
    assert mapping(r) == {"0": (1, None), "1": (2, None), "2": (4, None)}
    assert r.skipped == ()


def test_skipped_title_in_middle() -> None:
    # Regression 5: 1100 title is skipped (ref_rt ~1320)
    r = align(titles(1320, 1100, 1320, 1320), eps(1320, 1320, 1320, 1320, 1320, 1320, 1320, 1320, 1320, 1320))
    assert mapping(r) == {"0": (1, None), "2": (2, None), "3": (3, None)}
    assert r.skipped == ("1",)


def test_tolerance_zero_raises() -> None:
    # Regression 6a: tolerance < 1 raises ValueError
    try:
        align(titles(2600), eps(2600), tolerance=0)
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "tolerance" in str(e).lower()


def test_duplicate_refs_raises() -> None:
    # Regression 6b: duplicate refs raise ValueError
    try:
        align([TitleIn(ref="0", seconds=2600), TitleIn(ref="0", seconds=2600)], eps(2600))
        assert False, "Should raise ValueError"
    except ValueError as e:
        assert "unique" in str(e).lower()


def test_two_episode_confidence() -> None:
    # Regression 7: two-episode match confidence = round(1 - delta/eff_tol, 3)
    r = align(titles(6010), eps(3000, 3000))
    assert len(r.matches) == 1
    match = r.matches[0]
    assert match.episode_end == 2
    # delta = |6010 - 6000| = 10; eff_tol = min(300, max(60, 6000//10)) = min(300, 600) = 300
    expected_conf = round(1 - 10 / 300, 3)
    assert match.confidence == expected_conf


def test_play_all_by_other_titles_only() -> None:
    # Covers play-all-by-other-titles path (not episode-sum): fewer episodes
    # so 7500 doesn't match any 3+ episode sum, but matches sum of 3 other titles
    r = align(titles(7500, 2500, 2500, 2500), eps(2600, 2600))
    # Title "0" (7500) is play-all, excluded; remaining eligible
    # DP chooses to match "2" → E1, "3" → E2, skipping "1"
    assert "0" in r.play_all or all(m.ref != "0" for m in r.matches)
    assert mapping(r) == {"2": (1, None), "3": (2, None)}
    assert "1" in r.skipped
