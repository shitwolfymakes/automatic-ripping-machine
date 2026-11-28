"""The "one version of the film" policy in track selection: what starts ticked with one version per set and
with every version, for the 3D reference disc, duplicates and decoys, editions and the 2D/3D rule (D58-D60)."""

from __future__ import annotations

import pytest

from arm_backend.track_selection import preset_ticks, select_tracks, select_tracks_for_review
from arm_common import DiscType, IdentificationMode, MediaType, OutputMode, RipPreset, TrackSelection
from arm_common.schemas import ScanResult, ScanTitle
from tests.bd_structure_scans import EXTRA, OTHER_ANGLE, PICK, SUBSET, br3d_structure_scan

JOB = "job_01JZXR7K3M5Q8N4VWA00000001"


def _preset(rule: TrackSelection, **filters: object) -> RipPreset:
    return RipPreset(
        id="rpr_test",
        name="test",
        media_type=MediaType.MOVIE,
        is_builtin=False,
        track_selection=rule,
        identification_mode=IdentificationMode.REQUIRED,
        output_mode=OutputMode.TRACKS,
        track_filters_json=dict(filters) or None,
    )


def _ticked(scan: ScanResult, rule: TrackSelection, **kw: object) -> set[str]:
    return {t.source_ref for t in select_tracks_for_review(JOB, scan, _preset(rule), **kw) if not t.excluded}  # type: ignore[arg-type]


def _rippable_ticks(rippable: frozenset[str], **kw: object) -> set[str]:
    ticks = preset_ticks(br3d_structure_scan(), _preset(TrackSelection.MAIN_FEATURE), rippable=rippable, **kw)  # type: ignore[arg-type]
    assert ticks is not None
    return set(ticks)


def _title(
    index: int, clips: tuple[int, ...], *, seconds: int = 7200, source: str | None = None, **kw: object
) -> ScanTitle:
    return ScanTitle(
        index=index,
        duration_seconds=seconds,
        chapter_count=kw.pop("chapters", 12),  # type: ignore[arg-type]
        segment_map=list(clips),
        source_file=source or f"{index:05d}.mpls",
        **kw,  # type: ignore[arg-type]
    )


def _bd(*titles: ScanTitle) -> ScanResult:
    return ScanResult(disc_type=DiscType.BLURAY, titles=list(titles))


# --- the 3D reference disc ---


@pytest.mark.parametrize("rule", [TrackSelection.MAIN_FEATURE, TrackSelection.ALL_TRACKS, TrackSelection.ARCHIVE])
def test_one_version_ticks_the_pick_only(rule: TrackSelection) -> None:
    ticked = _ticked(br3d_structure_scan(), rule, tick_one_version=True)
    assert PICK in ticked and OTHER_ANGLE not in ticked and SUBSET not in ticked


def test_main_feature_with_every_version_ticks_the_pick_and_all_its_alternates() -> None:
    ticked = _ticked(br3d_structure_scan(), TrackSelection.MAIN_FEATURE, tick_one_version=False)
    assert ticked == {PICK, OTHER_ANGLE, SUBSET}


@pytest.mark.parametrize("rule", [TrackSelection.ALL_TRACKS, TrackSelection.ARCHIVE])
def test_every_version_ticks_every_feature_title(rule: TrackSelection) -> None:
    ticked = _ticked(br3d_structure_scan(), rule, tick_one_version=False)
    assert ticked == {EXTRA, PICK, OTHER_ANGLE, SUBSET}


def test_the_policy_defaults_to_one_version() -> None:
    assert _ticked(br3d_structure_scan(), TrackSelection.MAIN_FEATURE) == {PICK}


def test_a_custom_allowlist_ignores_the_policy_and_the_classes() -> None:
    preset = _preset(TrackSelection.CUSTOM, title_indices=[2])
    for one in (True, False):
        tracks = select_tracks(JOB, br3d_structure_scan(), preset, tick_one_version=one)
        assert {t.source_ref for t in tracks} == {OTHER_ANGLE}


# --- duplicates and decoys are never ticked (D58) ---


def test_duplicates_and_decoys_stay_unticked_with_every_version() -> None:
    scan = _bd(
        _title(0, (1, 2, 3), source="00100.mpls"),
        _title(1, (1, 2, 3), source="00101.mpls"),  # exact duplicate
        _title(2, (3, 2, 1), source="00102.mpls"),  # decoy: same clips, other order
    )
    for rule in (TrackSelection.MAIN_FEATURE, TrackSelection.ALL_TRACKS, TrackSelection.ARCHIVE):
        assert _ticked(scan, rule, tick_one_version=False) == {"0"}


# --- editions (D59) ---


def _editions() -> ScanResult:
    return _bd(
        _title(0, (1, 2, 3, 4), seconds=7200, source="00100.mpls"),
        _title(1, (1, 2, 3, 5), seconds=7800, source="00101.mpls"),
        _title(2, (1, 2, 3, 5), seconds=7800, source="00102.mpls", angle=2),
    )


def test_every_edition_starts_ticked_with_one_version_per_film() -> None:
    scan = _bd(
        _title(0, (1, 2, 3, 4), seconds=7200, source="00100.mpls"),
        _title(1, (1, 2, 3, 5), seconds=7800, source="00101.mpls"),
    )
    assert _ticked(scan, TrackSelection.MAIN_FEATURE, tick_one_version=True) == {"0", "1"}


def test_an_editions_alternates_follow_the_policy() -> None:
    scan = _bd(
        _title(0, (1, 2, 3, 4), seconds=7200, source="00100.mpls"),
        _title(1, (1, 2, 3, 5), seconds=7800, source="00101.mpls", angle=1),
        _title(2, (1, 2, 3, 6), seconds=7800, source="00101.mpls", angle=2),
    )
    assert _ticked(scan, TrackSelection.MAIN_FEATURE, tick_one_version=True) == {"0", "1"}
    assert _ticked(scan, TrackSelection.MAIN_FEATURE, tick_one_version=False) == {"0", "1", "2"}


# --- 2D / 3D (D60) ---


def _views() -> ScanResult:
    return _bd(
        _title(0, (10, 11, 12), source="00100.mpls", stereo_3d=False),
        _title(1, (10, 11, 12), source="00101.mpls", stereo_3d=True),
    )


@pytest.mark.parametrize("prefer_3d, expected", [(False, {"0"}), (True, {"1"}), (None, {"0"})])
def test_the_view_preference_picks_the_dimension(prefer_3d: bool | None, expected: set[str]) -> None:
    assert _ticked(_views(), TrackSelection.MAIN_FEATURE, prefer_stereo_3d=prefer_3d) == expected


def test_every_version_ticks_both_views_whatever_the_preference() -> None:
    for prefer in (False, True):
        assert _ticked(_views(), TrackSelection.MAIN_FEATURE, tick_one_version=False, prefer_stereo_3d=prefer) == {
            "0",
            "1",
        }


def test_choosing_2d_still_leaves_the_angle_axis_to_the_pick_order() -> None:
    scan = _bd(
        _title(0, (1, 9), source="00334.mpls", angle=1, stereo_3d=True),
        _title(1, (2, 9), source="00334.mpls", angle=2, stereo_3d=True),
        _title(2, (1, 9), source="00335.mpls", angle=1, stereo_3d=False),
        _title(3, (2, 9), source="00335.mpls", angle=2, stereo_3d=False),
    )
    assert _ticked(scan, TrackSelection.MAIN_FEATURE, prefer_stereo_3d=False) == {"2"}
    assert _ticked(scan, TrackSelection.MAIN_FEATURE, prefer_stereo_3d=True) == {"0"}
    assert _ticked(scan, TrackSelection.MAIN_FEATURE, tick_one_version=False, prefer_stereo_3d=False) == {
        "0",
        "1",
        "2",
        "3",
    }


# --- unrippable picks ---


def test_an_unrippable_pick_gives_way_to_its_first_rippable_alternate() -> None:
    rippable = frozenset({EXTRA, OTHER_ANGLE, SUBSET})
    assert _rippable_ticks(rippable) == {OTHER_ANGLE}


def test_a_rippable_pick_never_moves() -> None:
    rippable = frozenset({EXTRA, PICK})
    assert _rippable_ticks(rippable) == {PICK}


def test_every_version_drops_only_the_unrippable_members() -> None:
    rippable = frozenset({PICK, SUBSET})
    ticked = _rippable_ticks(rippable, tick_one_version=False)
    assert ticked == {PICK, SUBSET}


def test_nothing_rippable_ticks_nothing() -> None:
    assert _rippable_ticks(frozenset()) == set()


# --- preset_ticks ---


def test_preset_ticks_are_the_refs_the_review_would_tick() -> None:
    scan = br3d_structure_scan()
    preset = _preset(TrackSelection.MAIN_FEATURE)
    assert preset_ticks(scan, preset, tick_one_version=False) == frozenset({PICK, OTHER_ANGLE, SUBSET})
    assert preset_ticks(scan, preset, tick_one_version=True) == frozenset({PICK})


def test_a_preset_that_takes_the_disc_whole_has_no_ticks() -> None:
    preset = _preset(TrackSelection.MAIN_FEATURE).model_copy(update={"output_mode": OutputMode.ISO})
    assert preset_ticks(br3d_structure_scan(), preset) is None
