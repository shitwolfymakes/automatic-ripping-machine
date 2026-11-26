"""Post-rip lifecycle of parked session applications.

Promotes them once the rip lands, or cancels them when it never will.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auto_session import (
    ApplySessionOutcome,
    SkippedReason,
    encode_gate_refusal,
    fan_out_tasks_for_application,
    job_tracks,
    load_transcode_preset,
    maybe_auto_apply_session,
    media_mismatch_detail,
)
from arm_backend.path_template import TemplateValidationError
from arm_backend.ws import WSHub
from arm_common import Job, Session, SessionApplication, SessionApplicationStatus, Track, TranscodeTask

logger = logging.getLogger(__name__)


_NO_TRACKS_DETAIL = "not ripped yet: the application fans out when the rip completes"
_NO_OUTPUTS_DETAIL = (
    "tracks exist but none resolved an output for this session (excluded, or none match its "
    "media_type/track routing); the application stays parked"
)


class ResolveFanOutOutcome(NamedTuple):
    """One waiting_identify application's outcome from resolve's fan-out pass.

    `skipped_reason=None` means the application was promoted to QUEUED and
    `tasks` lists the newly-created TranscodeTask rows. A non-None reason
    means the application stays in WAITING_IDENTIFY and `error_detail`
    carries a human-readable explanation for the response body / UI.
    """

    application: SessionApplication
    tasks: list[TranscodeTask]
    skipped_reason: SkippedReason | None
    error_detail: str | None


async def cancel_parked_applications(db: AsyncSession, job: Job) -> int:
    """Cancel the job's WAITING_IDENTIFY applications: the rip failed or the
    job was abandoned, so the drain that would fill them never runs. Leaves
    the commit to the caller. Returns how many were cancelled."""
    parked = (
        (
            await db.execute(
                select(SessionApplication)
                .where(col(SessionApplication.job_id) == job.id)
                .where(col(SessionApplication.status) == SessionApplicationStatus.WAITING_IDENTIFY)
            )
        )
        .scalars()
        .all()
    )
    now = datetime.now(timezone.utc)
    for application in parked:
        application.status = SessionApplicationStatus.CANCELLED
        application.completed_at = now
        db.add(application)
    if parked:
        logger.info("cancelled %d parked session application(s) job_id=%s", len(parked), job.id)
    return len(parked)


def _to_resolve_fan_out_outcome(
    app: SessionApplication, job: Job, sess: Session, outcome: ApplySessionOutcome
) -> ResolveFanOutOutcome:
    """Map a fan-out's ApplySessionOutcome to the outcome resolve reports for that application."""
    if outcome.skipped_reason == "collisions":
        return ResolveFanOutOutcome(
            application=app,
            tasks=[],
            skipped_reason="collisions",
            error_detail=f"output path collisions: {len(outcome.collisions)} path(s) already claimed",
        )

    if outcome.skipped_reason == "no_tracks":
        return ResolveFanOutOutcome(
            application=app,
            tasks=[],
            skipped_reason="no_tracks",
            error_detail=_NO_TRACKS_DETAIL,
        )

    if outcome.skipped_reason == "media_mismatch":
        return ResolveFanOutOutcome(
            application=app,
            tasks=[],
            skipped_reason="media_mismatch",
            error_detail=outcome.error_detail or media_mismatch_detail(job, sess),
        )

    if outcome.skipped_reason == "no_outputs":
        return ResolveFanOutOutcome(
            application=app,
            tasks=[],
            skipped_reason="no_outputs",
            error_detail=_NO_OUTPUTS_DETAIL,
        )

    assert outcome.application is not None
    return ResolveFanOutOutcome(
        application=outcome.application,
        tasks=outcome.tasks,
        skipped_reason=None,
        error_detail=None,
    )


async def _fan_out_waiting_application(
    db: AsyncSession,
    app: SessionApplication,
    job: Job,
    tracks: list[Track],
    hub: WSHub | None,
) -> ResolveFanOutOutcome:
    """Try to promote one waiting_identify application to queued and return its outcome."""
    sess = (await db.execute(select(Session).where(col(Session.id) == app.session_id))).scalar_one_or_none()
    if sess is None:
        return ResolveFanOutOutcome(
            application=app,
            tasks=[],
            skipped_reason="session_missing",
            error_detail=f"session {app.session_id} no longer exists",
        )

    transcode_preset = await load_transcode_preset(db, sess)
    if sess.transcode_preset_id is not None and transcode_preset is None:
        return ResolveFanOutOutcome(
            application=app,
            tasks=[],
            skipped_reason="session_missing",
            error_detail=f"transcode_preset {sess.transcode_preset_id} no longer exists",
        )

    refusal = await encode_gate_refusal(db, transcode_preset)
    if refusal is not None:
        skipped_reason, error_detail = refusal
        return ResolveFanOutOutcome(application=app, tasks=[], skipped_reason=skipped_reason, error_detail=error_detail)

    try:
        outcome = await fan_out_tasks_for_application(
            db,
            application=app,
            job=job,
            sess=sess,
            transcode_preset=transcode_preset,
            tracks=tracks,
            hub=hub,
            source="manual",
            overwrite=False,
            created_by_user_id=None,
        )
    except TemplateValidationError as exc:
        return ResolveFanOutOutcome(
            application=app,
            tasks=[],
            skipped_reason="template",
            error_detail=str(exc),
        )

    return _to_resolve_fan_out_outcome(app, job, sess, outcome)


async def fan_out_waiting_identify_applications(
    db: AsyncSession,
    *,
    job: Job,
    hub: WSHub | None,
) -> list[ResolveFanOutOutcome]:
    """For each waiting_identify application on `job`, attempt to promote it to queued.

    Called from the resolve router after `job.status` is set to IDENTIFIED.
    Per-application failures (missing session/preset, template error,
    collision) are captured in the returned outcomes rather than raised —
    identifying a disc should succeed even if downstream session fan-out
    has problems. Caller is responsible for the commit.
    """
    apps = list(
        (
            await db.execute(
                select(SessionApplication)
                .where(col(SessionApplication.job_id) == job.id)
                .where(col(SessionApplication.status) == SessionApplicationStatus.WAITING_IDENTIFY)
                .order_by(col(SessionApplication.created_at).asc())
            )
        )
        .scalars()
        .all()
    )
    if not apps:
        return []

    tracks = await job_tracks(db, job)

    return [await _fan_out_waiting_application(db, app, job, tracks, hub) for app in apps]


async def after_rip(db: AsyncSession, job: Job, hub: WSHub) -> list[ResolveFanOutOutcome]:
    """Everything that happens once a job's rip is done and its identity is
    known: drain parked applications, then the
    auto-apply hook. Two callers — `rip-complete` for jobs that ripped
    already identified, and `resolve` when a `ripped_awaiting_identify`
    placeholder gains its identity. Never raises; returns the drain's
    outcomes so resolve can report them.

    If the drain promoted at least one parked application to
    QUEUED-with-tasks, that IS the operator's explicit choice winning — skip
    the drive-default auto-apply entirely rather than also queueing it
    alongside. Without this, a disc with both a parked session (explicit,
    pre-rip apply) and a drive default (auto_transcode_on_idle) would fan
    out tasks for both, even though a promoted parked application already
    represents a deliberate operator decision for this disc.
    """
    outcomes = await drain_parked_applications_after_rip(db, job, hub)
    if any(outcome.skipped_reason is None for outcome in outcomes):
        return outcomes
    await maybe_auto_apply_session(db, job, hub)
    return outcomes


async def drain_parked_applications_after_rip(
    db: AsyncSession,
    job: Job,
    hub: WSHub | None,
    *,
    trigger: str = "after-rip",
) -> list[ResolveFanOutOutcome]:
    """First half of `after_rip`.

    A session applied (or resolved) before the rip completes parks as
    `waiting_identify` with no tasks, even when review Track rows already
    exist (held discs): nothing has been ripped yet. Now that the rip has
    landed, promote every parked application on the job. Per-application problems stay parked and
    log at WARN; nothing here may break the caller.

    Also reused when transcoding is switched back on (`trigger` labels the
    log lines): encode applications that hit this drain while the toggle was
    off stayed parked with reason `transcode_disabled`.
    """
    # Read before the try: a rollback expires every loaded instance, and an
    # expired attribute cannot lazy-load on an AsyncSession (MissingGreenlet).
    job_id = job.id
    try:
        outcomes = await fan_out_waiting_identify_applications(db, job=job, hub=hub)
        if not outcomes:
            return []
        await db.commit()
    except Exception:  # noqa: BLE001 - hook must never break rip-complete
        await db.rollback()
        logger.exception("%s: draining parked session_applications failed job_id=%s", trigger, job_id)
        try:
            # Reload the job the rollback expired, so the caller (after_rip's
            # auto-apply half) can keep reading it.
            await db.refresh(job)
        except Exception:  # noqa: BLE001
            logger.warning("%s: reloading job_id=%s after a failed drain failed", trigger, job_id, exc_info=True)
        return []
    for outcome in outcomes:
        if outcome.skipped_reason is None:
            logger.info(
                "%s: fanned out parked session_application=%s job_id=%s tasks=%d",
                trigger,
                outcome.application.id,
                job_id,
                len(outcome.tasks),
            )
        else:
            logger.warning(
                "%s: parked session_application=%s job_id=%s stays parked reason=%s: %s",
                trigger,
                outcome.application.id,
                job_id,
                outcome.skipped_reason,
                outcome.error_detail,
            )
    return outcomes
