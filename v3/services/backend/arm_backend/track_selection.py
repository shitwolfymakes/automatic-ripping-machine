from arm_common import DiscType, RipPreset, Track, TrackKind, TrackSelection
from arm_common.schemas import ScanResult, ScanTitle

MAIN_FEATURE_MIN_SECONDS = 45 * 60
ALL_TRACKS_MIN_SECONDS = 60


class TrackSelectionError(ValueError):
    pass


def _video_track(job_id: str, title: ScanTitle) -> Track:
    return Track(
        job_id=job_id,
        kind=TrackKind.VIDEO_TITLE,
        index=title.index,
        source_ref=str(title.index),
        expected_duration_seconds=title.duration_seconds,
    )


def _audio_track(job_id: str, title: ScanTitle) -> Track:
    return Track(
        job_id=job_id,
        kind=TrackKind.AUDIO_TRACK,
        index=title.index,
        source_ref=str(title.index),
        expected_duration_seconds=title.duration_seconds,
    )


def _select_video(scan: ScanResult, rule: TrackSelection, job_id: str) -> list[Track]:
    titles = scan.titles
    if not titles:
        return []
    if rule == TrackSelection.MAIN_FEATURE:
        eligible = [t for t in titles if t.duration_seconds >= MAIN_FEATURE_MIN_SECONDS]
        chosen = max(eligible or titles, key=lambda t: t.duration_seconds)
        return [_video_track(job_id, chosen)]
    if rule == TrackSelection.ALL_TRACKS:
        return [_video_track(job_id, t) for t in titles if t.duration_seconds >= ALL_TRACKS_MIN_SECONDS]
    if rule == TrackSelection.ARCHIVE:
        return [_video_track(job_id, t) for t in titles]
    if rule == TrackSelection.CUSTOM:
        raise NotImplementedError("custom track selection deferred to Phase 6")
    raise TrackSelectionError(f"unknown track_selection: {rule}")


def _select_audio(scan: ScanResult, rule: TrackSelection, job_id: str) -> list[Track]:
    if rule == TrackSelection.CUSTOM:
        raise NotImplementedError("custom track selection deferred to Phase 6")
    return [_audio_track(job_id, t) for t in scan.titles]


def select_tracks(job_id: str, scan: ScanResult, rip_preset: RipPreset) -> list[Track]:
    """Apply rip-preset track-selection rules to a scan.

    Phase 3 only handles MAIN_FEATURE / ALL_TRACKS / ARCHIVE for video,
    plus an unconditional all-tracks selection for CD/DATA. CUSTOM is
    deferred to Phase 6.
    """
    if scan.disc_type in (DiscType.DVD, DiscType.BLURAY):
        return _select_video(scan, rip_preset.track_selection, job_id)
    if scan.disc_type == DiscType.CD:
        return _select_audio(scan, rip_preset.track_selection, job_id)
    if scan.disc_type == DiscType.DATA:
        return [
            Track(
                job_id=job_id,
                kind=TrackKind.DATA_DUMP,
                index=0,
                source_ref="full",
            )
        ]
    raise TrackSelectionError(f"cannot select tracks for disc_type={scan.disc_type}")
