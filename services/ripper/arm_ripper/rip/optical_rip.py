"""The DVD and Blu-ray rip: one makemkvcon run for the whole disc, attributed back to the selected tracks."""

import asyncio
import logging
from collections.abc import Callable, Collection
from pathlib import Path

from arm_common.schemas import TrackView

from arm_ripper.rip.makemkv_process import STOPPED_ERROR
from arm_ripper.rip.makemkv_rip import (
    OUTPUT_FILE_RE,
    RipDiscResult,
    output_files_in_rip_order,
    rip_disc,
)
from arm_ripper.rip.result import RipResult
from arm_ripper.rip.title_hasher import OnHashed, TitleHasher
from arm_ripper.rip.track_callbacks import OnTrackDone, OnTrackProgress, OnTrackStart, TransferStats

# Log under the dispatcher's name: these lines have always come from that logger.
logger = logging.getLogger("arm_ripper.rip.dispatcher")


def _index_tracks(
    tracks: list[TrackView], skip_track_ids: Collection[str]
) -> tuple[dict[int, TrackView], list[TrackView]]:
    """Map each track to its source title index; also return, in order, the tracks whose `source_ref` isn't an int
    and that no earlier pass settled, which the caller fails."""
    # Pre-compute source_ref → track lookup so the rip-side callbacks
    # are O(1). Skip tracks already settled; collect malformed ones.
    track_by_index: dict[int, TrackView] = {}
    invalid: list[TrackView] = []
    for track in tracks:
        try:
            idx = int(track.source_ref)
        except ValueError:
            if track.id not in skip_track_ids:
                invalid.append(track)
            continue
        track_by_index[idx] = track
    return track_by_index, invalid


def _eligible_source_indexes(track_by_index: dict[int, TrackView], min_length_seconds: int) -> list[int]:
    """The source indexes MakeMKV will rip, ascending: each track at least `min_length_seconds` long, or of unknown
    length."""
    # Eligible source indexes — those whose duration meets `--minlength`,
    # sorted ascending. MakeMKV's `mkv all` output files carry an
    # output-position suffix (`_t00`, `_t01`, ...) rather than the
    # source title index, so we pair this list positionally with the
    # files post-rip to get attribution back. Tracks with no
    # `duration_seconds` (rare — scan didn't find one) are treated as
    # eligible to avoid dropping them silently; if MakeMKV skips them,
    # they fall through to "produced no .mkv" downstream.
    return sorted(
        idx
        for idx, t in track_by_index.items()
        if t.duration_seconds is None or t.duration_seconds >= min_length_seconds
    )


def _first_eligible_track(track_by_index: dict[int, TrackView], eligible: list[int]) -> TrackView | None:
    """The track for the first eligible title, which carries the disc-level progress; None when nothing is eligible."""
    return track_by_index[eligible[0]] if eligible else None


def _no_output_error(title_idx: int, track: TrackView, min_length_seconds: int, eligible: list[int]) -> str:
    """Why a selected title has no result: MakeMKV skipped it as too short, or it produced nothing for it."""
    duration = track.duration_seconds
    if duration is not None and duration < min_length_seconds:
        return f"track duration {duration}s below minlength={min_length_seconds}s; makemkvcon skipped it"
    return f"makemkvcon produced no output for title {title_idx} (eligible={title_idx in eligible})"


def _finished_file(output_dir: Path, title_idx: int, position: int) -> tuple[Path, int] | None:
    """The file MakeMKV wrote at this output position and its size; None, after logging why, when it isn't on disk
    yet or can't be stat'ed."""
    files = output_files_in_rip_order(output_dir)
    if position >= len(files):
        # File not on disk yet — defer to the post-rip loop. Should
        # be rare: MakeMKV finalises before emitting the next PRGC.
        logger.debug(
            "on_title_done: file for source_idx=%d position=%d not on disk yet; deferring",
            title_idx,
            position,
        )
        return None
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
        return None
    return file_path, size


class _OpticalRip:
    """One single-invocation DVD/BD rip: the per-title callbacks makemkvcon's stream fires, and the attribution after it
    exits."""

    def __init__(
        self,
        *,
        device_path: str,
        output_dir: Path,
        track_by_index: dict[int, TrackView],
        eligible: list[int],
        skipped: set[int],
        on_track_start: OnTrackStart,
        on_track_done: OnTrackDone,
        on_track_progress: OnTrackProgress | None,
        min_length_seconds: int,
        stop: asyncio.Event | None,
        drive_lost: Callable[[], bool] | None,
    ) -> None:
        self._device_path = device_path
        self._output_dir = output_dir
        self._track_by_index = track_by_index
        self._eligible = eligible
        self._skipped = skipped
        self._on_track_start = on_track_start
        self._on_track_done = on_track_done
        self._on_track_progress = on_track_progress
        self._min_length_seconds = min_length_seconds
        self._stop = stop
        self._drive_lost = drive_lost
        self._started: set[int] = set(skipped)
        # Source indexes whose Track has already been PATCHed DONE via the
        # streamer's mid-rip on_title_done callback. The post-rip
        # attribution loop skips these to avoid double-PATCHing.
        self._done_emitted: set[int] = set(skipped)
        self._hasher = TitleHasher()

    def _drive_dropped(self) -> bool:
        """The drive left the bus under this rip. The first time
        `drive_lost` says so, set `stop`, which kills makemkvcon."""
        if self._stop is None:
            return False
        if not self._stop.is_set() and self._drive_lost is not None and self._drive_lost():
            logger.warning("drive dropped off the bus mid-rip; stopping makemkvcon")
            self._stop.set()
        return self._stop.is_set()

    async def _on_title_start(self, title_idx: int) -> None:
        track = self._track_by_index.get(title_idx)
        if track is None:
            # MakeMKV announced a title we didn't select (e.g. user
            # picked TRACKS mode but rip_disc rips all ≥ minlength).
            return
        if title_idx in self._started:
            return
        self._started.add(title_idx)
        await self._on_track_start(track)

    async def _on_title_progress(self, title_idx: int, fraction: float) -> None:
        if self._on_track_progress is None:
            return
        track = self._track_by_index.get(title_idx)
        if track is None:
            return
        await self._on_track_progress(track, fraction)

    async def _on_disc_progress(self, fraction: float) -> None:
        """Disc-overall PRGV fallback for `mkv all`.

        MakeMKV in `mkv all` mode emits no per-title PRGT, so the
        streamer's `current_title` stays None and no `_on_title_progress`
        ever fires. Without this fallback the dashboard bar would stay
        at 0 % for the whole rip even though the file is being written.

        We attribute disc-level progress to the first eligible track —
        the WS payload requires a track_id, but the UI's rips store
        keys live progress by `job_id` and only ever displays a single
        bar per disc (see services/ui-neu/frontend/src/lib/stores/rips.svelte.ts),
        so the choice of track_id is purely a wire-format detail. The
        bar fills smoothly 0→100 % across the whole rip via the PRGV
        `total/max` channel. Per-title attribution still happens
        post-rip in the attribution loop below.
        """
        first_track = _first_eligible_track(self._track_by_index, self._eligible)
        if self._on_track_progress is None or first_track is None:
            return
        await self._on_track_progress(first_track, fraction)

    def _finalise_after_hash(self, track: TrackView, result: RipResult) -> OnHashed:
        async def then(digest: str | None) -> None:
            await self._on_track_done(
                track,
                RipResult(
                    ok=True,
                    output_path=result.output_path,
                    size_bytes=result.size_bytes,
                    duration_seconds=result.duration_seconds,
                    sha256=digest,
                ),
            )

        return then

    async def _on_verify_progress(self, done: int, total: int, rate: float | None) -> None:
        first_track = _first_eligible_track(self._track_by_index, self._eligible)
        if self._on_track_progress is None or first_track is None:
            return
        stats: TransferStats = {"bytes_done": done, "bytes_total": total, "rate_bps": rate, "phase": "verifying"}
        await self._on_track_progress(first_track, min(done / total, 1.0) if total else 0.0, stats)

    async def _on_title_done(self, title_idx: int) -> None:
        """Mid-rip per-title finalisation. Stat the .mkv produced for
        this title's output position and hand it to the background
        hasher, which PATCHes the Track DONE with size, output_path and
        sha256 once the file is hashed. The hash never runs on the
        streamer: a 27 GB main feature would block it for minutes and
        starve the next title's PRGC of attention.

        Files are matched positionally to `eligible_source_indexes`
        (same convention as the post-rip attribution loop): the file
        whose `_tNN.mkv` suffix equals this title's position in the
        eligible list is the one MakeMKV just finalised.
        """
        track = self._track_by_index.get(title_idx)
        if track is None:
            return
        if title_idx in self._done_emitted:
            return
        if self._drive_dropped():
            # makemkvcon moved on because the drive dropped under this title,
            # so its file is cut short. The stopped-rip path below reports it
            # unfinished.
            return
        try:
            position = self._eligible.index(title_idx)
        except ValueError:
            # MakeMKV announced a title we didn't list as eligible —
            # nothing to attribute live; the post-rip loop handles it.
            return
        found = _finished_file(self._output_dir, title_idx, position)
        if found is None:
            return
        file_path, size = found
        await self._ensure_started(title_idx, track)
        result = RipResult(
            ok=True,
            output_path=file_path,
            size_bytes=size,
            duration_seconds=track.duration_seconds or track.expected_duration_seconds,
        )
        self._done_emitted.add(title_idx)
        self._hasher.submit(file_path, size, self._finalise_after_hash(track, result))

    async def _ensure_started(self, title_idx: int, track: TrackView) -> None:
        """Guarantee on_track_start has fired for this track before any
        terminal PATCH. In `mkv all` mode the stream-driven PRGT often
        doesn't fire, so this synthesises the QUEUED → IN_PROGRESS
        transition from the post-rip attribution loop."""
        if title_idx in self._started:
            return
        self._started.add(title_idx)
        await self._on_track_start(track)

    async def run(self) -> None:
        """Run makemkvcon once, then report every selected track exactly once."""
        try:
            disc_result = await rip_disc(
                device_path=self._device_path,
                output_dir=self._output_dir,
                minlength_seconds=self._min_length_seconds,
                eligible_source_indexes=self._eligible,
                on_title_start=self._on_title_start,
                on_title_progress=self._on_title_progress,
                on_disc_progress=self._on_disc_progress,
                on_title_done=self._on_title_done,
                hash_outputs=False,
                stop=self._stop,
            )
            _delete_skipped_outputs(self._output_dir, self._eligible, self._skipped)
            if disc_result.overall_error is None and self._drive_dropped():
                # makemkvcon exited on its own after the drive dropped: a title
                # not finalised above may be cut short, so none of them count.
                disc_result = RipDiscResult(overall_error=STOPPED_ERROR, titles={})

            if disc_result.overall_error is not None:
                await self._fail_unfinished(disc_result.overall_error)
                return

            await self._attribute(disc_result)

            await self._hasher.finish(self._on_verify_progress)
        except BaseException:
            # Abandoned mid-rip (CancelledError) or a PATCH that gave up: stop
            # hashing files that are about to be wiped.
            self._hasher.cancel()
            raise

    async def _attribute(self, disc_result: RipDiscResult) -> None:
        """Report each selected track the live path didn't finish, from rip_disc's per-title results; hand each good
        file to the hasher."""
        # Per-title attribution for tracks the live path didn't already
        # finalise (e.g. below-minlength tracks MakeMKV skipped, or
        # eligible tracks that didn't produce a file). Tracks already in
        # `done_emitted` were handed to the hasher by `_on_title_done`
        # mid-rip and are skipped here to avoid double-PATCHing.
        # - If rip_disc reports a result for it: use that. (Includes
        #   ok=False for eligible titles that didn't render — the live
        #   path can't report failures since it's only triggered by PRGC
        #   transitions on successful saves.) A successful file goes to
        #   the hasher like a live one.
        # - Otherwise: the track was below `min_length_seconds`, so MakeMKV
        #   never attempted it. FAILED with a clear reason so the operator
        #   can lower minlength and retry.
        for title_idx, track in self._track_by_index.items():
            if title_idx in self._done_emitted:
                continue
            await self._ensure_started(title_idx, track)
            result = disc_result.titles.get(title_idx)
            if result is None:
                err = _no_output_error(title_idx, track, self._min_length_seconds, self._eligible)
                await self._on_track_done(track, RipResult(ok=False, error=err))
                continue
            output_path = result.output_path
            if not result.ok or output_path is None:
                await self._on_track_done(track, result)
                continue
            # Carry duration_seconds through from the scan when MakeMKV
            # produced the file successfully. rip_disc doesn't measure
            # durations from the .mkv files, so we forward the scan-time
            # estimate. `track.duration_seconds` is the post-rip actual
            # (null until a previous rip set it — usually null here);
            # `track.expected_duration_seconds` is the scan-time estimate
            # populated by `select_tracks` at rip-start.
            if result.duration_seconds is None:
                result = RipResult(
                    ok=True,
                    output_path=result.output_path,
                    size_bytes=result.size_bytes,
                    duration_seconds=track.duration_seconds or track.expected_duration_seconds,
                )
            self._done_emitted.add(title_idx)
            self._hasher.submit(output_path, result.size_bytes or 0, self._finalise_after_hash(track, result))

    async def _fail_unfinished(self, error: str) -> None:
        """Fail every selected track the live path didn't finish with the rip-level error, once the files already handed
        to the hasher are hashed."""
        # Rip-level failure — mark every selected track FAILED with the
        # disc-level error so the operator knows what happened. Each
        # track must transit IN_PROGRESS first per the backend's state
        # machine. Tracks already handed to the hasher via the live
        # path (titles that finalised before the rip aborted) are
        # PATCHed DONE once hashed — partial success is still success
        # for those files.
        logger.warning("rip_disc failed: %s", error)
        await self._hasher.finish(self._on_verify_progress)
        for title_idx, track in self._track_by_index.items():
            if title_idx in self._done_emitted:
                continue
            await self._ensure_started(title_idx, track)
            await self._on_track_done(track, RipResult(ok=False, error=error))


async def rip_optical(
    *,
    device_path: str,
    tracks: list[TrackView],
    output_dir: Path,
    on_track_start: OnTrackStart,
    on_track_done: OnTrackDone,
    on_track_progress: OnTrackProgress | None,
    min_length_seconds: int,
    stop: asyncio.Event | None = None,
    skip_track_ids: Collection[str] = (),
    drive_lost: Callable[[], bool] | None = None,
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
    track_by_index, invalid = _index_tracks(tracks, skip_track_ids)
    # No need to fire on_track_start for an invalid-source_ref
    # track — the backend rejects the track entirely via the
    # FAILED-from-QUEUED guard. Falling through to on_track_done
    # is consistent with how the per-title implementation handled
    # it, and the upstream patch_with_retry catches the 409 if
    # it ever shows up here.
    for track in invalid:
        await on_track_done(track, RipResult(ok=False, error=f"invalid source_ref: {track.source_ref!r}"))

    if not track_by_index:
        return

    eligible_source_indexes = _eligible_source_indexes(track_by_index, min_length_seconds)

    # Titles an earlier pass of this job already settled (a resume after the
    # drive dropped off the bus): makemkvcon rips them again, as `mkv all`
    # does, but they get no callbacks and their new files are deleted.
    skipped = {idx for idx, t in track_by_index.items() if t.id in skip_track_ids}
    await _OpticalRip(
        device_path=device_path,
        output_dir=output_dir,
        track_by_index=track_by_index,
        eligible=eligible_source_indexes,
        skipped=skipped,
        on_track_start=on_track_start,
        on_track_done=on_track_done,
        on_track_progress=on_track_progress,
        min_length_seconds=min_length_seconds,
        stop=stop,
        drive_lost=drive_lost,
    ).run()


def _delete_skipped_outputs(output_dir: Path, eligible_source_indexes: list[int], skipped: set[int]) -> None:
    """Delete the files a resume pass wrote for titles an earlier pass already
    settled. Matched by their `_tNN` position suffix, not by list order, so a
    title that produced no file never shifts the others."""
    if not skipped:
        return
    positions = {pos for pos, idx in enumerate(eligible_source_indexes) if idx in skipped}
    for f in output_dir.glob("*.mkv"):
        m = OUTPUT_FILE_RE.search(f.name)
        if m and int(m.group(1)) in positions:
            f.unlink(missing_ok=True)
