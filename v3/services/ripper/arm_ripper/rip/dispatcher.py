import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from arm_common import DiscType, DriveMediaStatus
from arm_common.schemas import TrackView

from arm_ripper.drive_status import probe_drive_media
from arm_ripper.rip.abcde_rip import rip_cd
from arm_ripper.rip.data_rip import rip_data
from arm_ripper.rip.makemkv_rip import RipResult, rip_title

logger = logging.getLogger("arm_ripper.rip.dispatcher")

OnTrackStart = Callable[[TrackView], Awaitable[None]]
OnTrackDone = Callable[[TrackView, RipResult], Awaitable[None]]
OnTrackProgress = Callable[[TrackView, float], Awaitable[None]]

# Drive-recovery window between titles. External USB Blu-ray drives
# (e.g. LG BP50NB40) misbehave in two ways after a long sustained read:
# (1) the kernel unbinds /dev/sr0 entirely (USB autosuspend); subsequent
#     opens fail with ENODEV. open() is what catches this.
# (2) the device re-binds quickly but the medium reports SCSI NOT_READY
#     ("LOGICAL UNIT IS IN PROCESS OF BECOMING READY") for another
#     30-60s while the drive re-spins and re-reads the BD discovery
#     structures. CDROM_DRIVE_STATUS catches this — the ioctl returns
#     CDS_DRIVE_NOT_READY until the medium is actually rip-ready.
# 60s covers the slow USB-BD case observed in production; if the drive
# really is dead we fail-open and let makemkvcon's exit=11 error carry
# the user-visible failure rather than hanging the rip queue.
DRIVE_READY_TIMEOUT_SECONDS = 60.0
DRIVE_READY_POLL_INTERVAL_SECONDS = 0.5


def _is_rip_ready(status: DriveMediaStatus) -> bool:
    """Disc loaded → ready. UNKNOWN is a fall-through bucket (ioctl
    unsupported, virt drive in a test rig); we accept it rather than
    deadlock the rip queue, and let makemkvcon report any real failure."""
    return status in (DriveMediaStatus.LOADED, DriveMediaStatus.UNKNOWN)


async def _wait_for_drive_ready(
    device_path: str,
    *,
    timeout_seconds: float = DRIVE_READY_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DRIVE_READY_POLL_INTERVAL_SECONDS,
) -> bool:
    """Poll `device_path` until the medium is rip-ready, or
    `timeout_seconds` elapses. Returns True on success, False on
    timeout.

    A healthy drive returns immediately on the first probe (no sleep).
    A drive that's mid-re-enumeration or mid-spin-up returns within a
    few poll intervals.
    """
    deadline = time.monotonic() + timeout_seconds
    waited = 0.0
    last_reason = "no probes attempted"
    while True:
        # `verify_read=True` so a parked disc that reports CDS_DISC_OK
        # but returns SCSI NOT_READY on the first SCSI read is caught
        # *before* we hand off to makemkvcon. Run via to_thread because
        # a read on a recovering drive can briefly block.
        status, last_reason = await asyncio.to_thread(probe_drive_media, device_path, verify_read=True)
        if _is_rip_ready(status):
            if waited > 0:
                logger.info("drive %s ready after %.1fs (%s)", device_path, waited, last_reason)
            return True
        if time.monotonic() >= deadline:
            logger.warning(
                "drive %s did not become ready within %.0fs (last status: %s)",
                device_path,
                timeout_seconds,
                last_reason,
            )
            return False
        await asyncio.sleep(poll_interval_seconds)
        waited += poll_interval_seconds


async def rip_all(
    disc_type: DiscType,
    device_path: str,
    tracks: list[TrackView],
    output_dir: Path,
    on_track_start: OnTrackStart,
    on_track_done: OnTrackDone,
    on_track_progress: OnTrackProgress | None = None,
) -> None:
    """Rip every track in `tracks` and invoke the lifecycle callbacks.

    Per disc_type:
    - DVD / BD: iterate tracks; one makemkvcon invocation per title.
    - CD: mark all tracks IN_PROGRESS, run abcde once for the whole disc,
      then emit DONE/FAILED per track from the bulk result.
    - DATA: a single dd dump assigned to the first (only) track.
    """
    if disc_type in (DiscType.DVD, DiscType.BLURAY):
        for i, track in enumerate(tracks):
            # Between-titles drive-recovery wait. Skipped on the first
            # title (the scan just opened the drive) and on the disc-type
            # branches that rip in one shot (CD/DATA below). See
            # _wait_for_drive_ready for the why.
            if i > 0:
                await _wait_for_drive_ready(device_path)

            await on_track_start(track)

            async def _on_progress(fraction: float, t: TrackView = track) -> None:
                if on_track_progress is not None:
                    await on_track_progress(t, fraction)

            try:
                title_index = int(track.source_ref)
            except ValueError:
                await on_track_done(
                    track,
                    RipResult(ok=False, error=f"invalid source_ref: {track.source_ref!r}"),
                )
                continue

            result = await rip_title(
                device_path=device_path,
                title_index=title_index,
                output_dir=output_dir,
                expected_duration_seconds=track.duration_seconds,
                on_progress=_on_progress,
            )
            await on_track_done(track, result)
        return

    if disc_type == DiscType.CD:
        for track in tracks:
            await on_track_start(track)
        results = await rip_cd(
            device_path=device_path,
            output_dir=output_dir,
            track_indexes=[t.index for t in tracks],
        )
        for track in tracks:
            result = results.get(
                track.index,
                RipResult(ok=False, error=f"abcde produced no entry for track {track.index}"),
            )
            await on_track_done(track, result)
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
