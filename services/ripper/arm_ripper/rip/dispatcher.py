import asyncio
import time
from collections.abc import Callable, Collection
from pathlib import Path

from arm_common import DiscType
from arm_common.enums import TrackKind
from arm_common.schemas import TrackView

from arm_ripper.rip.abcde_rip import rip_cd
from arm_ripper.rip.data_rip import rip_data
from arm_ripper.rip.makemkv_backup import rip_backup
from arm_ripper.rip.optical_rip import rip_optical
from arm_ripper.rip.result import RipResult
from arm_ripper.rip.track_callbacks import OnTrackDone, OnTrackProgress, OnTrackStart, TransferStats

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
    stop: asyncio.Event | None = None,
    skip_track_ids: Collection[str] = (),
    drive_lost: Callable[[], bool] | None = None,
) -> None:
    """Rip every track in `tracks` and invoke the lifecycle callbacks.

    DVD / BD only: `stop` kills makemkvcon when set (the drive dropped off the
    bus), and `skip_track_ids` names tracks an earlier pass already settled.
    `drive_lost` is asked as each title finishes: makemkvcon moves on from a
    title the drive dropped under before anything else may notice, and that
    title's file is cut short, so it is reported unfinished and `stop` is set.
    A resume passes every track so the `mkv all` output positions still line
    up, and the skipped tracks get no callbacks (their new files are deleted).

    Per disc_type:
    - DVD / BD: one `makemkvcon mkv ... all` invocation for the whole
      disc; per-title outcomes attributed from the robot stream and
      the produced files. Drive stays open the whole time — no gaps
      where USB autosuspend can drop the device. Selected titles get
      DONE/FAILED based on whether MakeMKV produced their file. Titles
      below `min_length_seconds` are skipped by MakeMKV; if the user
      requested one of those, we report FAILED with a clear reason
      rather than silently ignoring it.
    - Any disc whose tracks are all DISC_BACKUP: one `makemkvcon backup --decrypt` (`rip_backup`) for the first track.
    - CD: mark all tracks IN_PROGRESS, run abcde once for the whole disc,
      then emit DONE/FAILED per track from the bulk result.
    - DATA: a single dd dump assigned to the first (only) track.
    """
    if tracks and all(t.kind == TrackKind.DISC_BACKUP for t in tracks):
        await _rip_disc_backup(device_path, tracks[0], output_dir, on_track_start, on_track_done, on_track_progress)
        return

    rip_as = _effective_disc_type(disc_type, tracks)
    if rip_as in (DiscType.DVD, DiscType.BLURAY):
        await rip_optical(
            device_path=device_path,
            tracks=tracks,
            output_dir=output_dir,
            on_track_start=on_track_start,
            on_track_done=on_track_done,
            on_track_progress=on_track_progress,
            min_length_seconds=min_length_seconds,
            stop=stop,
            skip_track_ids=skip_track_ids,
            drive_lost=drive_lost,
        )
        return

    if rip_as == DiscType.CD:
        await _rip_audio_cd(device_path, tracks, output_dir, on_track_start, on_track_done)
        return

    if rip_as == DiscType.DATA:
        await _rip_data_dump(device_path, tracks, output_dir, on_track_start, on_track_done, on_track_progress)
        return

    await _fail_unsupported(rip_as, tracks, on_track_done)


def _effective_disc_type(disc_type: DiscType, tracks: list[TrackView]) -> DiscType:
    """The disc type to rip as: DATA when every track is a full-disc dump, else the type the scan gave."""
    if tracks and all(t.kind == TrackKind.DATA_DUMP for t in tracks):
        # A full-disc dump is a dump whatever the scan called the disc: an
        # operator can pick the full-disc dump session for a bluray/dvd ISO,
        # and makemkvcon must not be asked to rip it.
        return DiscType.DATA
    return disc_type


async def _rip_disc_backup(
    device_path: str,
    backup: TrackView,
    output_dir: Path,
    on_track_start: OnTrackStart,
    on_track_done: OnTrackDone,
    on_track_progress: OnTrackProgress | None,
) -> None:
    """Back up the whole disc with one decrypting `makemkvcon backup`, reported as the single `backup` track."""
    await on_track_start(backup)

    async def _on_backup_progress(fraction: float) -> None:
        if on_track_progress is not None:
            await on_track_progress(backup, fraction)

    result = await rip_backup(device_path=device_path, output_dir=output_dir, on_progress=_on_backup_progress)
    await on_track_done(backup, result)


async def _rip_audio_cd(
    device_path: str,
    tracks: list[TrackView],
    output_dir: Path,
    on_track_start: OnTrackStart,
    on_track_done: OnTrackDone,
) -> None:
    """Rip an audio CD with one abcde run: start every track, then report each one as abcde finishes it."""
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


async def _rip_data_dump(
    device_path: str,
    tracks: list[TrackView],
    output_dir: Path,
    on_track_start: OnTrackStart,
    on_track_done: OnTrackDone,
    on_track_progress: OnTrackProgress | None,
) -> None:
    """Copy the whole disc or image with one dd run, reported as the first track with byte-level progress."""
    if not tracks:
        return
    first = tracks[0]
    await on_track_start(first)
    started = time.monotonic()

    async def _on_data_progress(done: int, total: int | None) -> None:
        if on_track_progress is None:
            return
        elapsed = time.monotonic() - started
        stats: TransferStats = {
            "bytes_done": done,
            "bytes_total": total,
            "rate_bps": done / elapsed if elapsed > 0 else None,
        }
        await on_track_progress(first, min(done / total, 1.0) if total else 0.0, stats)

    result = await rip_data(device_path=device_path, output_dir=output_dir, on_progress=_on_data_progress)
    await on_track_done(first, result)


async def _fail_unsupported(rip_as: DiscType, tracks: list[TrackView], on_track_done: OnTrackDone) -> None:
    """Fail every track of a disc type no ripper handles."""
    for track in tracks:
        await on_track_done(
            track,
            RipResult(ok=False, error=f"no rip path for disc_type={rip_as.value}"),
        )
