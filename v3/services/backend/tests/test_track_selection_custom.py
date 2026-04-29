import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.track_selection import TrackSelectionError, select_tracks  # noqa: E402
from arm_common import (  # noqa: E402
    DiscType,
    IdentificationMode,
    MediaType,
    OutputMode,
    RipPreset,
    TrackKind,
    TrackSelection,
)
from arm_common.schemas import ScanResult, ScanTitle  # noqa: E402


def _scan(*durations: int) -> ScanResult:
    return ScanResult(
        disc_type=DiscType.DVD,
        titles=[ScanTitle(index=i + 1, duration_seconds=d) for i, d in enumerate(durations)],
    )


def _custom_preset(filters: dict) -> RipPreset:
    return RipPreset(
        id="rpr_test",
        name="custom",
        media_type=MediaType.MOVIE,
        track_selection=TrackSelection.CUSTOM,
        identification_mode=IdentificationMode.REQUIRED,
        output_mode=OutputMode.TRACKS,
        track_filters_json=filters,
    )


def test_custom_min_duration_filters_short_tracks() -> None:
    scan = _scan(30, 120, 3600)
    preset = _custom_preset({"min_duration_seconds": 100})
    result = select_tracks("job_x", scan, preset)
    assert sorted(t.index for t in result) == [2, 3]


def test_custom_max_duration_filters_long_tracks() -> None:
    scan = _scan(30, 120, 3600)
    preset = _custom_preset({"max_duration_seconds": 200})
    result = select_tracks("job_x", scan, preset)
    assert sorted(t.index for t in result) == [1, 2]


def test_custom_indices_allowlist() -> None:
    scan = _scan(60, 60, 60, 60)
    preset = _custom_preset({"title_indices": [1, 3]})
    result = select_tracks("job_x", scan, preset)
    assert sorted(t.index for t in result) == [1, 3]


def test_custom_indices_blocklist() -> None:
    scan = _scan(60, 60, 60, 60)
    preset = _custom_preset({"title_indices_exclude": [2, 4]})
    result = select_tracks("job_x", scan, preset)
    assert sorted(t.index for t in result) == [1, 3]


def test_custom_combinations_anded() -> None:
    scan = _scan(30, 120, 3600, 7200)
    preset = _custom_preset({"title_indices": [2, 3, 4], "max_duration_seconds": 4000})
    result = select_tracks("job_x", scan, preset)
    assert sorted(t.index for t in result) == [2, 3]


def test_custom_with_no_matches_returns_empty_list() -> None:
    scan = _scan(60)
    preset = _custom_preset({"min_duration_seconds": 1000})
    assert select_tracks("job_x", scan, preset) == []


def test_custom_without_filters_raises() -> None:
    preset = RipPreset(
        id="rpr_bad",
        name="bad",
        media_type=MediaType.MOVIE,
        track_selection=TrackSelection.CUSTOM,
        identification_mode=IdentificationMode.REQUIRED,
        output_mode=OutputMode.TRACKS,
        track_filters_json=None,
    )
    with pytest.raises(TrackSelectionError):
        select_tracks("job_x", _scan(60), preset)


def test_audio_custom_filters_apply_to_cd_scan() -> None:
    scan = ScanResult(
        disc_type=DiscType.CD,
        titles=[ScanTitle(index=i, duration_seconds=180) for i in range(1, 11)],
    )
    preset = _custom_preset({"title_indices": [3, 5, 7]})
    preset.media_type = MediaType.MUSIC
    result = select_tracks("job_x", scan, preset)
    assert sorted(t.index for t in result) == [3, 5, 7]
    assert all(t.kind == TrackKind.AUDIO_TRACK for t in result)
