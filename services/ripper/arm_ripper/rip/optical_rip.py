"""The DVD and Blu-ray rip: one makemkvcon run for the whole disc, or one per ticked title, attributed back to the
ticked tracks."""

import asyncio
import logging
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from pathlib import Path

from arm_common.enums import TrackStatus
from arm_common.schemas import TrackView

from arm_ripper.drive_ready import ReadyOutcome, wait_until_readable
from arm_ripper.rip.disc_progress import DiscProgress
from arm_ripper.rip.makemkv_process import STOPPED_ERROR
from arm_ripper.rip.makemkv_rip import (
    OUTPUT_FILE_RE,
    RipDiscResult,
    output_files_in_rip_order,
    rip_disc,
)
from arm_ripper.rip.makemkv_settle import suspect_output
from arm_ripper.rip.options import RipOptions
from arm_ripper.rip.result import RipResult
from arm_ripper.rip.title_retry import rip_title_with_retry
from arm_ripper.rip.track_callbacks import OnTrackDone, OnTrackProgress, OnTrackStart, TransferStats, active_index

# Log under the dispatcher's name: these lines have always come from that logger.
logger = logging.getLogger("arm_ripper.rip.dispatcher")


def _index_tracks(
    tracks: list[TrackView], skip_track_ids: Collection[str], title_numbers: Mapping[str, int]
) -> tuple[dict[int, TrackView], list[TrackView]]:
    """Map each track to the MakeMKV title number the backend gave its `source_ref`; also return, in order, the
    tracks with no title number that no earlier pass settled, which the caller fails."""
    # Pre-compute title number → track lookup so the rip-side callbacks
    # are O(1). Skip tracks already settled; collect unnumbered ones.
    track_by_index: dict[int, TrackView] = {}
    invalid: list[TrackView] = []
    for track in tracks:
        idx = title_numbers.get(track.source_ref)
        if idx is None:
            if track.id not in skip_track_ids:
                invalid.append(track)
            continue
        track_by_index[idx] = track
    return track_by_index, invalid


def _scan_duration(track: TrackView) -> int | None:
    """The length MakeMKV's `--minlength` filter sees: the scan-time estimate, else the measured length, else None.

    Before a rip `duration_seconds` (the post-rip actual) is still None, so filtering on it alone would count every
    title as eligible and shift the positional file pairing."""
    if track.expected_duration_seconds is not None:
        return track.expected_duration_seconds
    return track.duration_seconds


def _eligible_source_indexes(track_by_index: dict[int, TrackView], min_length_seconds: int) -> list[int]:
    """The source indexes MakeMKV will rip, ascending: each track at least `min_length_seconds` long, or of unknown
    length."""
    # Eligible source indexes — those whose scan duration meets `--minlength`,
    # sorted ascending. MakeMKV's `mkv all` output files carry an
    # output-position suffix (`_t00`, `_t01`, ...) rather than the
    # source title index, so we pair this list positionally with the
    # files post-rip to get attribution back. Tracks with no known
    # duration (rare — scan didn't find one) are treated as
    # eligible to avoid dropping them silently; if MakeMKV skips them,
    # they fall through to "produced no .mkv" downstream.
    return sorted(idx for idx, t in track_by_index.items() if _meets_min_length(_scan_duration(t), min_length_seconds))


def _meets_min_length(duration: int | None, min_length_seconds: int) -> bool:
    """Whether MakeMKV keeps a title of this length; an unknown length counts as kept."""
    return duration is None or duration >= min_length_seconds


def _no_output_error(title_idx: int, track: TrackView, min_length_seconds: int, eligible: list[int]) -> str:
    """Why a ticked title has no result: MakeMKV skipped it as too short, or it produced nothing for it."""
    duration = _scan_duration(track)
    if not _meets_min_length(duration, min_length_seconds):
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


def expected_output_size(track: TrackView, keep_3d: bool) -> int | None:
    """The size a finished output of `track` should reach, or None when the scan's figure does not apply.

    The scan's size for a 3D title counts its MVC dependent-view clips. A run that keeps MVC writes them, so the figure
    stands (and a 3D rip that lost the view lands under it). A run that drops MVC writes the base view only, and the
    scan holds no base-only figure, so a 3D title ripped as 2D has no expected size to compare against."""
    if track.stereo_3d and not keep_3d:
        return None
    return track.expected_size_bytes


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
        title: int | None = None,
        end_on_completion: bool = False,
        keep_3d: bool = False,
    ) -> None:
        self._device_path = device_path
        self._keep_3d = keep_3d
        self._title = title
        self._end_on_completion = end_on_completion
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

    def _drive_dropped(self) -> bool:
        """The drive left the bus under this rip. The first time
        `drive_lost` says so, set `stop`, which kills makemkvcon."""
        if self._stop is None:
            return False
        if not self._stop.is_set() and self._drive_lost is not None and self._drive_lost():
            logger.warning("drive dropped off the bus mid-rip; stopping makemkvcon")
            self._stop.set()
        return self._stop.is_set()

    def _audit(self, title_idx: int, track: TrackView, path: Path, size: int) -> None:
        """Log a finished output that looks short or unfinalised. Only logs: a failed check never fails the title."""
        problems = suspect_output(path, size, expected_output_size(track, self._keep_3d))
        if problems:
            logger.warning("title %d output %s looks suspect: %s", title_idx, path.name, "; ".join(problems))

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

    async def _on_disc_progress(self, fraction: float) -> None:
        """Report MakeMKV's disc-overall PRGV fraction.

        The figure is the disc-wide fraction, so the bar fills smoothly
        0→100 % across the whole rip via the PRGV `total/max` channel.
        It is reported as the progress of the title being ripped (see
        `_active_track`), so the UI can show which file is active.
        """
        track = self._active_track()
        if self._on_track_progress is None or track is None:
            return
        await self._on_track_progress(track, fraction)

    def _active_track(self) -> TrackView | None:
        """The track for the eligible title MakeMKV is ripping: the first whose file it has not finished, or the last
        once all are; None when nothing is eligible."""
        if not self._eligible:
            return None
        return self._track_by_index[active_index(self._eligible, self._done_emitted)]

    async def _on_title_done(self, title_idx: int) -> None:
        """Mid-rip per-title finalisation. Stat the .mkv produced for
        this title's output position and PATCH the Track DONE with its
        size and output_path as soon as makemkvcon has closed the file.

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
        self._audit(title_idx, track, file_path, size)
        await self._ensure_started(title_idx, track)
        result = RipResult(
            ok=True,
            output_path=file_path,
            size_bytes=size,
            duration_seconds=track.duration_seconds or track.expected_duration_seconds,
        )
        self._done_emitted.add(title_idx)
        await self._on_track_done(track, result)

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
        """Run makemkvcon once, then report every ticked (not SKIPPED) track exactly once."""
        disc_result = await rip_disc(
            device_path=self._device_path,
            output_dir=self._output_dir,
            minlength_seconds=self._min_length_seconds,
            eligible_source_indexes=self._eligible,
            on_title_start=self._on_title_start,
            on_disc_progress=self._on_disc_progress,
            on_title_done=self._on_title_done,
            stop=self._stop,
            title=self._title,
            end_on_completion=self._end_on_completion,
            keep_3d=self._keep_3d,
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

    async def _attribute(self, disc_result: RipDiscResult) -> None:
        """Report each ticked track the live path didn't finish, from rip_disc's per-title results."""
        # Per-title attribution for tracks the live path didn't already
        # finalise (e.g. below-minlength tracks MakeMKV skipped, or
        # eligible tracks that didn't produce a file). Tracks already in
        # `done_emitted` were reported by `_on_title_done`
        # mid-rip and are skipped here to avoid double-PATCHing.
        # - If rip_disc reports a result for it: use that. (Includes
        #   ok=False for eligible titles that didn't render — the live
        #   path can't report failures since it's only triggered by PRGC
        #   transitions on successful saves.)
        # - Otherwise: the track was below `min_length_seconds`, so MakeMKV
        #   never attempted it. FAILED with a clear reason so the operator
        #   can lower the session minimum or the minimum title length
        #   setting and rip the disc again; the rip never goes below the
        #   minimum the scan used (`rip_min_length_seconds`).
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
            if result.size_bytes is not None:
                self._audit(title_idx, track, output_path, result.size_bytes)
            if result.duration_seconds is None:
                result = RipResult(
                    ok=True,
                    output_path=result.output_path,
                    size_bytes=result.size_bytes,
                    duration_seconds=track.duration_seconds or track.expected_duration_seconds,
                )
            self._done_emitted.add(title_idx)
            await self._on_track_done(track, result)

    async def _fail_unfinished(self, error: str) -> None:
        """Fail every ticked track the live path didn't finish with the rip-level error."""
        # Rip-level failure — mark every ticked track FAILED with the
        # disc-level error so the operator knows what happened. Each
        # track must transit IN_PROGRESS first per the backend's state
        # machine. Tracks the live path already reported DONE (titles
        # that finalised before the rip aborted) stay done — partial
        # success is still success for those files.
        logger.warning("rip_disc failed: %s", error)
        for title_idx, track in self._track_by_index.items():
            if title_idx in self._done_emitted:
                continue
            await self._ensure_started(title_idx, track)
            await self._on_track_done(track, RipResult(ok=False, error=error))


def _keep_3d_titles(track_by_index: dict[int, TrackView], keep_3d_refs: Collection[str]) -> set[int]:
    """The ticked titles whose MVC dependent view the rip keeps."""
    return {
        idx for idx, t in track_by_index.items() if t.source_ref in keep_3d_refs and t.status is not TrackStatus.SKIPPED
    }


async def rip_optical(
    *,
    device_path: str,
    tracks: list[TrackView],
    output_dir: Path,
    on_track_start: OnTrackStart,
    on_track_done: OnTrackDone,
    on_track_progress: OnTrackProgress | None,
    min_length_seconds: int,
    title_numbers: Mapping[str, int],
    stop: asyncio.Event | None = None,
    skip_track_ids: Collection[str] = (),
    drive_lost: Callable[[], bool] | None = None,
    options: RipOptions = RipOptions(),
) -> None:
    """Single-invocation DVD/BD rip with per-title attribution.

    `options.per_title` (`ARM_RIP_INVOCATION=per_title`) instead runs one `mkv … <title>` per ticked (not SKIPPED),
    unsettled eligible title, each into its own folder. `options.keep_3d_refs` names the 3D titles that keep their MVC
    view: per title, each one's run selects MVC video; in one `mkv all` run, any of them does so for the whole run.
    `options.end_on_completion` ends each makemkvcon run once it
    is complete and its files are closed, instead of at its exit.

    The makemkvcon invocation rips every title ≥ minlength to
    `output_dir`. The caller settles minlength never below the minimum
    the scan listed titles with (`rip_min_length_seconds`), so every file
    belongs to a listed title. We map MakeMKV title number → TrackView through
    `title_numbers` (the backend's `source_ref` → number answer) and
    fan the lifecycle callbacks out as MakeMKV's stream announces each
    title. Tracks with no title number are failed up front — same
    shape as the per-title implementation.

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
    track_by_index, invalid = _index_tracks(tracks, skip_track_ids, title_numbers)
    # No need to fire on_track_start for an unnumbered
    # track — the backend rejects the track entirely via the
    # FAILED-from-QUEUED guard. Falling through to on_track_done
    # is consistent with how the per-title implementation handled
    # it, and the upstream patch_with_retry catches the 409 if
    # it ever shows up here.
    for track in invalid:
        await on_track_done(
            track, RipResult(ok=False, error=f"MakeMKV has no title number for source_ref {track.source_ref!r}")
        )

    if not track_by_index:
        return

    eligible_source_indexes = _eligible_source_indexes(track_by_index, min_length_seconds)

    # Titles an earlier pass of this job already settled (a resume after the
    # drive dropped off the bus): makemkvcon rips them again, as `mkv all`
    # does, but they get no callbacks and their new files are deleted.
    skipped = {idx for idx, t in track_by_index.items() if t.id in skip_track_ids}
    keep_3d_titles = _keep_3d_titles(track_by_index, options.keep_3d_refs)
    if options.per_title:
        await _rip_each_title(
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
            end_on_completion=options.end_on_completion,
            keep_3d_titles=keep_3d_titles,
        )
        return
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
        end_on_completion=options.end_on_completion,
        keep_3d=bool(keep_3d_titles),
    ).run()


def _disc_wide(on_track_progress: OnTrackProgress | None, disc: DiscProgress, title: int) -> OnTrackProgress | None:
    """`on_track_progress` reporting the disc-wide fraction for a title's own fraction; None when nothing listens."""
    if on_track_progress is None:
        return None

    async def report(track: TrackView, fraction: float, stats: TransferStats | None = None, /) -> None:
        await on_track_progress(track, disc.fraction(title, fraction), stats)

    return report


@dataclass(frozen=True)
class _TitleRun:
    """What one title's makemkvcon run needs; `attempt` runs it, as often as the retry asks."""

    device_path: str
    output_dir: Path
    track: TrackView
    title: int
    on_track_start: OnTrackStart
    on_track_progress: OnTrackProgress | None
    min_length_seconds: int
    stop: asyncio.Event | None
    drive_lost: Callable[[], bool] | None
    end_on_completion: bool
    keep_3d: bool

    async def attempt(self, on_done: OnTrackDone) -> None:
        """Run makemkvcon once for the title, reporting its result through `on_done`."""
        await _OpticalRip(
            device_path=self.device_path,
            output_dir=self.output_dir,
            track_by_index={self.title: self.track},
            eligible=[self.title],
            skipped=set(),
            on_track_start=self.on_track_start,
            on_track_done=on_done,
            on_track_progress=self.on_track_progress,
            min_length_seconds=self.min_length_seconds,
            stop=self.stop,
            drive_lost=self.drive_lost,
            title=self.title,
            end_on_completion=self.end_on_completion,
            keep_3d=self.keep_3d,
        ).run()


async def _report_unreached(
    titles: list[int],
    track_by_index: dict[int, TrackView],
    on_track_start: OnTrackStart,
    on_track_done: OnTrackDone,
    error: str,
    *,
    start: bool,
) -> None:
    """Report each of `titles`, which the loop never reached, as failed with `error`; `start` first moves a track
    to in-progress, which a failure needs unless the caller leaves the title for a resume."""
    for idx in titles:
        track = track_by_index[idx]
        if start:
            await on_track_start(track)
        await on_track_done(track, RipResult(ok=False, error=error))


async def _give_up_on_drive(
    titles: list[int],
    outcome: ReadyOutcome,
    track_by_index: dict[int, TrackView],
    on_track_start: OnTrackStart,
    on_track_done: OnTrackDone,
) -> None:
    """The drive will not deliver bytes for the remaining `titles`. One that has gone away is reported stopped, for the
    caller's drop-and-resume path; any other is a failure of those titles."""
    logger.warning("drive not ready (%s); %d title(s) not ripped", outcome.value, len(titles))
    if outcome is ReadyOutcome.ABSENT:
        await _report_unreached(titles, track_by_index, on_track_start, on_track_done, STOPPED_ERROR, start=False)
        return
    error = f"the drive was not ready to rip this title ({outcome.value})"
    await _report_unreached(titles, track_by_index, on_track_start, on_track_done, error, start=True)


async def _fail_below_minimum(
    track_by_index: dict[int, TrackView],
    eligible: list[int],
    skipped: set[int],
    min_length_seconds: int,
    on_track_start: OnTrackStart,
    on_track_done: OnTrackDone,
) -> None:
    """Fail each ticked title MakeMKV would not rip (below the minimum length), as a full pass does."""
    for idx, track in track_by_index.items():
        if idx in skipped or idx in eligible:
            continue
        await on_track_start(track)
        await on_track_done(
            track, RipResult(ok=False, error=_no_output_error(idx, track, min_length_seconds, eligible))
        )


async def _rip_each_title(
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
    end_on_completion: bool,
    keep_3d_titles: Collection[int],
) -> None:
    """One `mkv … <title>` per selected, unsettled eligible title, each into `output_dir/title-NN`, in source order.

    Settled and SKIPPED titles are never read. Each title waits for the drive to be readable first, and one that
    fails because the drive was not ready is tried once more. Progress is reported disc-wide. Once `stop` is set (the
    drive dropped), the titles not yet reached are reported stopped so the caller leaves them for its next resume.
    Selected titles MakeMKV would not rip (below the minimum length) fail with the same reason a full pass gives them.
    A title in `keep_3d_titles` is ripped with MVC video selected; the others under MakeMKV's default.
    """
    pending = [idx for idx in eligible if idx not in skipped]
    # Unticked (SKIPPED) titles are no rip work; the ones an earlier pass settled stay in as done work.
    ticked = {idx: track_by_index[idx] for idx in eligible if track_by_index[idx].status is not TrackStatus.SKIPPED}
    disc = DiscProgress({idx: track.expected_size_bytes for idx, track in ticked.items()}, skipped)
    for n, idx in enumerate(pending):
        if stop is not None and stop.is_set():
            await _report_unreached(
                pending[n:], track_by_index, on_track_start, on_track_done, STOPPED_ERROR, start=False
            )
            return
        outcome = await wait_until_readable(device_path)
        if outcome is not ReadyOutcome.READY:
            await _give_up_on_drive(pending[n:], outcome, track_by_index, on_track_start, on_track_done)
            return
        folder = output_dir / f"title-{idx:02d}"
        title_run = _TitleRun(
            device_path=device_path,
            output_dir=folder,
            track=track_by_index[idx],
            title=idx,
            on_track_start=on_track_start,
            on_track_progress=_disc_wide(on_track_progress, disc, idx),
            min_length_seconds=min_length_seconds,
            stop=stop,
            drive_lost=drive_lost,
            end_on_completion=end_on_completion,
            keep_3d=idx in keep_3d_titles,
        )
        await rip_title_with_retry(
            track=track_by_index[idx],
            device_path=device_path,
            folder=folder,
            run_attempt=title_run.attempt,
            on_track_done=on_track_done,
        )
        disc.settle(idx)
    await _fail_below_minimum(track_by_index, eligible, skipped, min_length_seconds, on_track_start, on_track_done)


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
