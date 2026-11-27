"""Version classes: angle, subset and view, the pick order and the chapter tie-break."""

import json
import random
from pathlib import Path

import pytest

from arm_common import TitleClass
from arm_common.schemas import ScanTitle
from arm_common.title_classes import (
    ALTERNATE_CLASSES,
    KEPT_CLASSES,
    TitleVerdict,
    classify_titles,
    pick_version,
    shared_clips,
    version_sets,
)

FIXTURES = Path(__file__).parent / "fixtures" / "scan_titles"


def load(name):
    return [ScanTitle.model_validate(row) for row in json.loads((FIXTURES / f"{name}.json").read_text())]


def classes(verdicts):
    return {i: (v.title_class, v.of_index) for i, v in verdicts.items()}


def title(index, seconds=7200, clips=(1, 2), chapters=10, angle=None, stereo=False, source=None, name=None):
    return ScanTitle(
        index=index,
        duration_seconds=seconds,
        chapter_count=chapters,
        source_file=source or f"{index:05d}.mpls",
        segment_count=len(clips),
        segment_map=list(clips),
        playlist_name=name,
        angle=angle,
        stereo_3d=stereo,
    )


BR2049 = {
    0: (TitleClass.PRIMARY, None),
    1: (TitleClass.PRIMARY, None),
    2: (TitleClass.ANGLE, 1),
    3: (TitleClass.SUBSET, 1),
}


def test_blade_runner_3d_angles_and_subset():
    assert classes(classify_titles(load("bd_3d_angles"))) == BR2049


def test_blade_runner_3d_same_verdicts_from_the_makemkv_fallback_form():
    titles = [t.model_copy(update={"playlist_name": None, "size_bytes": None}) for t in load("bd_3d_angles")]
    random.Random(7).shuffle(titles)
    assert classes(classify_titles(titles)) == BR2049


def test_last_crusade_uhd_is_unchanged():
    assert classes(classify_titles(load("uhd_single_feature"))) == {
        0: (TitleClass.PRIMARY, None),
        1: (TitleClass.PRIMARY, None),
        2: (TitleClass.DUPLICATE, 0),
        3: (TitleClass.DUPLICATE, 1),
    }


@pytest.mark.parametrize(
    ("prefer", "pick"),
    [(None, 0), (False, 0), (True, 1)],
)
def test_twin_views_are_classified_and_the_hook_picks(prefer, pick):
    verdicts = classify_titles(load("bd_2d_3d_views"), prefer_stereo_3d=prefer)
    other = 1 - pick
    assert verdicts[pick] == TitleVerdict(pick, TitleClass.PRIMARY, None)
    assert verdicts[other] == TitleVerdict(other, TitleClass.VIEW, pick)


def test_same_dimension_twins_are_duplicates_not_views():
    twins = [t.model_copy(update={"stereo_3d": True}) for t in load("bd_2d_3d_views")]
    verdicts = classify_titles(twins, prefer_stereo_3d=False)
    assert verdicts[1] == TitleVerdict(1, TitleClass.DUPLICATE, 0)


def test_view_and_angle_are_independent_axes():
    titles = [
        title(0, source="00334.mpls", clips=(1, 9), angle=1, stereo=True),
        title(1, source="00334.mpls", clips=(2, 9), angle=2, stereo=True),
        title(2, source="00335.mpls", clips=(1, 9), angle=1, stereo=False),
        title(3, source="00335.mpls", clips=(2, 9), angle=2, stereo=False),
    ]
    verdicts = classify_titles(titles, prefer_stereo_3d=False)
    # The 3D pick becomes a view of the 2D pick; its angle follows the pick it repointed to.
    assert classes(verdicts) == {
        0: (TitleClass.VIEW, 2),
        1: (TitleClass.ANGLE, 2),
        2: (TitleClass.PRIMARY, None),
        3: (TitleClass.ANGLE, 2),
    }


def test_angles_pick_follows_the_name_then_the_lowest_angle():
    titles = [
        title(0, source="00334.mpls", angle=2, clips=(1, 3)),
        title(1, source="00334.mpls", angle=1, clips=(1, 2)),
    ]
    verdicts = classify_titles(titles)
    assert classes(verdicts) == {0: (TitleClass.ANGLE, 1), 1: (TitleClass.PRIMARY, None)}
    named = [titles[0].model_copy(update={"playlist_name": "FPL_MainFeature"}), titles[1]]
    assert classes(classify_titles(named)) == {0: (TitleClass.PRIMARY, None), 1: (TitleClass.ANGLE, 0)}


def test_a_single_angle_is_not_an_angle_group():
    titles = [
        title(0, source="00334.mpls", angle=1, clips=(1, 2)),
        title(1, source="00335.mpls", angle=1, clips=(3, 4)),
    ]
    assert {v.title_class for v in classify_titles(titles).values()} == {TitleClass.PRIMARY}


def test_variant_stays_a_variant_when_the_short_copy_has_chapters():
    base = title(0, seconds=7000, clips=(2,), chapters=12)
    longer = title(1, seconds=7100, clips=(1, 2), chapters=12)
    assert classes(classify_titles([base, longer])) == {0: (TitleClass.PRIMARY, None), 1: (TitleClass.VARIANT, 0)}


def test_one_chapter_copy_never_beats_the_chaptered_original():
    base = title(0, seconds=7000, clips=(2,), chapters=1)
    longer = title(1, seconds=7100, clips=(1, 2), chapters=16)
    assert classes(classify_titles([base, longer])) == {0: (TitleClass.SUBSET, 1), 1: (TitleClass.PRIMARY, None)}


def test_equal_chapters_keep_the_shorter_as_the_pick():
    base = title(0, seconds=7000, clips=(2,), chapters=1)
    longer = title(1, seconds=7100, clips=(1, 2), chapters=1)
    assert classes(classify_titles([base, longer])) == {0: (TitleClass.PRIMARY, None), 1: (TitleClass.VARIANT, 0)}


def test_a_title_without_a_chapter_count_counts_as_chapterless():
    base = title(0, seconds=7000, clips=(2,), chapters=None)
    longer = title(1, seconds=7100, clips=(1, 2), chapters=16)
    assert classes(classify_titles([base, longer])) == {0: (TitleClass.SUBSET, 1), 1: (TitleClass.PRIMARY, None)}


def test_subset_repoints_the_variants_of_the_demoted_base():
    base = title(0, seconds=7000, clips=(2,), chapters=1)
    middle = title(1, seconds=7050, clips=(2, 5), chapters=1)
    longer = title(2, seconds=7100, clips=(1, 2, 5), chapters=16)
    verdicts = classify_titles([base, middle, longer])
    assert verdicts[2] == TitleVerdict(2, TitleClass.PRIMARY, None)
    assert {verdicts[0].of_index, verdicts[1].of_index} == {2}
    assert {verdicts[0].title_class, verdicts[1].title_class} <= {TitleClass.SUBSET, TitleClass.VARIANT}


def test_alternates_are_never_kept():
    assert ALTERNATE_CLASSES == {TitleClass.ANGLE, TitleClass.SUBSET, TitleClass.VARIANT, TitleClass.VIEW}
    assert not ALTERNATE_CLASSES & KEPT_CLASSES


@pytest.mark.parametrize(
    ("group", "preferred", "expected"),
    [
        # the only title with a playlist name wins over everything
        ([title(0), title(1, name="FPL_MainFeature"), title(2)], {2}, 1),
        # two names: the preferred one
        ([title(0, name="a"), title(1, name="b"), title(2)], {1}, 1),
        # the only one with more than one chapter
        ([title(0, chapters=1), title(1, chapters=16), title(2, chapters=1)], set(), 1),
        # tied chapters: the lowest angle
        ([title(0, angle=2), title(1, angle=1), title(2, angle=3)], set(), 1),
        # a title without an angle counts as angle 1
        ([title(0, angle=2), title(1, angle=None)], set(), 1),
        # tied angles: the lowest index
        ([title(3), title(1), title(2)], set(), 1),
    ],
)
def test_pick_version_order(group, preferred, expected):
    assert pick_version(group, preferred).index == expected


def test_shared_clips():
    a = title(0, clips=(1, 2, 3))
    b = title(1, clips=(2, 3, 4, 5))
    assert shared_clips(a, b) == (frozenset({2, 3}), frozenset({1}), frozenset({4, 5}))
    assert shared_clips(title(2, clips=(1,)), ScanTitle(index=3, duration_seconds=1)) == (
        frozenset(),
        frozenset({1}),
        frozenset(),
    )


def test_version_sets_group_alternates_with_their_pick():
    verdicts = classify_titles(load("bd_3d_angles"))
    assert version_sets(list(verdicts.values())) == [(1, 2, 3)]


def test_version_sets_merge_every_edition_into_one_set_with_its_alternates():
    verdicts = [
        TitleVerdict(0, TitleClass.EDITION, None),
        TitleVerdict(1, TitleClass.EDITION, None),
        TitleVerdict(2, TitleClass.ANGLE, 1),
        TitleVerdict(3, TitleClass.PRIMARY, None),
        TitleVerdict(4, TitleClass.DECOY, 3),
        TitleVerdict(5, TitleClass.VIEW, 6),
        TitleVerdict(6, TitleClass.PRIMARY, None),
    ]
    assert version_sets(verdicts) == [(0, 1, 2), (5, 6)]


def test_version_sets_empty_without_alternates():
    assert version_sets(list(classify_titles(load("uhd_single_feature")).values())) == []
