"""Phase 8: shared apply-session core + rip-complete auto-apply hook.

`apply_session_internal` is the engine behind both code paths:
  * `POST /api/jobs/{id}/transcode` — manual click in the UI.
  * `_maybe_auto_apply_session` — fired from `rip-complete` when the disc's
    drive has `default_session_id` set and `Config.auto_transcode_on_idle` is
    enabled.

Both paths emit a single `session.queued` WS event on success with the
`source` field set to `"manual"` or `"auto"` so the UI can render where each
in-flight transcode came from.

Auto-apply failures never bubble out: a deleted session, a template that
resolves to an empty token, or a path collision all log at WARN and let the
caller's HTTP response succeed unchanged. The user can still hand-apply the
session afterwards.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal, NamedTuple

from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.config import settings
from arm_backend.path_template import TemplateValidationError
from arm_backend.transcode_apply import compute_outputs, find_collisions
from arm_backend.ws import WSHub
from arm_common import (
    Config,
    Drive,
    Job,
    JobStatus,
    RipPreset,
    Session,
    SessionApplication,
    SessionApplicationStatus,
    Track,
    TranscodePreset,
    TranscodeTask,
    TranscodeTaskStatus,
    with_log_context,
)
from arm_common.schemas import CollisionInfo

logger = logging.getLogger("arm_backend.auto_session")


_APPLY_OK_STATUSES: frozenset[JobStatus] = frozenset({JobStatus.IDENTIFIED, JobStatus.RIPPED, JobStatus.RIPPED_PARTIAL})


class SessionNotFoundError(Exception):
    """Raised by `apply_session_internal` when `session_id` doesn't resolve."""


SkippedReason = Literal["collisions", "template", "session_missing"]
ApplySource = Literal["manual", "auto"]


class ApplySessionOutcome(NamedTuple):
    application: SessionApplication | None
    tasks: list[TranscodeTask]
    collisions: list[CollisionInfo]
    idempotent: bool
    skipped_reason: SkippedReason | None


async def apply_session_internal(
    db: AsyncSession,
    *,
    job: Job,
    session_id: str,
    overwrite: bool = False,
    created_by_user_id: str | None,
    source: ApplySource,
    hub: WSHub | None = None,
) -> ApplySessionOutcome:
    """Create (or return existing) session_application + fan out transcode tasks.

    Caller responsibilities:
      * Manual route: map `SessionNotFoundError`/`TemplateValidationError`/
        `IntegrityError` to the appropriate HTTP 4xx response, and inspect
        `skipped_reason` to surface collisions to the client.
      * Auto hook: catch all exceptions, log at WARN, swallow.
    """
    with with_log_context(job_id=job.id):
        return await _apply_session_internal(
            db,
            job=job,
            session_id=session_id,
            overwrite=overwrite,
            created_by_user_id=created_by_user_id,
            source=source,
            hub=hub,
        )


async def _apply_session_internal(
    db: AsyncSession,
    *,
    job: Job,
    session_id: str,
    overwrite: bool,
    created_by_user_id: str | None,
    source: ApplySource,
    hub: WSHub | None,
) -> ApplySessionOutcome:
    sess = (await db.execute(select(Session).where(col(Session.id) == session_id))).scalar_one_or_none()
    if sess is None:
        raise SessionNotFoundError(session_id)

    # `auto` keeps idempotency: rip-complete fires once per disc, but we
    # don't want a flapping disc / repeated rip-complete event to spam new
    # applications. A previously-applied session for this (session, job)
    # is the answer; failed tasks get reset to QUEUED so the dispatcher
    # retries that slice.
    #
    # `manual` is non-idempotent on purpose: every click of Apply means
    # "do this work now". If it would write over an existing output, the
    # collision flow surfaces a confirm dialog; on overwrite=True the
    # colliding DONE/QUEUED tasks are deleted before we fan out fresh
    # rows. IN_PROGRESS collisions are still refused — can't safely
    # replace a transcoder that's actively writing.
    if source == "auto":
        existing = (
            await db.execute(
                select(SessionApplication)
                .where(col(SessionApplication.session_id) == session_id)
                .where(col(SessionApplication.job_id) == job.id)
            )
        ).scalar_one_or_none()
        if existing is not None:
            tasks = await _load_tasks(db, existing.id)
            retried = await _retry_failed_tasks(db, tasks)
            if retried > 0:
                if existing.status in (
                    SessionApplicationStatus.FAILED,
                    SessionApplicationStatus.DONE_PARTIAL,
                    SessionApplicationStatus.DONE,
                ):
                    existing.status = SessionApplicationStatus.RUNNING
                    existing.completed_at = None
                await db.commit()
                tasks = await _load_tasks(db, existing.id)
                logger.info(
                    "apply (auto): reset %d failed task(s) on existing session_application=%s",
                    retried,
                    existing.id,
                )
            return ApplySessionOutcome(
                application=existing,
                tasks=tasks,
                collisions=[],
                idempotent=retried == 0,
                skipped_reason=None,
            )

    # `awaiting_user_id` → park as `waiting_identify` with no tasks.
    # In practice this only happens via the manual route — `rip-complete`
    # only fires for jobs already past identification.
    if job.status == JobStatus.AWAITING_USER_ID:
        application = SessionApplication(
            session_id=session_id,
            job_id=job.id,
            status=SessionApplicationStatus.WAITING_IDENTIFY,
            overwrite=False,
            created_by_user_id=created_by_user_id,
        )
        db.add(application)
        await db.commit()
        await db.refresh(application)
        return ApplySessionOutcome(
            application=application,
            tasks=[],
            collisions=[],
            idempotent=False,
            skipped_reason=None,
        )

    if job.status not in _APPLY_OK_STATUSES:
        # Manual route maps this to 409; auto path never reaches here because
        # `maybe_auto_apply_session` gates on RIPPED/RIPPED_PARTIAL.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job is in status {job.status.value}; cannot apply a session",
        )

    rip_preset = (
        await db.execute(select(RipPreset).where(col(RipPreset.id) == sess.rip_preset_id))
    ).scalar_one_or_none()
    if rip_preset is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"session references missing rip_preset_id={sess.rip_preset_id}",
        )

    transcode_preset: TranscodePreset | None = None
    if sess.transcode_preset_id is not None:
        transcode_preset = (
            await db.execute(select(TranscodePreset).where(col(TranscodePreset.id) == sess.transcode_preset_id))
        ).scalar_one_or_none()
        if transcode_preset is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"session references missing transcode_preset_id={sess.transcode_preset_id}",
            )

    tracks = list(
        (await db.execute(select(Track).where(col(Track.job_id) == job.id).order_by(col(Track.index)))).scalars().all()
    )

    resolved = compute_outputs(job, tracks, sess, transcode_preset)

    paths = [r.output_path for r in resolved]
    media_root = Path(settings.MEDIA_ROOT)
    collisions = await find_collisions(db, paths, media_root)
    if collisions and not overwrite:
        return ApplySessionOutcome(
            application=None,
            tasks=[],
            collisions=collisions,
            idempotent=False,
            skipped_reason="collisions",
        )

    if overwrite and collisions:
        await _evict_colliding_tasks(db, paths)

    application = SessionApplication(
        session_id=session_id,
        job_id=job.id,
        status=SessionApplicationStatus.QUEUED,
        overwrite=overwrite,
        created_by_user_id=created_by_user_id,
    )
    db.add(application)
    await db.flush()

    new_tasks = [
        TranscodeTask(
            session_application_id=application.id,
            source_track_id=r.track_id,
            status=TranscodeTaskStatus.QUEUED,
            output_path=r.output_path,
            attempts=0,
            progress_pct=0,
        )
        for r in resolved
    ]
    db.add_all(new_tasks)

    if hub is not None and new_tasks:
        await hub.emit(
            topic="session.events",
            event_type="session.queued",
            payload={
                "session_application_id": application.id,
                "session_id": session_id,
                "job_id": job.id,
                "source": source,
                "task_count": len(new_tasks),
            },
            job_id=job.id,
            session=db,
        )

    await db.commit()
    await db.refresh(application)
    for task in new_tasks:
        await db.refresh(task)

    logger.info(
        "apply session_id=%s job_id=%s tasks=%d overwrite=%s source=%s",
        session_id,
        job.id,
        len(new_tasks),
        overwrite,
        source,
    )

    return ApplySessionOutcome(
        application=application,
        tasks=new_tasks,
        collisions=[],
        idempotent=False,
        skipped_reason=None,
    )


async def _evict_colliding_tasks(db: AsyncSession, paths: list[str]) -> None:
    """Delete live tasks that claim the soon-to-be-reused `paths`.

    Called on the overwrite=True branch of manual apply. We delete the
    QUEUED/DONE/FAILED rows at those paths so the new fan-out doesn't
    trip the partial unique index on `output_path`. IN_PROGRESS at the
    same path is a hard refusal — a live transcoder is actively writing
    and can't be safely displaced; the user should cancel that task
    explicitly first.

    Empty `session_applications` left behind (all their tasks evicted)
    get cleaned up here so the JobDetail page doesn't accumulate husk
    rows on every re-apply.
    """
    in_progress_ids = (
        (
            await db.execute(
                select(TranscodeTask.id)
                .where(col(TranscodeTask.output_path).in_(paths))
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


async def _retry_failed_tasks(db: AsyncSession, tasks: list[TranscodeTask]) -> int:
    """Reset every FAILED task back to QUEUED so the dispatcher retries it.

    Clears `last_error`, `claimed_by`, `claim_heartbeat_at`, and `progress_pct`
    so a fresh spawn looks like a brand-new task. `attempts` is preserved —
    it's a useful audit signal of how many tries have happened. Returns the
    number of rows reset.
    """
    reset = 0
    for task in tasks:
        if task.status != TranscodeTaskStatus.FAILED:
            continue
        task.status = TranscodeTaskStatus.QUEUED
        task.last_error = None
        task.claimed_by = None
        task.claim_heartbeat_at = None
        task.progress_pct = 0
        reset += 1
    if reset:
        await db.flush()
    return reset


async def _load_tasks(db: AsyncSession, session_application_id: str) -> list[TranscodeTask]:
    rows = (
        (
            await db.execute(
                select(TranscodeTask)
                .where(col(TranscodeTask.session_application_id) == session_application_id)
                .order_by(col(TranscodeTask.created_at).asc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def maybe_auto_apply_session(
    db: AsyncSession,
    job: Job,
    hub: WSHub,
) -> None:
    """Hook invoked from `rip-complete`. Silent on every failure mode.

    Resolution order for the session to apply:
      1. `job.metadata_json["pending_session_id"]` — set by the ripper when
         the rip was kicked off via `POST /api/jobs/manual` with a chosen
         session. Always wins; bypasses `auto_transcode_on_idle` since the
         user explicitly opted in for this one rip.
      2. `drive.default_session_id` — the persistent per-drive default,
         only honoured when `Config.auto_transcode_on_idle` is True.
    """
    pending = (job.metadata_json or {}).get("pending_session_id")
    if isinstance(pending, str) and pending:
        session_id = pending
    else:
        drive = (await db.execute(select(Drive).where(col(Drive.id) == job.drive_id))).scalar_one_or_none()
        if drive is None or drive.default_session_id is None:
            return

        config_row = (await db.execute(select(Config).where(col(Config.id) == 1))).scalar_one_or_none()
        if config_row is None or not config_row.auto_transcode_on_idle:
            return

        session_id = drive.default_session_id
    try:
        outcome = await apply_session_internal(
            db,
            job=job,
            session_id=session_id,
            overwrite=False,
            created_by_user_id=None,
            source="auto",
            hub=hub,
        )
    except SessionNotFoundError:
        logger.warning(
            "auto-apply skipped: session_id=%s missing for job_id=%s",
            session_id,
            job.id,
        )
        return
    except TemplateValidationError as exc:
        logger.warning(
            "auto-apply skipped: template error session_id=%s job_id=%s: %s",
            session_id,
            job.id,
            exc,
        )
        return
    except IntegrityError as exc:
        await db.rollback()
        logger.warning(
            "auto-apply skipped: integrity error session_id=%s job_id=%s: %s",
            session_id,
            job.id,
            exc,
        )
        return
    except Exception as exc:  # noqa: BLE001 - hook must never break rip-complete
        await db.rollback()
        logger.exception(
            "auto-apply unexpected error session_id=%s job_id=%s: %s",
            session_id,
            job.id,
            exc,
        )
        return

    if outcome.skipped_reason is not None:
        logger.warning(
            "auto-apply skipped reason=%s session_id=%s job_id=%s",
            outcome.skipped_reason,
            session_id,
            job.id,
        )
