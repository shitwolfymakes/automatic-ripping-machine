from arm_common import DiscType, RipPreset, Track, TrackKind, TrackSelection
from arm_common.schemas import ScanResult, ScanTitle, TrackFilters

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


def _parse_filters(rip_preset: RipPreset) -> TrackFilters:
    """Materialise `track_filters_json` as a typed `TrackFilters`.

    Raises if the preset says CUSTOM but has no filters configured — that
    combination is a save-time bug we surface loudly rather than silently
    selecting nothing.
    """
    if rip_preset.track_filters_json is None:
        raise TrackSelectionError(
            f"rip_preset {rip_preset.id} declares CUSTOM track_selection but has no track_filters_json"
        )
    return TrackFilters.model_validate(rip_preset.track_filters_json)


def _apply_custom_filters(titles: list[ScanTitle], filters: TrackFilters) -> list[ScanTitle]:
    """AND-of-conditions filter. `title_indices` (allowlist) restricts first; min/max + exclude apply after."""
    candidates = titles
    if filters.title_indices is not None:
        allow = set(filters.title_indices)
        candidates = [t for t in candidates if t.index in allow]
    if filters.title_indices_exclude is not None:
        deny = set(filters.title_indices_exclude)
        candidates = [t for t in candidates if t.index not in deny]
    if filters.min_duration_seconds is not None:
        threshold = filters.min_duration_seconds
        candidates = [t for t in candidates if t.duration_seconds >= threshold]
    if filters.max_duration_seconds is not None:
        ceiling = filters.max_duration_seconds
        candidates = [t for t in candidates if t.duration_seconds <= ceiling]
    return candidates


def _select_video(scan: ScanResult, rip_preset: RipPreset, job_id: str) -> list[Track]:
    titles = scan.titles
    if not titles:
        return []
    rule = rip_preset.track_selection
    if rule == TrackSelection.MAIN_FEATURE:
        eligible = [t for t in titles if t.duration_seconds >= MAIN_FEATURE_MIN_SECONDS]
        chosen = max(eligible or titles, key=lambda t: t.duration_seconds)
        return [_video_track(job_id, chosen)]
    if rule == TrackSelection.ALL_TRACKS:
        return [_video_track(job_id, t) for t in titles if t.duration_seconds >= ALL_TRACKS_MIN_SECONDS]
    if rule == TrackSelection.ARCHIVE:
        return [_video_track(job_id, t) for t in titles]
    if rule == TrackSelection.CUSTOM:
        filters = _parse_filters(rip_preset)
        return [_video_track(job_id, t) for t in _apply_custom_filters(titles, filters)]
    raise TrackSelectionError(f"unknown track_selection: {rule}")


def _select_audio(scan: ScanResult, rip_preset: RipPreset, job_id: str) -> list[Track]:
    rule = rip_preset.track_selection
    if rule == TrackSelection.CUSTOM:
        filters = _parse_filters(rip_preset)
        return [_audio_track(job_id, t) for t in _apply_custom_filters(scan.titles, filters)]
    return [_audio_track(job_id, t) for t in scan.titles]


def select_tracks(job_id: str, scan: ScanResult, rip_preset: RipPreset) -> list[Track]:
    """Apply rip-preset track-selection rules to a scan."""
    if scan.disc_type in (DiscType.DVD, DiscType.BLURAY):
        return _select_video(scan, rip_preset, job_id)
    if scan.disc_type == DiscType.CD:
        return _select_audio(scan, rip_preset, job_id)
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
