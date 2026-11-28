"""Failing a job with a reason the operator can read."""

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from arm_backend.session_drain import cancel_parked_applications
from arm_backend.ws import WSHub
from arm_common import Job, JobStatus
from arm_common.enums import ScanFailureReason
from arm_common.schemas import ScanFailure

logger = logging.getLogger("arm_backend.job_failure")

_VOLUME_KEY_UNKNOWN_TEXT = (
    "MakeMKV could not decrypt this disc: its volume key is unknown and could not be downloaded. "
    "MakeMKV fetches keys from its online server over HTTPS (TCP 443); check that your firewall or router allows "
    "it, then re-insert the disc."
)
_FAILURE_TEXT: dict[ScanFailureReason, str] = {
    ScanFailureReason.VOLUME_KEY_UNKNOWN: _VOLUME_KEY_UNKNOWN_TEXT,
    ScanFailureReason.DISC_OPEN_FAILED: (
        "MakeMKV could not open this disc. Check that it is clean and undamaged and that the drive can read it, "
        "then re-insert it."
    ),
    ScanFailureReason.TIMED_OUT: (
        "MakeMKV took too long to read this disc and was stopped. Re-insert the disc to try again; if it keeps "
        "happening, check the disc and the drive."
    ),
    ScanFailureReason.MAKEMKV_EXPIRED: (
        "This MakeMKV build has expired and refuses to scan discs. Update the ripper image to get a current one."
    ),
    ScanFailureReason.MAKEMKV_ERROR: ("MakeMKV could not scan this disc. The job log has MakeMKV's last output."),
}


def scan_failure_text(failure: ScanFailure) -> str:
    """Pure: the sentence that tells the operator why the scan failed and what to try."""
    return _FAILURE_TEXT[failure.reason]


async def fail_job(db: AsyncSession, hub: WSHub, job: Job, reason: str) -> None:
    """Mark the job FAILED with `reason`, release its parked sessions, announce `rip.failed` and commit."""
    job.status = JobStatus.FAILED
    job.ripped_at = datetime.now(timezone.utc)
    job.failure_reason = reason
    db.add(job)
    await cancel_parked_applications(db, job)
    await hub.emit(
        topic="ripper.events",
        event_type="rip.failed",
        payload={
            "job_id": job.id,
            "drive_id": job.drive_id,
            "status": job.status.value,
            "tracks_done": 0,
            "tracks_failed": 0,
            "tracks_total": 0,
            "reason": reason,
        },
        job_id=job.id,
        session=db,
    )
    await db.commit()
    logger.warning("job_id=%s failed: %s", job.id, reason)
