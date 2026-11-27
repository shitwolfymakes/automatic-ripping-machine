"""Blu-ray title classifier: decoys, duplicates, variants, editions."""

import json
import random
from pathlib import Path

import pytest

from arm_common import TitleClass
from arm_common.schemas import ScanTitle
from arm_common.title_classes import (
    KEPT_CLASSES,
    MAIN_FEATURE_MIN_SECONDS,
    TitleVerdict,
    _best_base,
    _extra_seconds,
    _m2ts_clip_number,
    _playlist_covers_raw,
    classify_titles,
    pick_representative,
)

FIXTURE = Path(__file__).parent / "fixtures" / "scan_titles" / "bd_decoy_playlists.json"
FEATURE = 2 * 3600
HOUR_41 = 6072


def title(index, seconds, clips=None, source=None, playlist_name=None):
    return ScanTitle(
        index=index,
        duration_seconds=seconds,
        source_file=source if source is not None else f"{index:05d}.mpls",
        segment_count=len(clips) if clips else None,
        segment_map=clips,
        playlist_name=playlist_name,
    )


def classes(verdicts):
    return {i: (v.title_class, v.of_index) for i, v in verdicts.items()}


def decoy_titles():
    return [ScanTitle.model_validate(row) for row in json.loads(FIXTURE.read_text())]


def assert_decoy_outcome(verdicts):
    assert len(verdicts) == 309
    kept = {i for i, v in verdicts.items() if v.title_class in KEPT_CLASSES}
    assert kept == {0, 1, 3, 4, 5, 6, 7, 8, 9, 10}
    assert {verdicts[i].title_class for i in kept} == {TitleClass.PRIMARY}
    assert verdicts[2] == TitleVerdict(2, TitleClass.VARIANT, 0)
    others = [v for i, v in verdicts.items() if i not in kept and i != 2]
    assert len(others) == 298
    assert {(v.title_class, v.of_index) for v in others} == {(TitleClass.DECOY, 0)}
    unticked = [v for v in verdicts.values() if v.title_class not in KEPT_CLASSES]
    assert len(unticked) == 299
    assert {v.of_index for v in unticked} == {0}


def test_decoy_fixture_outcome():
    assert_decoy_outcome(classify_titles(decoy_titles()))


def test_decoy_fixture_without_comment_keeps_lowest_index():
    titles = decoy_titles()
    titles[0] = titles[0].model_copy(update={"playlist_name": None})
    assert_decoy_outcome(classify_titles(titles))


def test_decoy_fixture_preferred_breaks_the_tie_without_comment():
    titles = decoy_titles()
    titles[0] = titles[0].model_copy(update={"playlist_name": None})
    verdicts = classify_titles(titles, preferred=frozenset({11}))
    assert verdicts[11].title_class is TitleClass.PRIMARY
    assert verdicts[0] == TitleVerdict(0, TitleClass.DECOY, 11)
    assert verdicts[2] == TitleVerdict(2, TitleClass.VARIANT, 11)


def test_decoy_fixture_is_deterministic_under_shuffle():
    titles = decoy_titles()
    expected = classify_titles(titles)
    random.Random(7).shuffle(titles)
    assert classify_titles(titles) == expected


def test_empty_scan():
    assert classify_titles([]) == {}


def test_titles_without_segment_map_are_all_primary():
    titles = [title(0, FEATURE), title(1, FEATURE), title(2, 600, source="1")]
    verdicts = classify_titles(titles)
    assert {v.title_class for v in verdicts.values()} == {TitleClass.PRIMARY}
    assert {v.of_index for v in verdicts.values()} == {None}


def test_exact_duplicates_keep_the_lowest_index():
    titles = [title(5, FEATURE, [1, 2, 3]), title(2, FEATURE, [1, 2, 3])]
    verdicts = classify_titles(titles)
    assert classes(verdicts) == {
        2: (TitleClass.PRIMARY, None),
        5: (TitleClass.DUPLICATE, 2),
    }


# Last Crusade shape: a playlist, a longer one, the raw stream of the first.


def last_crusade(playlist_clips, raw_clips):
    return [
        title(0, 7611, playlist_clips, "00801.mpls"),
        title(1, 7980, [900, 901], "00802.mpls"),
        title(2, 7611, raw_clips, "00294.m2ts"),
        title(3, 7560, [902, 903], "00803.mpls"),
    ]


@pytest.mark.parametrize("playlist_clips", [[294], [293, 294]])
@pytest.mark.parametrize("raw_clips", [[294], None])
def test_raw_stream_duplicate(playlist_clips, raw_clips):
    verdicts = classify_titles(last_crusade(playlist_clips, raw_clips))
    assert classes(verdicts) == {
        0: (TitleClass.PRIMARY, None),
        1: (TitleClass.PRIMARY, None),
        2: (TitleClass.DUPLICATE, 0),
        3: (TitleClass.PRIMARY, None),
    }


def test_raw_stream_with_longer_playlist_within_window():
    verdicts = classify_titles([title(0, 7611 + 60, [293, 294], "00801.mpls"), title(1, 7611, None, "00294.m2ts")])
    assert verdicts[1] == TitleVerdict(1, TitleClass.DUPLICATE, 0)


def test_raw_stream_not_covered_stays_primary():
    cases = {
        "playlist too long": [title(0, 7611 + 181, [294]), title(1, 7611, None, "00294.m2ts")],
        "playlist shorter": [title(0, 7610, [294]), title(1, 7611, None, "00294.m2ts")],
        "clip not in playlist": [title(0, 7611, [295]), title(1, 7611, None, "00294.m2ts")],
        "no playlist": [title(0, 7611, None, "00294.m2ts"), title(1, 9, [1], "00295.m2ts")],
    }
    for name, titles in cases.items():
        assert classes(classify_titles(titles))[1][0] is TitleClass.PRIMARY, name


def test_raw_stream_picks_the_commented_playlist():
    titles = [
        title(0, 7611, [294], "00801.mpls"),
        title(1, 7611, [294, 295], "00802.mpls", playlist_name="FPL_MainFeature"),
        title(2, 7611, None, "00294.m2ts"),
    ]
    verdicts = classify_titles(titles)
    assert verdicts[2] == TitleVerdict(2, TitleClass.DUPLICATE, 1)


def test_raw_stream_ignores_titles_already_duplicates():
    # t0 and t1 are equal; the raw stream points at the survivor only.
    titles = [
        title(0, 7611, [293, 294], "00801.mpls"),
        title(1, 7611, [293, 294], "00802.mpls"),
        title(2, 7611, None, "00294.m2ts"),
    ]
    verdicts = classify_titles(titles)
    assert verdicts[1] == TitleVerdict(1, TitleClass.DUPLICATE, 0)
    assert verdicts[2] == TitleVerdict(2, TitleClass.DUPLICATE, 0)


def test_raw_stream_already_a_duplicate_is_left_alone():
    titles = [
        title(0, 7611, [294], "00294.m2ts"),
        title(1, 7611, [294], "00295.m2ts"),
        title(2, 7611, [293, 294], "00801.mpls"),
    ]
    verdicts = classify_titles(titles)
    assert verdicts[1] == TitleVerdict(1, TitleClass.DUPLICATE, 0)


def test_raw_stream_uses_clip_seconds_when_known():
    playlist = title(0, 9000, [293, 294], "00801.mpls")
    raw = title(1, 7611, None, "00294.m2ts")
    # Playlist is far longer than the window, but the clip is the raw's length.
    assert classify_titles([playlist, raw])[1].title_class is TitleClass.PRIMARY
    verdicts = classify_titles([playlist, raw], clip_seconds={294: 7610.0})
    assert verdicts[1] == TitleVerdict(1, TitleClass.DUPLICATE, 0)
    short = classify_titles([playlist, raw], clip_seconds={294: 7000.0})
    assert short[1].title_class is TitleClass.PRIMARY


# Variants


def test_variant_with_clip_durations_instead_of_title_durations():
    base = title(0, 6000, [1, 2, 3])
    disclaimer = title(1, 6000 + 500, [1, 2, 3, 9], playlist_name="Copy Disclaimer")
    # Title durations say +500 s (too long); the extra clip is only 60 s.
    assert classify_titles([base, disclaimer])[1].title_class in KEPT_CLASSES
    verdicts = classify_titles([base, disclaimer], clip_seconds={9: 60.0})
    assert verdicts[1] == TitleVerdict(1, TitleClass.VARIANT, 0)
    # Unknown extra clip: falls back to the title durations.
    verdicts = classify_titles([base, disclaimer], clip_seconds={7: 1.0})
    assert verdicts[1].title_class in KEPT_CLASSES


def test_variant_limits():
    base = title(0, 6000, [1, 2, 3])
    cases = {
        "three extra clips": title(1, 6060, [1, 2, 3, 7, 8, 9]),
        "too much extra time": title(2, 6000 + 181, [1, 2, 3, 9]),
        "no extra time": title(3, 6000, [1, 2, 3, 9]),
        "not a superset": title(4, 6060, [1, 2, 9]),
        "same clip set": title(5, 6060, [3, 2, 1]),
    }
    for name, other in cases.items():
        verdicts = classify_titles([base, other])
        assert verdicts[other.index].title_class is not TitleClass.VARIANT, name


def test_variant_prefers_the_largest_clip_set_then_lowest_index():
    small = title(0, 5000, [1, 2])
    big = title(1, 5900, [1, 2, 3, 4])
    twin = title(2, 5900, [1, 2, 4, 3])  # decoy of big, never a base
    variant = title(3, 5960, [1, 2, 3, 4, 9])
    verdicts = classify_titles([small, big, twin, variant])
    assert verdicts[3] == TitleVerdict(3, TitleClass.VARIANT, 1)
    assert verdicts[2] == TitleVerdict(2, TitleClass.DECOY, 1)


def test_variant_ties_take_the_lowest_index():
    a = title(0, 5900, [1, 2, 3])
    b = title(1, 5900, [1, 2, 4])
    variant = title(2, 5960, [1, 2, 3, 4])
    assert classify_titles([a, b, variant])[2] == TitleVerdict(2, TitleClass.VARIANT, 0)


def test_variant_of_a_decoy_group_representative_repoints_its_decoys():
    base = title(0, 5000, [1, 2, 3])
    # Group of two: rep (index 1, commented) is also a variant of base.
    rep = title(1, 5060, [1, 2, 3, 9], playlist_name="FPL_MainFeature")
    decoy = title(2, 5060, [9, 3, 2, 1])
    verdicts = classify_titles([base, rep, decoy])
    assert verdicts[1] == TitleVerdict(1, TitleClass.VARIANT, 0)
    assert verdicts[2] == TitleVerdict(2, TitleClass.DECOY, 0)


def test_variant_chain_repoints_when_the_base_is_demoted_later():
    outer = title(0, 5120, [1, 2, 3, 8, 9])
    middle = title(1, 5060, [1, 2, 3, 9])
    inner = title(2, 5000, [1, 2, 3])
    verdicts = classify_titles([outer, middle, inner])
    assert verdicts[0] == TitleVerdict(0, TitleClass.VARIANT, 2)
    assert verdicts[1] == TitleVerdict(1, TitleClass.VARIANT, 2)
    assert verdicts[2].title_class is TitleClass.PRIMARY


# Editions


def test_two_editions():
    theatrical = title(0, 2 * 3600, list(range(1, 21)))
    extended = title(1, 2 * 3600 + 17 * 60, list(range(1, 21)) + [31, 32, 33, 34])
    verdicts = classify_titles([theatrical, extended])
    assert classes(verdicts) == {
        0: (TitleClass.EDITION, None),
        1: (TitleClass.EDITION, None),
    }


def test_editions_keep_their_decoys_out():
    theatrical = title(0, 2 * 3600, list(range(1, 21)))
    extended = title(1, 2 * 3600 + 17 * 60, list(range(1, 21)) + [31, 32, 33, 34])
    decoy = title(2, 2 * 3600, list(range(20, 0, -1)))
    verdicts = classify_titles([theatrical, extended, decoy])
    assert verdicts[2] == TitleVerdict(2, TitleClass.DECOY, 0)
    assert verdicts[0].title_class is TitleClass.EDITION
    assert verdicts[1].title_class is TitleClass.EDITION


def test_three_d_pair_within_three_minutes_stays_primary():
    left = title(0, FEATURE, list(range(1, 21)))
    right = title(1, FEATURE + 120, list(range(1, 15)) + [31, 32, 33, 34, 35, 36])
    verdicts = classify_titles([left, right])
    assert {v.title_class for v in verdicts.values()} == {TitleClass.PRIMARY}


def test_low_overlap_pair_stays_primary():
    one = title(0, FEATURE, list(range(1, 21)))
    two = title(1, FEATURE + 1200, list(range(15, 35)))
    verdicts = classify_titles([one, two])
    assert {v.title_class for v in verdicts.values()} == {TitleClass.PRIMARY}


def test_short_pair_is_not_feature_length():
    shorts = [title(0, 600, [1, 2, 3, 4]), title(1, 1500, [1, 2, 3, 5])]
    verdicts = classify_titles(shorts)
    assert {v.title_class for v in verdicts.values()} == {TitleClass.PRIMARY}


def test_feature_floor_is_a_share_of_the_longest_kept_title():
    # 50 min and 4 h overlap, but 50 min is under 60 % of 4 h.
    pair = [title(0, 3000, [1, 2, 3, 4]), title(1, 4 * 3600, [1, 2, 3, 4, 5, 6, 7, 8])]
    assert {v.title_class for v in classify_titles(pair).values()} == {TitleClass.PRIMARY}


def test_unstructured_features_never_pair_as_editions():
    # An unstructured feature-length title never joins an edition pair.
    verdicts = classify_titles([title(0, FEATURE), title(1, FEATURE + 1200)])
    assert {v.title_class for v in verdicts.values()} == {TitleClass.PRIMARY}


# Helpers


def test_pick_representative_rules():
    plain = title(3, 10, [1, 2])
    lower = title(1, 10, [2, 1])
    commented = title(2, 10, [1, 3], playlist_name="FPL")
    other_commented = title(4, 10, [3, 1], playlist_name="X")
    assert pick_representative([plain, lower], frozenset()) is lower
    assert pick_representative([plain, commented], frozenset({3})) is commented
    assert pick_representative([plain, lower], frozenset({3})) is plain
    # Two comments, no preference: lowest index.
    assert pick_representative([other_commented, commented], frozenset()) is commented
    # Two comments narrowed by preference.
    assert pick_representative([other_commented, commented], frozenset({4})) is other_commented


def test_m2ts_clip_number():
    assert _m2ts_clip_number("00294.m2ts") == 294
    assert _m2ts_clip_number("00294.M2TS") == 294
    assert _m2ts_clip_number("00294.mpls") is None
    assert _m2ts_clip_number("title.m2ts") is None
    assert _m2ts_clip_number("5") is None
    assert _m2ts_clip_number(None) is None


def test_playlist_covers_raw_requires_an_mpls_source():
    raw = title(1, 100, None, "00294.m2ts")
    assert not _playlist_covers_raw(title(0, 100, [294], "00294.m2ts"), raw, 294, None)
    no_source = title(0, 100, [294]).model_copy(update={"source_file": None})
    assert not _playlist_covers_raw(no_source, raw, 294, None)
    assert _playlist_covers_raw(title(0, 100, [294], "00001.MPLS"), raw, 294, None)


def test_extra_seconds_and_best_base_without_candidates():
    base = title(0, 100, [1])
    cand = title(1, 130, [1, 2])
    assert _extra_seconds(base, cand, None) == 30
    assert _extra_seconds(base, cand, {2: 12.5}) == 12.5
    assert _best_base(cand, [], None) is None


def test_main_feature_threshold_is_forty_five_minutes():
    assert MAIN_FEATURE_MIN_SECONDS == 45 * 60
