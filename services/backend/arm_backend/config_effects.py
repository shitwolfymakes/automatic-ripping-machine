"""What a config change sets off after it is committed: identity re-resolution and parked-encode re-drain."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.identity.pipeline import resolve_job
from arm_backend.identity.stage_runner import EpisodeStageRunner, emit_identity_resolved
from arm_backend.session_drain import drain_parked_applications_after_rip
from arm_backend.ws import WSHub
from arm_common import Job, JobStatus, SessionApplication, SessionApplicationStatus
from arm_common.enums import NON_TERMINAL_JOB_STATUSES, REDRAIN_JOB_STATUSES

logger = logging.getLogger("arm_backend.config_effects")

# Ripped jobs are re-resolved only while no session has been applied: once
# transcodes exist their output paths were built from the identity as it was.
_RERESOLVE_JOB_STATUSES = NON_TERMINAL_JOB_STATUSES | {JobStatus.RIPPED_AWAITING_IDENTIFY}
_RERESOLVE_IF_UNAPPLIED_STATUSES = frozenset({JobStatus.RIPPED, JobStatus.RIPPED_PARTIAL})


async def reresolve_identity(session: AsyncSession, hub: WSHub | None, stage_runner: EpisodeStageRunner | None) -> None:
    """Re-run the identity resolver on live jobs after the source settings
    changed, and schedule the episode stage (a newly enabled episode source
    has no stored claims yet). Per job: lock, resolve, commit, emit. A failure
    is logged and skipped; the PATCH has already committed and never fails
    here."""
    try:
        candidates = [
            (job.id, job.status)
            for job in (
                await session.execute(
                    select(Job).where(
                        col(Job.status).in_(list(_RERESOLVE_JOB_STATUSES | _RERESOLVE_IF_UNAPPLIED_STATUSES))
                    )
                )
            )
            .scalars()
            .all()
        ]
        applied = {
            application.job_id
            for application in (
                await session.execute(
                    select(SessionApplication).where(
                        col(SessionApplication.job_id).in_([job_id for job_id, _ in candidates])
                    )
                )
            )
            .scalars()
            .all()
        }
    except Exception:  # noqa: BLE001 - never fail the config PATCH
        logger.warning("identity source change: listing live jobs failed", exc_info=True)
        return
    job_ids = [
        job_id
        for job_id, job_status in candidates
        if job_status not in _RERESOLVE_IF_UNAPPLIED_STATUSES or job_id not in applied
    ]
    for job_id in job_ids:
        try:
            job = (
                await session.execute(
                    select(Job).where(col(Job.id) == job_id).with_for_update().execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()
            if job is None:
                continue
            resolved = await resolve_job(session, job)
            await session.commit()
            if resolved.changed and hub is not None:
                await emit_identity_resolved(session, hub, job, resolved, sources={})
                await session.commit()
        except Exception:  # noqa: BLE001 - one job must not stop the rest
            await session.rollback()
            logger.warning("identity source change: re-resolving job_id=%s failed", job_id, exc_info=True)
            continue
        if stage_runner is not None:
            stage_runner.schedule(job_id)
    if job_ids:
        logger.info("identity source change: re-resolved %d live job(s)", len(job_ids))


async def redrain_parked_applications(session: AsyncSession, hub: WSHub | None) -> None:
    """Promote encode applications parked while transcoding was off.

    Runs after the toggle commit, so `transcode_enabled_now` reads the new
    value. Reuses the after-rip drain (which commits per job, logs per
    application, and never raises); any failure here is logged and swallowed
    so the PATCH itself always succeeds once the toggle is saved.
    """
    try:
        parked_job_ids = {
            app.job_id
            for app in (
                await session.execute(
                    select(SessionApplication).where(
                        col(SessionApplication.status) == SessionApplicationStatus.WAITING_IDENTIFY
                    )
                )
            )
            .scalars()
            .all()
        }
        if not parked_job_ids:
            return
        job_ids = [
            job.id
            for job in (
                await session.execute(
                    select(Job)
                    .where(col(Job.id).in_(sorted(parked_job_ids)))
                    .where(col(Job.status).in_(list(REDRAIN_JOB_STATUSES)))
                )
            )
            .scalars()
            .all()
        ]
    except Exception:  # noqa: BLE001 - re-drain must never fail the config PATCH
        logger.warning("transcode re-enable: listing parked session_applications failed", exc_info=True)
        return
    for job_id in job_ids:
        # Load each job fresh: a failed drain rolls the session back, which
        # expires every job loaded before it.
        try:
            job = (
                await session.execute(
                    select(Job).where(col(Job.id) == job_id).execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()
            if job is not None:
                await drain_parked_applications_after_rip(session, job, hub, trigger="transcode re-enable")
        except Exception:  # noqa: BLE001 - one job must not stop the rest
            await session.rollback()
            logger.warning("transcode re-enable: re-draining job_id=%s failed", job_id, exc_info=True)
