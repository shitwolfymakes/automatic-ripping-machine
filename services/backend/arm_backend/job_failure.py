"""Failing a job with a reason the operator can read."""

import logging
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from arm_backend.session_drain import cancel_parked_applications
from arm_backend.ws import WSHub
from arm_common import Job, JobStatus

logger = logging.getLogger("arm_backend.job_failure")


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
