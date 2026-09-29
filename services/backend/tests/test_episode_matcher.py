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


# Final review fix wave


def test_two_episode_match_never_spans_a_numbering_hole() -> None:
    # Important 1: siblings claimed E5-E6; the 5280 s title must not become "E04-E07"
    remaining = [Episode(season=1, number=n, name=f"E{n}", runtime_s=2640) for n in range(1, 11) if n not in (5, 6)]
    r = align(titles(2600, 2610, 2620, 5280), remaining)
    assert all(not (m.episode == 4 and m.episode_end == 7) for m in r.matches)
    assert all(m.episode_end is None or m.episode_end == m.episode + 1 for m in r.matches)


def test_two_episode_match_skips_provider_gap() -> None:
    # Important 1: a provider list missing E3 must not yield "E02-E04"
    listed = [Episode(season=1, number=n, name=f"E{n}", runtime_s=2640) for n in (1, 2, 4, 5)]
    r = align(titles(2640, 5280), listed)
    assert (2, 4) not in mapping(r).values()


def test_run_crosses_a_claimed_hole_on_runtime_evidence() -> None:
    # A sibling claimed E12-E21, so the remaining list is E7-E11, E22 (a
    # ten-episode hole). A title whose runtime fits E22 crosses the hole
    # instead of being skipped: a disc can genuinely span a numbering gap.
    remaining = [Episode(season=1, number=n, name=f"E{n}", runtime_s=2600) for n in (7, 8, 9, 10, 11, 22)]
    r = align(titles(*[2600] * 6), remaining, anchor=0)
    assert [m.episode for m in r.matches] == [7, 8, 9, 10, 11, 22]
    assert r.skipped == ()


# Numbering-hole penalty removal (a provider gap is missing data, not a hole to
# pay for): the season list genuinely lacks a number, and the disc's titles
# still carry runtime evidence for the episodes either side of it.


def test_maps_across_a_single_number_gap_on_runtime_evidence() -> None:
    # Provider list has no E4; the disc's 6 titles still land on their
    # runtime-matching episode either side of the gap.
    all_numbers = [1, 2, 3, 5, 6, 7, 8, 9, 10]
    ep_rt = {1: 3090, 2: 3070, 3: 2800, 5: 3080, 6: 2780, 7: 3010, 8: 2900, 9: 3050, 10: 2890}
    episodes = [Episode(season=1, number=n, name=f"E{n}", runtime_s=ep_rt[n]) for n in all_numbers]
    r = align(titles(3050, 2815, 3080, 2780, 3030, 2905), episodes)
    assert [m.episode for m in r.matches] == [2, 3, 5, 6, 7, 8]
    assert r.skipped == ()


def test_maps_across_a_two_number_gap_on_runtime_evidence() -> None:
    # Provider list has no E4 or E5; the disc's 6 titles still land on their
    # runtime-matching episode either side of the two-number gap.
    all_numbers = [1, 2, 3, 6, 7, 8, 9, 10]
    ep_rt = {1: 2500, 2: 2410, 3: 2530, 6: 2650, 7: 2470, 8: 2590, 9: 2710, 10: 2500}
    episodes = [Episode(season=1, number=n, name=f"E{n}", runtime_s=ep_rt[n]) for n in all_numbers]
    r = align(titles(2410, 2530, 2660, 2470, 2590, 2710), episodes)
    assert [m.episode for m in r.matches] == [2, 3, 6, 7, 8, 9]
    assert r.skipped == ()


def test_leading_extra_before_a_gap_does_not_drop_the_first_episode() -> None:
    # A 420 s extra is skipped; the four episodes after it still map
    # correctly across the provider's missing E4, including the first one.
    all_numbers = [1, 2, 3, 5, 6, 7, 8, 9]
    ep_rt = {1: 1940, 2: 2170, 3: 1950, 5: 2090, 6: 2200, 7: 1930, 8: 2160, 9: 2010}
    episodes = [Episode(season=1, number=n, name=f"E{n}", runtime_s=ep_rt[n]) for n in all_numbers]
    r = align(titles(420, 2060, 2190, 1920, 2130), episodes)
    assert mapping(r) == {"1": (5, None), "2": (6, None), "3": (7, None), "4": (8, None)}
    assert r.skipped == ("0",)


def test_identical_runtimes_with_anchor_are_ambiguous() -> None:
    # Important 4b: an anchor alone decided E6-E10; E5-E9 or E7-E11 fit equally well
    r = align(titles(*[3000] * 5), eps(*[3000] * 20), anchor=5)
    assert [m.episode for m in r.matches] == [6, 7, 8, 9, 10]
    assert r.ambiguous is True


def test_distinctive_runtimes_are_not_ambiguous() -> None:
    r = align(titles(1300, 3500), eps(2600, 2600, 1320, 3480, 2600))
    assert mapping(r) == {"0": (3, None), "1": (4, None)}
    assert r.ambiguous is False


def test_nominal_identical_provider_runtimes_are_ambiguous() -> None:
    # Provider lists every episode at the nominal 2600 s: E2-E4 fits as well as E1-E3
    r = align(titles(2580, 2640, 2600), eps(2600, 2600, 2600, 2600))
    assert mapping(r) == {"0": (1, None), "1": (2, None), "2": (3, None)}
    assert r.ambiguous is True


def test_shift_that_leaves_the_season_is_not_ambiguous() -> None:
    # Two-episode season: shifting E1-E2 either way runs off the list
    r = align(titles(3000, 3000), eps(3000, 3000))
    assert r.ambiguous is False


def test_shift_crossing_a_season_boundary_is_not_ambiguous() -> None:
    listed = [Episode(season=1, number=1, runtime_s=3000), Episode(season=2, number=1, runtime_s=3000)]
    r = align(titles(3000), listed)
    assert [(m.season, m.episode) for m in r.matches] == [(1, 1)]
    assert r.ambiguous is False


def test_shift_onto_a_two_episode_match_is_not_ambiguous() -> None:
    # -1 runs E1 off the list; +1 would move E1 onto E2, which the double holds
    r = align(titles(3000, 6010, 3000), eps(3000, 3000, 3000, 3000, 3000, 3000))
    assert mapping(r) == {"0": (1, None), "1": (2, 3), "2": (4, None)}
    assert r.ambiguous is False


def test_ambiguity_ignores_two_episode_matches() -> None:
    # Only the single-episode match (E3) is shifted (to E4); the double stays put
    r = align(titles(6000, 3000), eps(3000, 3000, 3000, 3000, 3000))
    assert mapping(r) == {"0": (1, 2), "1": (3, None)}
    assert r.ambiguous is True


def test_shift_with_worse_total_delta_is_not_ambiguous() -> None:
    # Shifting forward moves 3000 -> 3200 (within tolerance) but adds 200 s of delta
    r = align(titles(3000), eps(3000, 3200))
    assert r.ambiguous is False


def test_unknown_runtimes_are_ambiguous() -> None:
    r = align(titles(2600, 2600), eps(None, None, None))
    assert r.ambiguous is True


def test_no_single_episode_match_is_not_ambiguous() -> None:
    assert align(titles(6000), eps(3000, 3000, 3000)).ambiguous is False
    assert align([], eps(3000)).ambiguous is False


def test_play_all_of_exactly_two_other_titles() -> None:
    # Minor 4: 6970 is the sum of the two other titles, not an E1-E2 double
    r = align(titles(3480, 3490, 6970), eps(3600, 3600, 3600, 3600))
    assert r.play_all == ("2",)
    assert mapping(r) == {"0": (1, None), "1": (2, None)}
