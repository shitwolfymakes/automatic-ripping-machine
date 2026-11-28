from arm_common import MissTitlesKept, TrackStatus, DiscType, OutputMode, RipPreset, Track, TrackKind, TrackSelection
from arm_common.disc_titles import scan_candidates, track_ref
from arm_common.schemas import ScanResult, ScanTitle, TrackFilters
from arm_common.title_classes import (
    ALTERNATE_CLASSES,
    KEPT_CLASSES,
    MAIN_FEATURE_MIN_SECONDS,
    TitleClass,
    TitleVerdict,
    classify_titles,
)

ALL_TRACKS_MIN_SECONDS = 60


class TrackSelectionError(ValueError):
    pass


def _verdict_columns(verdict: TitleVerdict | None, refs: dict[int, str]) -> tuple[TitleClass | None, str | None]:
    """The track columns (`title_class`, `title_class_ref`) a classifier verdict fills; both NULL
    without one (a DVD, or a title the classifier never saw). `title_class_ref` is the `source_ref`
    of the kept title a copy points at."""
    if verdict is None:
        return None, None
    return verdict.title_class, None if verdict.of_index is None else refs[verdict.of_index]


def _verdict_fields(verdict: TitleVerdict | None, refs: dict[int, str]) -> dict[str, TitleClass | str | None]:
    title_class, title_class_ref = _verdict_columns(verdict, refs)
    return {"title_class": title_class, "title_class_ref": title_class_ref}


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
    scan: ScanResult,
    titles: list[ScanTitle],
    refs: dict[int, str],
    preferred: frozenset[str],
    prefer_stereo_3d: bool | None,
) -> dict[int, TitleVerdict]:
    """Verdicts for every title of a Blu-ray scan; `{}` for any other disc, which
    leaves every title a candidate. `preferred` are title refs; `prefer_stereo_3d`
    is the dimension of a 2D/3D twin pair that stays kept (None: the classifier's
    pick order decides)."""
    if scan.disc_type != DiscType.BLURAY:
        return {}
    preferred_indexes = frozenset(i for i, ref in refs.items() if ref in preferred)
    return classify_titles(
        titles, preferred=preferred_indexes, clip_seconds=_clip_seconds(scan), prefer_stereo_3d=prefer_stereo_3d
    )


def _stand_ins(
    titles: list[ScanTitle],
    verdicts: dict[int, TitleVerdict],
    refs: dict[int, str],
    rippable: frozenset[str],
) -> list[ScanTitle]:
    """For each kept title MakeMKV cannot rip, its first rippable alternate: the
    pick moves only when the pick itself is out."""
    stand_ins: list[ScanTitle] = []
    for kept in (t for t in titles if verdicts[t.index].title_class in KEPT_CLASSES and refs[t.index] not in rippable):
        alternates = [
            t
            for t in titles
            if verdicts[t.index].title_class in ALTERNATE_CLASSES
            and verdicts[t.index].of_index == kept.index
            and refs[t.index] in rippable
        ]
        stand_ins.extend(alternates[:1])
    return stand_ins


def _kept_titles(
    titles: list[ScanTitle],
    verdicts: dict[int, TitleVerdict],
    refs: dict[int, str],
    rippable: frozenset[str] | None,
) -> list[ScanTitle]:
    """The titles the classifier keeps, that MakeMKV can rip; every title when there
    are no verdicts. An unrippable kept title gives way to its first rippable alternate."""
    kept = titles if not verdicts else [t for t in titles if verdicts[t.index].title_class in KEPT_CLASSES]
    if rippable is None:
        return kept
    stand_ins = _stand_ins(titles, verdicts, refs, rippable) if verdicts else []
    return _by_index([t for t in kept if refs[t.index] in rippable], stand_ins)


def _alternate_titles(
    titles: list[ScanTitle],
    verdicts: dict[int, TitleVerdict],
    refs: dict[int, str],
    rippable: frozenset[str] | None,
) -> list[ScanTitle]:
    """The rippable titles that are another version of a kept title."""
    return [
        t
        for t in titles
        if verdicts.get(t.index) is not None
        and verdicts[t.index].title_class in ALTERNATE_CLASSES
        and (rippable is None or refs[t.index] in rippable)
    ]


def _main_feature(candidates: list[ScanTitle], verdicts: dict[int, TitleVerdict]) -> list[ScanTitle]:
    """Every edition of a multi-edition disc; else the longest candidate of at
    least MAIN_FEATURE_MIN_SECONDS, or the longest of all when none is that long."""
    edition_indices = {i for i, v in verdicts.items() if v.title_class == TitleClass.EDITION}
    editions = [t for t in candidates if t.index in edition_indices]
    if editions or not candidates:
        return editions
    eligible = [t for t in candidates if t.duration_seconds >= MAIN_FEATURE_MIN_SECONDS]
    return [max(eligible or candidates, key=lambda t: t.duration_seconds)]


def _family(title: ScanTitle, verdicts: dict[int, TitleVerdict]) -> int:
    """The index of the kept title a version set is built around: the title itself, or what it is an alternate of."""
    verdict = verdicts.get(title.index)
    if verdict is None or verdict.of_index is None or verdict.title_class not in ALTERNATE_CLASSES:
        return title.index
    return verdict.of_index


def _by_index(*groups: list[ScanTitle]) -> list[ScanTitle]:
    """The titles of every group once each, in index order."""
    return sorted({t.index: t for group in groups for t in group}.values(), key=lambda t: t.index)


def _with_versions(
    picked: list[ScanTitle], alternates: list[ScanTitle], verdicts: dict[int, TitleVerdict]
) -> list[ScanTitle]:
    """`picked` plus every alternate that is another version of the same kept title."""
    families = {_family(t, verdicts) for t in picked}
    return _by_index(picked, [t for t in alternates if verdicts[t.index].of_index in families])


def _custom_pool(titles: list[ScanTitle], candidates: list[ScanTitle], filters: TrackFilters) -> list[ScanTitle]:
    """An operator allowlist picks from every title, classification ignored;
    without one the filters run over the classifier's candidates."""
    return titles if filters.title_indices is not None else candidates


def _video_candidates(
    titles: list[ScanTitle],
    verdicts: dict[int, TitleVerdict],
    refs: dict[int, str],
    rippable: frozenset[str] | None,
    tick_one_version: bool,
) -> tuple[list[ScanTitle], list[ScanTitle]]:
    """(the titles a selection rule may take, the alternates of kept titles it may add
    when every version is ticked). A job with one version per film adds none."""
    kept = _kept_titles(titles, verdicts, refs, rippable)
    alternates = [] if tick_one_version else _alternate_titles(titles, verdicts, refs, rippable)
    return kept, alternates


def _select_video(
    scan: ScanResult,
    rip_preset: RipPreset,
    job_id: str,
    preferred: frozenset[str],
    rippable: frozenset[str] | None,
    tick_one_version: bool,
    prefer_stereo_3d: bool | None,
) -> list[Track]:
    titles = scan_candidates(scan)
    if not titles:
        return []
    refs = {t.index: track_ref(scan, t) for t in titles}
    verdicts = _classify(scan, titles, refs, preferred, prefer_stereo_3d)
    kept, alternates = _video_candidates(titles, verdicts, refs, rippable, tick_one_version)
    candidates = _by_index(kept, alternates)
    rule = rip_preset.track_selection
    if rule == TrackSelection.MAIN_FEATURE:
        picked = _with_versions(_main_feature(kept, verdicts), alternates, verdicts)
        return [_video_track(job_id, t, verdicts, refs) for t in picked]
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
    tick_one_version: bool = True,
    prefer_stereo_3d: bool | None = None,
) -> list[Track]:
    """Apply rip-preset track-selection rules to a scan. `preferred` are the
    title refs a metadata source calls the main feature; the classifier uses
    them to break ties between look-alike titles. `rippable`, when given, are
    the only refs a video selection may take (the ones MakeMKV can rip).
    `tick_one_version` takes one title per version set (plus every edition);
    False also takes the alternates (angles, copies, the other dimension),
    never duplicates or decoys. `prefer_stereo_3d` is the dimension of a 2D/3D
    twin pair that counts as the pick (None: the classifier's order decides)."""
    whole = _whole_disc_tracks(job_id, scan, rip_preset)
    if whole is not None:
        return whole
    if scan.disc_type in (DiscType.DVD, DiscType.BLURAY):
        return _select_video(scan, rip_preset, job_id, preferred, rippable, tick_one_version, prefer_stereo_3d)
    if scan.disc_type == DiscType.CD:
        return _select_audio(scan, rip_preset, job_id)
    raise TrackSelectionError(f"cannot select tracks for disc_type={scan.disc_type}")


def title_classes(
    scan: ScanResult, *, preferred: frozenset[str] = frozenset(), prefer_stereo_3d: bool | None = None
) -> dict[str, tuple[TitleClass | None, str | None]]:
    """`source_ref` -> the track columns (`title_class`, `title_class_ref`) the classifier gives
    each scanned title; both None for a disc with no classifier verdicts."""
    titles = scan_candidates(scan)
    refs = {t.index: track_ref(scan, t) for t in titles}
    verdicts = _classify(scan, titles, refs, preferred, prefer_stereo_3d)
    return {refs[t.index]: _verdict_columns(verdicts.get(t.index), refs) for t in titles}


def preset_ticks(
    scan: ScanResult,
    rip_preset: RipPreset,
    *,
    preferred: frozenset[str] = frozenset(),
    rippable: frozenset[str] | None = None,
    tick_one_version: bool = True,
    prefer_stereo_3d: bool | None = None,
) -> frozenset[str] | None:
    """The `source_ref`s the preset ticks for this scan and policy; None when the
    preset takes the disc whole and there is no per-title tick to compute."""
    if _whole_disc_tracks("", scan, rip_preset) is not None:
        return None
    tracks = select_tracks(
        "",
        scan,
        rip_preset,
        preferred=preferred,
        rippable=rippable,
        tick_one_version=tick_one_version,
        prefer_stereo_3d=prefer_stereo_3d,
    )
    return frozenset(t.source_ref for t in tracks)


def select_tracks_for_review(
    job_id: str,
    scan: ScanResult,
    rip_preset: RipPreset,
    *,
    preferred: frozenset[str] = frozenset(),
    rippable: frozenset[str] | None = None,
    tick_one_version: bool = True,
    prefer_stereo_3d: bool | None = None,
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

    kept_refs = preset_ticks(
        scan,
        rip_preset,
        preferred=preferred,
        rippable=rippable,
        tick_one_version=tick_one_version,
        prefer_stereo_3d=prefer_stereo_3d,
    )
    rows = _title_tracks(job_id, scan, preferred, prefer_stereo_3d)
    for track in rows:
        track.excluded = track.source_ref not in (kept_refs or frozenset())
    return rows


def select_rip_tracks(
    job_id: str,
    scan: ScanResult,
    rip_preset: RipPreset,
    *,
    preferred: frozenset[str] = frozenset(),
    rippable: frozenset[str] | None = None,
    tick_one_version: bool = True,
    prefer_stereo_3d: bool | None = None,
) -> list[Track]:
    """The tracks rip-start stores for a disc no review has persisted yet.

    A DVD or Blu-ray stores every scanned title, the preset's rejects marked
    `excluded`: the ripper's one `makemkvcon mkv … all` writes a file for each
    title over the minimum length and pairs those files with the tracks by
    position, so it needs every title to credit each file correctly. A CD
    stores only the selection, because abcde rips exactly the tracks it is given.
    """
    select = select_tracks_for_review if scan.disc_type in (DiscType.DVD, DiscType.BLURAY) else select_tracks
    return select(
        job_id,
        scan,
        rip_preset,
        preferred=preferred,
        rippable=rippable,
        tick_one_version=tick_one_version,
        prefer_stereo_3d=prefer_stereo_3d,
    )


def _title_tracks(
    job_id: str, scan: ScanResult, preferred: frozenset[str], prefer_stereo_3d: bool | None
) -> list[Track]:
    """One Track per scanned title: audio for a CD, video otherwise, each video title labelled with its class."""
    titles = scan_candidates(scan)
    refs = {t.index: track_ref(scan, t) for t in titles}
    if scan.disc_type == DiscType.CD:
        return [_audio_track(job_id, title) for title in titles]
    verdicts = _classify(scan, titles, refs, preferred, prefer_stereo_3d)
    return [_video_track(job_id, title, verdicts, refs) for title in titles]


def select_tracks_on_miss(
    job_id: str,
    scan: ScanResult,
    rip_preset: RipPreset,
    titles_kept: MissTitlesKept,
    *,
    preferred: frozenset[str] = frozenset(),
    tick_one_version: bool = True,
    prefer_stereo_3d: bool | None = None,
) -> list[Track]:
    """Tracks for a disc that missed identification. `ALL` keeps every scanned
    title; `PRESET` keeps what the preset would, as the review gate does. A
    preset that takes the disc whole yields its single whole-disc track either way."""
    if titles_kept == MissTitlesKept.PRESET:
        return select_tracks_for_review(
            job_id,
            scan,
            rip_preset,
            preferred=preferred,
            tick_one_version=tick_one_version,
            prefer_stereo_3d=prefer_stereo_3d,
        )
    whole = _whole_disc_tracks(job_id, scan, rip_preset)
    if whole is not None:
        return whole
    return _title_tracks(job_id, scan, preferred, prefer_stereo_3d)
