"""Tracks of a structure scan are keyed by title ref and carry the classifier's verdicts as refs."""

from __future__ import annotations

from arm_backend.track_selection import select_tracks, select_tracks_for_review
from arm_common import (
    DiscType,
    IdentificationMode,
    MediaType,
    OutputMode,
    RipPreset,
    TrackSelection,
)
from arm_common.schemas import BdPlaylist, ScanResult, ScanTitle
from arm_common.title_classes import TitleClass
from tests.bd_structure_scans import EXTRA, OTHER_ANGLE, PICK, SUBSET, br3d_makemkv_titles, br3d_structure_scan

JOB = "job_01JZXR7K3M5Q8N4VWA00000001"


def _preset(rule: TrackSelection) -> RipPreset:
    return RipPreset(
        id="rpr_test",
        name="test",
        media_type=MediaType.MOVIE,
        is_builtin=False,
        track_selection=rule,
        identification_mode=IdentificationMode.REQUIRED,
        output_mode=OutputMode.TRACKS,
    )


def test_review_tracks_are_keyed_by_title_ref_in_card_order() -> None:
    tracks = select_tracks_for_review(JOB, br3d_structure_scan(), _preset(TrackSelection.MAIN_FEATURE))
    assert [(t.index, t.source_ref) for t in tracks] == [(0, EXTRA), (1, PICK), (2, OTHER_ANGLE), (3, SUBSET)]


def test_review_tracks_carry_the_structure_facts() -> None:
    tracks = {
        t.source_ref: t for t in select_tracks_for_review(JOB, br3d_structure_scan(), _preset(TrackSelection.ARCHIVE))
    }
    assert tracks[PICK].source_file == "00334.mpls"
    assert tracks[PICK].expected_duration_seconds == 9807
    assert tracks[PICK].expected_size_bytes is not None


def test_verdicts_point_at_refs_not_indexes() -> None:
    tracks = {
        t.source_ref: t for t in select_tracks_for_review(JOB, br3d_structure_scan(), _preset(TrackSelection.ARCHIVE))
    }
    assert tracks[PICK].title_class == TitleClass.PRIMARY and tracks[PICK].title_class_ref is None
    assert (tracks[OTHER_ANGLE].title_class, tracks[OTHER_ANGLE].title_class_ref) == (TitleClass.ANGLE, PICK)
    assert (tracks[SUBSET].title_class, tracks[SUBSET].title_class_ref) == (TitleClass.SUBSET, PICK)


def test_main_feature_of_a_structure_scan_keeps_the_pick_only() -> None:
    tracks = select_tracks_for_review(JOB, br3d_structure_scan(), _preset(TrackSelection.MAIN_FEATURE))
    assert {t.source_ref for t in tracks if not t.excluded} == {PICK}


def test_select_tracks_leaves_out_refs_that_are_not_rippable() -> None:
    tracks = select_tracks(JOB, br3d_structure_scan(), _preset(TrackSelection.ARCHIVE), rippable=frozenset({EXTRA}))
    assert {t.source_ref for t in tracks} == {EXTRA}
    both = select_tracks(JOB, br3d_structure_scan(), _preset(TrackSelection.ARCHIVE), rippable=frozenset({EXTRA, PICK}))
    assert {t.source_ref for t in both} == {EXTRA, PICK}


def test_a_preferred_ref_decides_between_look_alike_titles() -> None:
    scan = br3d_structure_scan()
    tracks = select_tracks_for_review(
        JOB, scan, _preset(TrackSelection.MAIN_FEATURE), preferred=frozenset({OTHER_ANGLE})
    )
    assert {t.source_ref for t in tracks if not t.excluded} == {OTHER_ANGLE}


def _fallback_scan() -> ScanResult:
    """The same disc after a failed structure read: MakeMKV's titles, no playlists."""
    return ScanResult(disc_type=DiscType.BLURAY, titles=br3d_makemkv_titles())


def test_a_makemkv_scan_keeps_index_keys_and_gets_the_same_verdicts() -> None:
    tracks = {t.source_ref: t for t in select_tracks_for_review(JOB, _fallback_scan(), _preset(TrackSelection.ARCHIVE))}
    assert set(tracks) == {"0", "1", "2", "3"}
    assert (tracks["2"].title_class, tracks["2"].title_class_ref) == (TitleClass.ANGLE, "1")
    assert (tracks["3"].title_class, tracks["3"].title_class_ref) == (TitleClass.SUBSET, "1")


def test_a_dvd_is_unchanged() -> None:
    scan = ScanResult(
        disc_type=DiscType.DVD,
        titles=[ScanTitle(index=1, duration_seconds=5400), ScanTitle(index=2, duration_seconds=30)],
    )
    tracks = select_tracks_for_review(JOB, scan, _preset(TrackSelection.MAIN_FEATURE))
    assert [(t.source_ref, t.title_class, t.title_class_ref, t.excluded) for t in tracks] == [
        ("1", None, None, False),
        ("2", None, None, True),
    ]


def test_a_blu_ray_with_playlists_below_the_minimum_has_no_tracks() -> None:
    short = BdPlaylist(name="00001.mpls", clips=[1], clip_seconds=[30.0], duration_seconds=30, chapter_count=1)
    scan = ScanResult(disc_type=DiscType.BLURAY, playlists=[short])
    assert select_tracks(JOB, scan, _preset(TrackSelection.ARCHIVE)) == []
