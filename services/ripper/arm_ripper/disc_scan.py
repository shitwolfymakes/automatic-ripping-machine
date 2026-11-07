"""Scans the disc for its titles, retrying while a freshly-settled drive is not yet data-readable."""

import asyncio
import logging

from arm_common.schemas import ScanResult
from arm_ripper.drive_poll import DriveErrorKind, DriveState, classify_drive_error, read_drive_status
from arm_ripper.scan import ScanError, scan as scan_disc
from arm_ripper.source import is_file_source

# The moved code keeps the job controller's logger name so existing log filters and log text stay the same.
logger = logging.getLogger("arm_ripper.job_controller")

# A freshly-settled disc can report DISC_OK via the CDROM_DRIVE_STATUS ioctl
# before the medium is *data*-readable, so makemkvcon enumerates zero titles.
# The disc IS present (per ioctl), so a zero-title scan there means "not ready
# yet," not "genuinely empty" — retry, letting the drive finish spinning up /
# the TOC become readable. Generous budget (a quick 1-2s retry would miss a slow
# settle — the field report saw 4/4 discs fail); bounded so a genuinely
# unreadable disc resolves to a clear give-up in ~26s.
SCAN_NOT_READY_MAX_ATTEMPTS = 5
SCAN_NOT_READY_BACKOFFS = (2.0, 4.0, 8.0, 12.0)  # between attempts 1→2, 2→3, 3→4, 4→5


async def scan_or_none(device_path: str) -> ScanResult | None:
    """Scan the disc, or None after a log line when the scan fails or the drive goes absent mid-scan (which ends
    the pipeline). Any other OSError propagates."""
    try:
        return await _scan_with_ready_retry(device_path)
    except ScanError as e:
        logger.error("scan failed device=%s err=%s", device_path, e)
        return None
    except OSError as e:
        if classify_drive_error(e) is not DriveErrorKind.ABSENT:
            raise
        logger.warning("drive went absent during scan device=%s — pipeline abandoned", device_path)
        return None


async def _scan_with_ready_retry(device_path: str) -> ScanResult:
    """Scan the disc, retrying when a DISC_OK drive yields zero titles.

    A `DISC_OK` drive that scans to zero titles is almost certainly not
    data-ready yet (the medium reports present via ioctl before the first
    SCSI read succeeds). Retry with backoff to wait out the settle. If the
    drive leaves DISC_OK (tray opened / disc pulled), stop. On exhaustion,
    return the last (empty) result — the caller handles the give-up.

    Note: `read_drive_status` (os.open + ioctl) may raise OSError if the
    device node vanishes mid-retry (USB autosuspend / passthrough teardown);
    that propagates to the pipeline task boundary by design — the task ends
    and the drive poller re-arms on the next disc-insert event.
    """
    last: ScanResult | None = None
    for attempt in range(1, SCAN_NOT_READY_MAX_ATTEMPTS + 1):
        result = await scan_disc(device_path)
        last = result
        if result.titles:
            return result

        # An ISO file has no drive to settle: the CDROM_DRIVE_STATUS ioctl
        # below is invalid on a regular file (ENOTTY) and would crash the
        # one-shot source pipeline. Zero titles from a file is final.
        if _zero_titles_are_final(device_path):
            return result

        if attempt < SCAN_NOT_READY_MAX_ATTEMPTS and not await _back_off_before_rescan(device_path, attempt):
            return result

    logger.error(
        "DISC_UNREADABLE_AFTER_RETRIES device=%s drive_state=DISC_OK attempts=%d — "
        "disc present per ioctl but no readable titles after retries; check disc/drive "
        "readiness (dirty/damaged disc, drive spin-up, or container device passthrough)",
        device_path,
        SCAN_NOT_READY_MAX_ATTEMPTS,
    )
    assert last is not None
    return last


def _zero_titles_are_final(device_path: str) -> bool:
    """Whether a zero-title scan is the answer rather than a drive still settling: an ISO source has nothing to
    settle, and a drive no longer DISC_OK has lost its disc."""
    if is_file_source(device_path):
        logger.warning("scan: 0 titles from ISO source %s — nothing to retry", device_path)
        return True
    state = read_drive_status(device_path)
    if state != DriveState.DISC_OK:
        logger.info(
            "scan: 0 titles and drive no longer DISC_OK (state=%s) device=%s — stopping",
            state.name,
            device_path,
        )
        return True
    return False


async def _back_off_before_rescan(device_path: str, attempt: int) -> bool:
    """Wait out this attempt's back-off, then report whether the drive still holds its disc and is worth
    scanning again."""
    backoff = SCAN_NOT_READY_BACKOFFS[attempt - 1]
    logger.warning(
        "scan returned 0 titles while drive=DISC_OK (data not ready?) device=%s titles=0 retry=%d/%d backoff=%.0fs",
        device_path,
        attempt,
        SCAN_NOT_READY_MAX_ATTEMPTS,
        backoff,
    )
    await asyncio.sleep(backoff)
    # Re-check status after the sleep — disc may have been pulled
    # while we were waiting; stop before wasting another scan probe.
    post_sleep_state = read_drive_status(device_path)
    if post_sleep_state != DriveState.DISC_OK:
        logger.info(
            "scan: drive left DISC_OK during backoff (state=%s) device=%s — stopping",
            post_sleep_state.name,
            device_path,
        )
        return False
    return True
