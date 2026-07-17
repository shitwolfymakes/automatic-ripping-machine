"""Track-selection rule unit tests."""

import pytest

from arm_backend.track_selection import (
    ALL_TRACKS_MIN_SECONDS,
    MAIN_FEATURE_MIN_SECONDS,
    select_tracks,
    select_tracks_for_review,
)
from arm_common import (
    DiscType,
    IdentificationMode,
    MediaType,
    OutputMode,
    RipPreset,
    TrackKind,
    TrackSelection,
)
from arm_common.schemas import ScanResult, ScanTitle


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


def _scan(*durations: int) -> ScanResult:
    return ScanResult(
        disc_type=DiscType.DVD,
        titles=[ScanTitle(index=i, duration_seconds=d) for i, d in enumerate(durations)],
    )


def test_archive_returns_every_title():
    scan = _scan(120, 90 * 60, 30, 60 * 60)
    tracks = select_tracks("job_01JZXR7K3M5Q8N4VWA00000001", scan, _preset(TrackSelection.ARCHIVE))
    assert [t.index for t in tracks] == [0, 1, 2, 3]
    assert all(t.kind == TrackKind.VIDEO_TITLE for t in tracks)


def test_all_tracks_filters_below_minimum():
    short = ALL_TRACKS_MIN_SECONDS - 1
    scan = _scan(short, ALL_TRACKS_MIN_SECONDS, 5 * 60, short)
    tracks = select_tracks("job_01JZXR7K3M5Q8N4VWA00000001", scan, _preset(TrackSelection.ALL_TRACKS))
    assert [t.index for t in tracks] == [1, 2]


def test_main_feature_returns_longest_above_threshold():
    scan = _scan(60 * 30, 90 * 60, 60 * 60, 45 * 60)
    tracks = select_tracks("job_01JZXR7K3M5Q8N4VWA00000001", scan, _preset(TrackSelection.MAIN_FEATURE))
    assert len(tracks) == 1
    assert tracks[0].index == 1
    assert tracks[0].expected_duration_seconds == 90 * 60


def test_main_feature_falls_back_to_longest_when_no_threshold_match():
    short = MAIN_FEATURE_MIN_SECONDS - 1
    scan = _scan(short, short - 100, short - 50)
    tracks = select_tracks("job_01JZXR7K3M5Q8N4VWA00000001", scan, _preset(TrackSelection.MAIN_FEATURE))
    assert len(tracks) == 1
    assert tracks[0].index == 0  # longest of the shorts
    assert tracks[0].expected_duration_seconds == short


def test_custom_without_filters_raises():
    from arm_backend.track_selection import TrackSelectionError

    with pytest.raises(TrackSelectionError):
        select_tracks("job_01JZXR7K3M5Q8N4VWA00000001", _scan(60), _preset(TrackSelection.CUSTOM))


def test_empty_scan_returns_empty():
    tracks = select_tracks("job_01JZXR7K3M5Q8N4VWA00000001", _scan(), _preset(TrackSelection.ARCHIVE))
    assert tracks == []


def test_data_disc_emits_single_dump():
    scan = ScanResult(disc_type=DiscType.DATA, volume_label="DATA_DISC")
    tracks = select_tracks("job_01JZXR7K3M5Q8N4VWA00000001", scan, _preset(TrackSelection.ALL_TRACKS))
    assert len(tracks) == 1
    assert tracks[0].kind == TrackKind.DATA_DUMP
    assert tracks[0].source_ref == "full"


def test_cd_emits_audio_tracks():
    scan = ScanResult(
        disc_type=DiscType.CD,
        titles=[ScanTitle(index=i, duration_seconds=180) for i in range(1, 4)],
    )
    tracks = select_tracks("job_01JZXR7K3M5Q8N4VWA00000001", scan, _preset(TrackSelection.ALL_TRACKS))
    assert [t.kind for t in tracks] == [TrackKind.AUDIO_TRACK] * 3
    assert [t.index for t in tracks] == [1, 2, 3]


# --- select_tracks_for_review (timed review gate: persist ALL, default excluded) ---


def test_review_persists_all_titles_with_main_feature_defaults():
    """MAIN_FEATURE keeps only the longest title; review persists ALL of them,
    marking the non-kept ones excluded by default."""
    scan = _scan(120, 90 * 60, 30, 60 * 60)  # indices 0..3; longest = index 1
    tracks = select_tracks_for_review("job_01JZXR7K3M5Q8N4VWA00000001", scan, _preset(TrackSelection.MAIN_FEATURE))
    assert [t.index for t in tracks] == [0, 1, 2, 3]  # every title persisted
    kept = {t.index for t in tracks if not t.excluded}
    assert kept == {1}  # only the longest is kept by default
    assert all(t.excluded for t in tracks if t.index != 1)


def test_review_archive_keeps_all_unexcluded():
    """ARCHIVE keeps every title -> none excluded by default."""
    scan = _scan(120, 5400, 30)
    tracks = select_tracks_for_review("job_01JZXR7K3M5Q8N4VWA00000001", scan, _preset(TrackSelection.ARCHIVE))
    assert len(tracks) == 3
    assert all(not t.excluded for t in tracks)


def test_review_all_tracks_excludes_below_minlength():
    """ALL_TRACKS drops titles under the min-length -> those persist excluded."""
    short = ALL_TRACKS_MIN_SECONDS - 1
    scan = _scan(short, 3600, short)
    tracks = select_tracks_for_review("job_01JZXR7K3M5Q8N4VWA00000001", scan, _preset(TrackSelection.ALL_TRACKS))
    assert len(tracks) == 3  # all persisted
    kept = {t.index for t in tracks if not t.excluded}
    assert kept == {1}  # only the above-threshold one kept by default


def test_review_data_disc_delegates_to_single_dump():
    scan = ScanResult(disc_type=DiscType.DATA, volume_label="DATA_DISC")
    tracks = select_tracks_for_review("job_01JZXR7K3M5Q8N4VWA00000001", scan, _preset(TrackSelection.ALL_TRACKS))
    assert len(tracks) == 1
    assert tracks[0].kind == TrackKind.DATA_DUMP
