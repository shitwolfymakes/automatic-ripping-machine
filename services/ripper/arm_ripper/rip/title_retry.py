"""Rips one title, retrying it once when the drive, not the title, made it fail."""

import logging
import shutil
from collections.abc import Awaitable, Callable
from pathlib import Path

from arm_common.schemas import TrackView

from arm_ripper.drive_ready import Probe, ReadyOutcome, is_drive_transient, probe_drive, wait_until_readable
from arm_ripper.rip.makemkv_process import STOPPED_ERROR
from arm_ripper.rip.result import RipResult
from arm_ripper.rip.track_callbacks import OnTrackDone

logger = logging.getLogger("arm_ripper.rip.dispatcher")

# One retry: a title that fails twice on a ready drive is a real failure.
TITLE_RETRIES = 1

RunAttempt = Callable[[OnTrackDone], Awaitable[None]]


class _Held:
    """Keeps the one result an attempt reports, so the caller can decide whether it stands."""

    def __init__(self) -> None:
        self.result: RipResult | None = None

    async def __call__(self, _track: TrackView, result: RipResult) -> None:
        self.result = result


def _failure_is_transient(device_path: str, result: RipResult, probe: Callable[[str], Probe]) -> bool:
    """Whether a failed attempt looks like the drive's doing and worth another try on a drive that recovers."""
    return result.error != STOPPED_ERROR and is_drive_transient(result.error, probe(device_path).state)


async def rip_title_with_retry(
    *,
    track: TrackView,
    device_path: str,
    folder: Path,
    run_attempt: RunAttempt,
    on_track_done: OnTrackDone,
    probe: Callable[[str], Probe] = probe_drive,
    wait_ready: Callable[[str], Awaitable[ReadyOutcome]] = wait_until_readable,
) -> RipResult:
    """Rip the title with `run_attempt` and report its result through `on_track_done`.

    A failure that looks drive-transient is retried up to TITLE_RETRIES times, each after the drive passes the
    readiness gate again and with the title's folder emptied; anything else, or a drive that does not come back, is
    reported as the attempt gave it.
    """
    attempt = 0
    while True:
        held = _Held()
        await run_attempt(held)
        result = held.result or RipResult(ok=False, error="the rip reported no result for this title")
        if result.ok or attempt >= TITLE_RETRIES or not _failure_is_transient(device_path, result, probe):
            break
        logger.warning("track %s failed with the drive not ready (%s); waiting to retry", track.id, result.error)
        if await wait_ready(device_path) is not ReadyOutcome.READY:
            break
        shutil.rmtree(folder, ignore_errors=True)
        attempt += 1
    await on_track_done(track, result)
    return result
