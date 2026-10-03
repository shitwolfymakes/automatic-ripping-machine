"""The shared job-abandon transition: status -> ABANDONED plus the two WS
events, used by `routers/jobs.py` `abandon_job` and `iso_rips.cancel_iso_rip`
so the two callers never drift apart. Neither commits here — each caller
owns its own commit point.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arm_common import Job, JobStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from arm_backend.ws import WSHub


async def abandon_job_transition(db: AsyncSession, hub: WSHub, job: Job, *, delete_raw: bool = False) -> None:
    """Move a non-terminal job to `abandoned` and tell the ripper to clean up.

    Two cases the ripper handles via the `job.abandoned` WS command:
      * AWAITING_USER_ID / AWAITING_REVIEW — the ripper is parked; the waiter
        polls, sees the non-matching status, exits cleanly.
      * RIPPING — the ripper has an active scan/identify/rip pipeline. The
        WS handler cancels the asyncio task, which kills the makemkvcon
        subprocess so file handles release on `/raw/<id>/`.

    `delete_raw` is plumbed in the WS payload because only the ripper has
    `/raw` mounted; doing the rmtree here would silently no-op. Even when
    there's no active task, the ripper still runs the rmtree against any
    orphaned partial-rip directory.
    """
    job.status = JobStatus.ABANDONED
    db.add(job)
    await db.flush()

    payload: dict[str, Any] = {
        "job_id": job.id,
        "drive_id": job.drive_id,
        "status": job.status.value,
        "delete_raw": delete_raw,
    }
    # Tell the ripper: cancel any active rip on this drive matching the
    # job, optionally rmtree /raw/<id>/. Also wakes a parked
    # `_await_resolution` waiter (handler treats the message as a generic
    # "drive state changed; re-poll" signal).
    await hub.emit(
        topic=f"ripper.commands.{job.drive_id}",
        event_type="job.abandoned",
        payload=payload,
        job_id=job.id,
        session=db,
    )
    await hub.emit(
        topic="ripper.events",
        event_type="rip.abandoned",
        payload=payload,
        job_id=job.id,
        session=db,
    )
