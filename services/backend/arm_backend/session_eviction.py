"""Evicting the applying job's own colliding tasks when a session is re-applied with overwrite."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_common import SessionApplication, TranscodeTask, TranscodeTaskStatus


async def evict_colliding_tasks(db: AsyncSession, paths: list[str], *, job_id: str) -> None:
    """Delete the *applying job's own* live tasks that claim the
    soon-to-be-reused `paths`.

    Called on the overwrite=True branch of manual apply. We delete the
    QUEUED/DONE/FAILED rows at those paths so the new fan-out doesn't
    trip the partial unique index on `output_path`. IN_PROGRESS at the
    same path is a hard refusal — a live transcoder is actively writing
    and can't be safely displaced; the user should cancel that task
    explicitly first.

    Scoped to `job_id`: eviction only ever removes tasks that belong to
    applications owned by the job doing the applying. A collision
    owned by a *different* job is never reachable here — the caller filters
    those out and reports them as a hard `skipped_reason="collisions"`
    before this function is called, even when overwrite=True. Re-ripping a
    disc and overwriting must never silently destroy another job's finished
    output.

    Empty `session_applications` left behind (all their tasks evicted)
    get cleaned up here so the JobDetail page doesn't accumulate husk
    rows on every re-apply.
    """
    own_application_ids = [
        row.id
        for row in (
            await db.execute(select(SessionApplication.id).where(col(SessionApplication.job_id) == job_id))
        ).all()
    ]
    if not own_application_ids:
        # Nothing of this job's has ever fanned out a task — an evictable
        # collision can only be an on-disk-only hit, which has no DB row.
        return

    in_progress_ids = (
        (
            await db.execute(
                select(TranscodeTask.id)
                .where(col(TranscodeTask.output_path).in_(paths))
                .where(col(TranscodeTask.session_application_id).in_(own_application_ids))
                .where(col(TranscodeTask.status) == TranscodeTaskStatus.IN_PROGRESS)
            )
        )
        .scalars()
        .all()
    )
    if in_progress_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"refusing overwrite: {len(in_progress_ids)} task(s) still in_progress at "
                "colliding paths — cancel them first, then re-apply"
            ),
        )

    rows = (
        (
            await db.execute(
                select(TranscodeTask)
                .where(col(TranscodeTask.output_path).in_(paths))
                .where(col(TranscodeTask.session_application_id).in_(own_application_ids))
                .where(col(TranscodeTask.status).in_(_EVICTABLE_STATES))
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        # FS-only collision (no DB row to evict) — atomic_output will
        # clobber the on-disk file via the .arm-inprogress rename dance.
        return

    affected_app_ids = {r.session_application_id for r in rows}
    for row in rows:
        await db.delete(row)
    await db.flush()

    # Drop session_applications that now have zero remaining tasks. If any
    # other tasks still link to the application, leave it alone.
    for app_id in affected_app_ids:
        remaining = (
            await db.execute(select(TranscodeTask).where(col(TranscodeTask.session_application_id) == app_id).limit(1))
        ).scalar_one_or_none()
        if remaining is not None:
            continue
        app = (
            await db.execute(select(SessionApplication).where(col(SessionApplication.id) == app_id))
        ).scalar_one_or_none()
        if app is not None:
            await db.delete(app)
    await db.flush()


_EVICTABLE_STATES: tuple[TranscodeTaskStatus, ...] = (
    TranscodeTaskStatus.QUEUED,
    TranscodeTaskStatus.DONE,
    TranscodeTaskStatus.FAILED,
)
