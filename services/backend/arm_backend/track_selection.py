from arm_common import TrackStatus, DiscType, OutputMode, RipPreset, Track, TrackKind, TrackSelection
from arm_common.disc_titles import scan_candidates, track_ref
from arm_common.schemas import ScanResult, ScanTitle, TrackFilters
from arm_common.title_classes import KEPT_CLASSES, MAIN_FEATURE_MIN_SECONDS, TitleClass, TitleVerdict, classify_titles

ALL_TRACKS_MIN_SECONDS = 60


class TrackSelectionError(ValueError):
    pass


def _verdict_fields(verdict: TitleVerdict | None, refs: dict[int, str]) -> dict[str, TitleClass | str | None]:
    """The track columns a classifier verdict fills; all NULL without one (a
    DVD, or a title the classifier never saw). `title_class_ref` is the
    `source_ref` of the kept title a copy points at."""
    if verdict is None:
        return {"title_class": None, "title_class_ref": None}
    ref = None if verdict.of_index is None else refs[verdict.of_index]
    return {"title_class": verdict.title_class, "title_class_ref": ref}


def _video_track(job_id: str, title: ScanTitle, verdicts: dict[int, TitleVerdict], refs: dict[int, str]) -> Track:
    return Track(
        job_id=job_id,
        kind=TrackKind.VIDEO_TITLE,
        index=title.index,
        source_ref=refs[title.index],
        expected_duration_seconds=title.duration_seconds,
        expected_size_bytes=title.size_bytes,
        source_file=title.source_file,
        playlist_name=title.playlist_name,
        **_verdict_fields(verdicts.get(title.index), refs),
    )


def _audio_track(job_id: str, title: ScanTitle) -> Track:
    return Track(
        job_id=job_id,
        kind=TrackKind.AUDIO_TRACK,
        index=title.index,
        source_ref=str(title.index),
        expected_duration_seconds=title.duration_seconds,
        expected_size_bytes=title.size_bytes,
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


def _clip_seconds(scan: ScanResult) -> dict[int, float]:
    """Seconds each clip plays, merged over every playlist and keyed by clip
    number. A clip in several playlists takes the first playlist's value (disc
    order). A playlist whose `clips` and `clip_seconds` lengths differ is
    skipped whole, as its pairing cannot be trusted."""
    merged: dict[int, float] = {}
    for playlist in scan.playlists:
        if len(playlist.clips) != len(playlist.clip_seconds):
            continue
        for clip, seconds in zip(playlist.clips, playlist.clip_seconds):
            merged.setdefault(clip, seconds)
    return merged


def _classify(
    scan: ScanResult, titles: list[ScanTitle], refs: dict[int, str], preferred: frozenset[str]
) -> dict[int, TitleVerdict]:
    """Verdicts for every title of a Blu-ray scan; `{}` for any other disc, which
    leaves every title a candidate. `preferred` are title refs."""
    if scan.disc_type != DiscType.BLURAY:
        return {}
    preferred_indexes = frozenset(i for i, ref in refs.items() if ref in preferred)
    return classify_titles(titles, preferred=preferred_indexes, clip_seconds=_clip_seconds(scan))


def _kept_titles(titles: list[ScanTitle], verdicts: dict[int, TitleVerdict]) -> list[ScanTitle]:
    """The titles the classifier keeps; all of them when there are no verdicts."""
    if not verdicts:
        return titles
    return [t for t in titles if verdicts[t.index].title_class in KEPT_CLASSES]


def _main_feature(candidates: list[ScanTitle], verdicts: dict[int, TitleVerdict]) -> list[ScanTitle]:
    """Every edition of a multi-edition disc; else the longest candidate of at
    least MAIN_FEATURE_MIN_SECONDS, or the longest of all when none is that long."""
    edition_indices = {i for i, v in verdicts.items() if v.title_class == TitleClass.EDITION}
    editions = [t for t in candidates if t.index in edition_indices]
    if editions:
        return editions
    eligible = [t for t in candidates if t.duration_seconds >= MAIN_FEATURE_MIN_SECONDS]
    return [max(eligible or candidates, key=lambda t: t.duration_seconds)]


def _custom_pool(titles: list[ScanTitle], candidates: list[ScanTitle], filters: TrackFilters) -> list[ScanTitle]:
    """An operator allowlist picks from every title, classification ignored;
    without one the filters run over the classifier's candidates."""
    return titles if filters.title_indices is not None else candidates


def _select_video(
    scan: ScanResult,
    rip_preset: RipPreset,
    job_id: str,
    preferred: frozenset[str],
    rippable: frozenset[str] | None,
) -> list[Track]:
    titles = scan_candidates(scan)
    if not titles:
        return []
    refs = {t.index: track_ref(scan, t) for t in titles}
    verdicts = _classify(scan, titles, refs, preferred)
    candidates = _kept_titles(titles, verdicts)
    if rippable is not None:
        candidates = [t for t in candidates if refs[t.index] in rippable]
    rule = rip_preset.track_selection
    if rule == TrackSelection.MAIN_FEATURE:
        return [_video_track(job_id, t, verdicts, refs) for t in _main_feature(candidates, verdicts)]
    if rule == TrackSelection.ALL_TRACKS:
        return [
            _video_track(job_id, t, verdicts, refs) for t in candidates if t.duration_seconds >= ALL_TRACKS_MIN_SECONDS
        ]
    if rule == TrackSelection.ARCHIVE:
        return [_video_track(job_id, t, verdicts, refs) for t in candidates]
    if rule == TrackSelection.CUSTOM:
        filters = _parse_filters(rip_preset)
        return [
            _video_track(job_id, t, verdicts, refs)
            for t in _apply_custom_filters(_custom_pool(titles, candidates, filters), filters)
        ]
    # Unreachable: TrackSelection enum is exhaustively handled above.
    raise TrackSelectionError(f"unknown track_selection: {rule}")  # pragma: no cover


def _select_audio(scan: ScanResult, rip_preset: RipPreset, job_id: str) -> list[Track]:
    rule = rip_preset.track_selection
    if rule == TrackSelection.CUSTOM:
        filters = _parse_filters(rip_preset)
        return [_audio_track(job_id, t) for t in _apply_custom_filters(scan.titles, filters)]
    return [_audio_track(job_id, t) for t in scan.titles]


class DiscBackupNeedsBluray(TrackSelectionError):
    """A FOLDER (decrypted backup) preset was applied to a disc that is not a Blu-ray."""


def _whole_disc_track(job_id: str, kind: TrackKind) -> Track:
    return Track(
        job_id=job_id,
        kind=kind,
        index=0,
        source_ref="full",
        status=TrackStatus.QUEUED,
        attempts=0,
    )


def _dumps_whole_disc(scan: ScanResult, rip_preset: RipPreset) -> bool:
    """A DATA disc has no titles, and an ISO preset copies a DVD or Blu-ray
    whole whatever titles the scan found: both are one full-disc dump."""
    if scan.disc_type == DiscType.DATA:
        return True
    return rip_preset.output_mode == OutputMode.ISO and scan.disc_type in (DiscType.DVD, DiscType.BLURAY)


def _whole_disc_tracks(job_id: str, scan: ScanResult, rip_preset: RipPreset) -> list[Track] | None:
    """The single track for a preset that takes the disc whole, or None when
    the preset selects titles. A FOLDER preset backs up a Blu-ray and refuses
    any other disc."""
    if rip_preset.output_mode == OutputMode.FOLDER:
        if scan.disc_type != DiscType.BLURAY:
            raise DiscBackupNeedsBluray(f"disc backup needs a Blu-ray, not disc_type={scan.disc_type.value}")
        return [_whole_disc_track(job_id, TrackKind.DISC_BACKUP)]
    if _dumps_whole_disc(scan, rip_preset):
        return [_whole_disc_track(job_id, TrackKind.DATA_DUMP)]
    return None


def select_tracks(
    job_id: str,
    scan: ScanResult,
    rip_preset: RipPreset,
    *,
    preferred: frozenset[str] = frozenset(),
    rippable: frozenset[str] | None = None,
) -> list[Track]:
    """Apply rip-preset track-selection rules to a scan. `preferred` are the
    title refs a metadata source calls the main feature; the classifier uses
    them to break ties between look-alike titles. `rippable`, when given, are
    the only refs a video selection may take (the ones MakeMKV can rip)."""
    whole = _whole_disc_tracks(job_id, scan, rip_preset)
    if whole is not None:
        return whole
    if scan.disc_type in (DiscType.DVD, DiscType.BLURAY):
        return _select_video(scan, rip_preset, job_id, preferred, rippable)
    if scan.disc_type == DiscType.CD:
        return _select_audio(scan, rip_preset, job_id)
    raise TrackSelectionError(f"cannot select tracks for disc_type={scan.disc_type}")


def select_tracks_for_review(
    job_id: str, scan: ScanResult, rip_preset: RipPreset, *, preferred: frozenset[str] = frozenset()
) -> list[Track]:
    """Persist EVERY scanned title as a Track for the timed review gate, marking
    preset-rejected titles `excluded=True` (the default keep/drop set) so the
    review UI shows the full title list and the operator can re-enable any.

    Differs from `select_tracks` (which returns only the preset's subset): here
    the preset computes *defaults*, not membership. The kept set is whatever
    `select_tracks` would have produced, matched by `source_ref`.

    A whole-disc track (a DATA disc, the ISO dump, the FOLDER backup) has no
    per-title list: review persistence is the single track `select_tracks` makes.
    """
    whole = _whole_disc_tracks(job_id, scan, rip_preset)
    if whole is not None:
        return whole

    kept_refs = {t.source_ref for t in select_tracks(job_id, scan, rip_preset, preferred=preferred)}
    titles = scan_candidates(scan)
    refs = {t.index: track_ref(scan, t) for t in titles}
    is_cd = scan.disc_type == DiscType.CD
    verdicts = _classify(scan, titles, refs, preferred)
    rows: list[Track] = []
    for title in titles:
        track = _audio_track(job_id, title) if is_cd else _video_track(job_id, title, verdicts, refs)
        track.excluded = refs[title.index] not in kept_refs
        rows.append(track)
    return rows
