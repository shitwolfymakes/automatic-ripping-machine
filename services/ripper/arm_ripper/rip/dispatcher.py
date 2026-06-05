import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from arm_common import DiscType
from arm_common.schemas import TrackView

from arm_ripper.rip.abcde_rip import rip_cd
from arm_ripper.rip.data_rip import rip_data
from arm_ripper.rip.makemkv_rip import RipResult, _output_files_in_rip_order, rip_disc

logger = logging.getLogger("arm_ripper.rip.dispatcher")

OnTrackStart = Callable[[TrackView], Awaitable[None]]
OnTrackDone = Callable[[TrackView, RipResult], Awaitable[None]]
OnTrackProgress = Callable[[TrackView, float], Awaitable[None]]

# v3 default. 120s drops menu loops and vendor bumpers without cutting
# the 2–5 minute extras users typically care about. Sessions can
# override per-rip via `Session.overrides_json["min_length_seconds"]`.
DEFAULT_MIN_LENGTH_SECONDS = 120


async def rip_all(
    disc_type: DiscType,
    device_path: str,
    tracks: list[TrackView],
    output_dir: Path,
    on_track_start: OnTrackStart,
    on_track_done: OnTrackDone,
    on_track_progress: OnTrackProgress | None = None,
    min_length_seconds: int = DEFAULT_MIN_LENGTH_SECONDS,
) -> None:
    """Rip every track in `tracks` and invoke the lifecycle callbacks.

    Per disc_type:
    - DVD / BD: one `makemkvcon mkv ... all` invocation for the whole
      disc; per-title outcomes attributed from the robot stream and
      the produced files. Drive stays open the whole time — no gaps
      where USB autosuspend can drop the device. Selected titles get
      DONE/FAILED based on whether MakeMKV produced their file. Titles
      below `min_length_seconds` are skipped by MakeMKV; if the user
      requested one of those, we report FAILED with a clear reason
      rather than silently ignoring it.
    - CD: mark all tracks IN_PROGRESS, run abcde once for the whole disc,
      then emit DONE/FAILED per track from the bulk result.
    - DATA: a single dd dump assigned to the first (only) track.
    """
    if disc_type in (DiscType.DVD, DiscType.BLURAY):
        await _rip_optical(
            device_path=device_path,
            tracks=tracks,
            output_dir=output_dir,
            on_track_start=on_track_start,
            on_track_done=on_track_done,
            on_track_progress=on_track_progress,
            min_length_seconds=min_length_seconds,
        )
        return

    if disc_type == DiscType.CD:
        for track in tracks:
            await on_track_start(track)
        track_by_index = {t.index: t for t in tracks}

        async def _cd_on_track_done(idx: int, result: RipResult) -> None:
            track = track_by_index.get(idx)
            if track is None:
                return
            await on_track_done(track, result)

        results = await rip_cd(
            device_path=device_path,
            output_dir=output_dir,
            track_indexes=[t.index for t in tracks],
            on_track_done=_cd_on_track_done,
        )
        # Defensive: rip_cd's contract is to fire on_track_done for every
        # track index it's given, so this loop is a no-op on the happy
        # path. It only catches a track that fell through (e.g. a code
        # path inside rip_cd that returned without firing the callback)
        # so the row doesn't stay IN_PROGRESS forever.
        for track in tracks:
            if track.index not in results:
                await on_track_done(
                    track,
                    RipResult(ok=False, error=f"abcde produced no entry for track {track.index}"),
                )
        return

    if disc_type == DiscType.DATA:
        if not tracks:
            return
        first = tracks[0]
        await on_track_start(first)
        result = await rip_data(device_path=device_path, output_dir=output_dir)
        await on_track_done(first, result)
        return

    for track in tracks:
        await on_track_done(
            track,
            RipResult(ok=False, error=f"no rip path for disc_type={disc_type.value}"),
        )


async def _rip_optical(
    *,
    device_path: str,
    tracks: list[TrackView],
    output_dir: Path,
    on_track_start: OnTrackStart,
    on_track_done: OnTrackDone,
    on_track_progress: OnTrackProgress | None,
    min_length_seconds: int,
) -> None:
    """Single-invocation DVD/BD rip with per-title attribution.

    The makemkvcon invocation rips every title ≥ minlength to
    `output_dir`. We map title_index → TrackView via `source_ref` and
    fan the lifecycle callbacks out as MakeMKV's stream announces each
    title. Tracks whose `source_ref` doesn't parse as an int are
    failed up front — same shape as the per-title implementation.

    Lifecycle correctness: the backend's track state machine requires
    `queued → in_progress → done|failed`. PRGT-driven `on_track_start`
    is best-effort — empirically MakeMKV in `mkv all` mode emits a
    single overall "Saving all titles to MKV files" PRGT rather than
    per-title milestones, so `_on_title_start` may never fire even on
    a healthy rip. We track which tracks already had `on_track_start`
    called via the stream, then synthesise it from the post-rip
    attribution for any track that didn't — so PATCH `done` / `failed`
    always lands on a row in `in_progress`.
    """
    # Pre-compute source_ref → track lookup so the rip-side callbacks
    # are O(1). Skip and pre-fail tracks with malformed source_ref.
    track_by_index: dict[int, TrackView] = {}
    for track in tracks:
        try:
            idx = int(track.source_ref)
        except ValueError:
            # No need to fire on_track_start for an invalid-source_ref
            # track — the backend rejects the track entirely via the
            # FAILED-from-QUEUED guard. Falling through to on_track_done
            # is consistent with how the per-title implementation handled
            # it, and the upstream patch_with_retry catches the 409 if
            # it ever shows up here.
            await on_track_done(
                track,
                RipResult(ok=False, error=f"invalid source_ref: {track.source_ref!r}"),
            )
            continue
        track_by_index[idx] = track

    if not track_by_index:
        return

    # Eligible source indexes — those whose duration meets `--minlength`,
    # sorted ascending. MakeMKV's `mkv all` output files carry an
    # output-position suffix (`_t00`, `_t01`, ...) rather than the
    # source title index, so we pair this list positionally with the
    # files post-rip to get attribution back. Tracks with no
    # `duration_seconds` (rare — scan didn't find one) are treated as
    # eligible to avoid dropping them silently; if MakeMKV skips them,
    # they fall through to "produced no .mkv" downstream.
    eligible_source_indexes = sorted(
        idx
        for idx, t in track_by_index.items()
        if t.duration_seconds is None or t.duration_seconds >= min_length_seconds
    )

    started: set[int] = set()
    # Source indexes whose Track has already been PATCHed DONE via the
    # streamer's mid-rip on_title_done callback. The post-rip
    # attribution loop skips these to avoid double-PATCHing.
    done_emitted: set[int] = set()

    async def _on_title_start(title_idx: int) -> None:
        track = track_by_index.get(title_idx)
        if track is None:
            # MakeMKV announced a title we didn't select (e.g. user
            # picked TRACKS mode but rip_disc rips all ≥ minlength).
            return
        if title_idx in started:
            return
        started.add(title_idx)
        await on_track_start(track)

    async def _on_title_progress(title_idx: int, fraction: float) -> None:
        if on_track_progress is None:
            return
        track = track_by_index.get(title_idx)
        if track is None:
            return
        await on_track_progress(track, fraction)

    async def _on_disc_progress(fraction: float) -> None:
        """Disc-overall PRGV fallback for `mkv all`.

        MakeMKV in `mkv all` mode emits no per-title PRGT, so the
        streamer's `current_title` stays None and no `_on_title_progress`
        ever fires. Without this fallback the dashboard bar would stay
        at 0 % for the whole rip even though the file is being written.

        We attribute disc-level progress to the first eligible track —
        the WS payload requires a track_id, but the UI's rips store
        keys live progress by `job_id` and only ever displays a single
        bar per disc (see [services/ui/src/components/JobCard.vue]),
        so the choice of track_id is purely a wire-format detail. The
        bar fills smoothly 0→100 % across the whole rip via the PRGV
        `total/max` channel. Per-title attribution still happens
        post-rip in the attribution loop below.
        """
        if on_track_progress is None or not eligible_source_indexes:
            return
        first_track = track_by_index.get(eligible_source_indexes[0])
        if first_track is None:
            return
        await on_track_progress(first_track, fraction)

    async def _on_title_done(title_idx: int) -> None:
        """Mid-rip per-title finalisation. Stat the .mkv produced for
        this title's output position and PATCH the Track DONE with
        size + output_path. SHA256 is intentionally skipped here —
        hashing a 27 GB main feature would block the streamer for a
        minute and starve the next title's PRGC of attention; if the
        column is needed it can be filled in by a separate post-rip
        pass.

        Files are matched positionally to `eligible_source_indexes`
        (same convention as the post-rip attribution loop): the file
        whose `_tNN.mkv` suffix equals this title's position in the
        eligible list is the one MakeMKV just finalised.
        """
        track = track_by_index.get(title_idx)
        if track is None:
            return
        if title_idx in done_emitted:
            return
        try:
            position = eligible_source_indexes.index(title_idx)
        except ValueError:
            # MakeMKV announced a title we didn't list as eligible —
            # nothing to attribute live; the post-rip loop handles it.
            return
        files = _output_files_in_rip_order(output_dir)
        if position >= len(files):
            # File not on disk yet — defer to the post-rip loop. Should
            # be rare: MakeMKV finalises before emitting the next PRGC.
            logger.debug(
                "on_title_done: file for source_idx=%d position=%d not on disk yet; deferring",
                title_idx,
                position,
            )
            return
        file_path = files[position]
        try:
            size = file_path.stat().st_size
        except OSError as exc:
            logger.warning(
                "on_title_done: stat failed source_idx=%d path=%s err=%s",
                title_idx,
                file_path,
                exc,
            )
            return
        await _ensure_started(title_idx, track)
        result = RipResult(
            ok=True,
            output_path=file_path,
            size_bytes=size,
            duration_seconds=track.duration_seconds or track.expected_duration_seconds,
        )
        done_emitted.add(title_idx)
        await on_track_done(track, result)

    async def _ensure_started(title_idx: int, track: TrackView) -> None:
        """Guarantee on_track_start has fired for this track before any
        terminal PATCH. In `mkv all` mode the stream-driven PRGT often
        doesn't fire, so this synthesises the QUEUED → IN_PROGRESS
        transition from the post-rip attribution loop."""
        if title_idx in started:
            return
        started.add(title_idx)
        await on_track_start(track)

    disc_result = await rip_disc(
        device_path=device_path,
        output_dir=output_dir,
        minlength_seconds=min_length_seconds,
        eligible_source_indexes=eligible_source_indexes,
        on_title_start=_on_title_start,
        on_title_progress=_on_title_progress,
        on_disc_progress=_on_disc_progress,
        on_title_done=_on_title_done,
    )

    if disc_result.overall_error is not None:
        # Rip-level failure — mark every selected track FAILED with the
        # disc-level error so the operator knows what happened. Each
        # track must transit IN_PROGRESS first per the backend's state
        # machine. Tracks already PATCHed DONE via the live path
        # (titles that finalised before the rip aborted) keep their
        # DONE status — partial success is still success for those
        # files.
        logger.warning("rip_disc failed: %s", disc_result.overall_error)
        for title_idx, track in track_by_index.items():
            if title_idx in done_emitted:
                continue
            await _ensure_started(title_idx, track)
            await on_track_done(track, RipResult(ok=False, error=disc_result.overall_error))
        return

    # Per-title attribution for tracks the live path didn't already
    # finalise (e.g. below-minlength tracks MakeMKV skipped, or
    # eligible tracks that didn't produce a file). Tracks already in
    # `done_emitted` were PATCHed DONE by `_on_title_done` mid-rip and
    # are skipped here to avoid double-PATCHing.
    # - If rip_disc reports a result for it: use that. (Includes
    #   ok=False for eligible titles that didn't render — the live
    #   path can't report failures since it's only triggered by PRGC
    #   transitions on successful saves.)
    # - Otherwise: the track was below `min_length_seconds`, so MakeMKV
    #   never attempted it. FAILED with a clear reason so the operator
    #   can lower minlength and retry.
    for title_idx, track in track_by_index.items():
        if title_idx in done_emitted:
            continue
        await _ensure_started(title_idx, track)
        result = disc_result.titles.get(title_idx)
        if result is None:
            duration = track.duration_seconds
            if duration is not None and duration < min_length_seconds:
                err = f"track duration {duration}s below minlength={min_length_seconds}s; makemkvcon skipped it"
            else:
                err = (
                    f"makemkvcon produced no output for title {title_idx} "
                    f"(eligible={title_idx in eligible_source_indexes})"
                )
            await on_track_done(track, RipResult(ok=False, error=err))
            continue
        # Carry duration_seconds through from the scan when MakeMKV
        # produced the file successfully. rip_disc doesn't measure
        # durations from the .mkv files, so we forward the scan-time
        # estimate. `track.duration_seconds` is the post-rip actual
        # (null until a previous rip set it — usually null here);
        # `track.expected_duration_seconds` is the scan-time estimate
        # populated by `select_tracks` at rip-start.
        if result.ok and result.duration_seconds is None:
            result = RipResult(
                ok=True,
                output_path=result.output_path,
                size_bytes=result.size_bytes,
                duration_seconds=track.duration_seconds or track.expected_duration_seconds,
                sha256=result.sha256,
            )
        await on_track_done(track, result)
