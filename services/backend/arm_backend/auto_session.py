"""Shared apply-session core + rip-complete auto-apply hook.

`apply_session_internal` is the engine behind both code paths:
  * `POST /api/jobs/{id}/transcode` — manual click in the UI.
  * `_maybe_auto_apply_session` — fired from `rip-complete` when a session is
    ROUTED to the job (`resolve_routed_session_id`: pending choice, else the
    compatibility-gated drive default, else `session_routes`) and
    `auto_apply_allowed` says unattended queueing is permitted.

Both paths emit a single `session.queued` WS event on success with the
`source` field set to `"manual"` or `"auto"` so the UI can render where each
in-flight transcode came from.

Auto-apply failures never bubble out: a deleted session, a template that
resolves to an empty token, a path collision, or a session/job media_type
incompatibility all log at WARN and let the caller's HTTP response succeed
unchanged. The user can still hand-apply the session afterwards.
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
from arm_backend.session_eviction import evict_colliding_tasks
from arm_backend.session_routing import (
    auto_apply_allowed,
    media_types_compatible,
    resolve_routed_session_id,
    routing_media_type,
)
from arm_backend.transcode_apply import (
    ResolvedTask,
    compute_outputs,
    encoder_available,
    find_collisions,
    is_passthrough_preset,
    transcode_enabled_now,
)
from arm_backend.ws import WSHub
from arm_common import (
    Job,
    OutputMode,
    RipPreset,
    Session,
    SessionApplication,
    SessionApplicationStatus,
    Track,
    TranscodePreset,
    TranscodeTask,
    TranscodeTaskStatus,
    TrackKind,
    with_log_context,
)
from arm_common.encoders import get_encoder
from arm_common.enums import APPLY_OK_JOB_STATUSES, APPLY_PARK_JOB_STATUSES, POST_RIP_JOB_STATUSES
from arm_common.models._columns import enum_value_str
from arm_common.schemas import ApplySkippedReason, CollisionInfo

logger = logging.getLogger("arm_backend.auto_session")


_TRANSCODE_DISABLED_DETAIL = (
    "transcoding is disabled (Settings > Transcoding); only passthrough sessions can be applied"
)
_NO_BACKUP_TRACK_DETAIL = "the Blu-ray decrypted backup session files a disc backup; this job has no backup track"
_ENCODER_UNAVAILABLE_DETAIL = "no enabled device has verified {encoder}; re-probe or enable it in Settings > GPUs"


def _encoder_unavailable_detail(preset: TranscodePreset) -> str:
    """Human-readable detail for `skipped_reason="encoder_unavailable"`.

    Call only after `encoder_available` has already returned False for
    `preset.encoder`. Distinguishes a catalog id that no longer exists (a
    stale row from a removed encoder, same failure mode the dispatcher's
    `_claim_gpu_for_task` guards against) from a known, vendor-pinned id
    with no currently-eligible device.
    """
    try:
        get_encoder(preset.encoder)
    except ValueError:
        return f"preset {preset.id} has unknown encoder {preset.encoder!r}"
    return _ENCODER_UNAVAILABLE_DETAIL.format(encoder=preset.encoder)


def media_mismatch_detail(job: Job, sess: Session) -> str:
    """Human-readable detail for `skipped_reason="media_mismatch"`, naming
    both sides. The job side is `routing_media_type(job)`, which is non-None
    by the time this is called (the guard only fires when both are set and
    incompatible). Uses `enum_value_str` rather than `.value` so a
    forward-compat row that loaded as a raw `str` still renders instead of
    raising `AttributeError`."""
    job_media_type = routing_media_type(job)
    assert job_media_type is not None
    return (
        f"session media type {enum_value_str(sess.media_type)} is not compatible with "
        f"job media type {enum_value_str(job_media_type)}"
    )


class SessionNotFoundError(Exception):
    """Raised by `apply_session_internal` when `session_id` doesn't resolve."""


SkippedReason = ApplySkippedReason  # single definition lives in arm_common.schemas
ApplySource = Literal["manual", "auto"]


class ApplySessionOutcome(NamedTuple):
    application: SessionApplication | None
    tasks: list[TranscodeTask]
    collisions: list[CollisionInfo]
    idempotent: bool
    skipped_reason: SkippedReason | None
    # Human-readable detail for the caller's error response, populated only
    # for skipped_reason="media_mismatch". Computed once here, at
    # the guard site where `job`/`sess` are both in hand, so the manual-apply
    # router (jobs.py) can build its 422 straight from this field instead of
    # re-SELECTing the Session and asserting it's non-None — a re-query that
    # a concurrent delete (or `python -O`, which strips asserts) could turn
    # into a 500 instead of the intended 422.
    error_detail: str | None = None


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


async def _existing_parked_application(db: AsyncSession, session_id: str, job_id: str) -> SessionApplication | None:
    """The WAITING_IDENTIFY application already parked for (session, job), if any.

    Parking is idempotent: a parked row does nothing until a drain fills it, so a
    repeat apply of the same session before the rip (or before identify) returns
    the parked row instead of parking a duplicate. A duplicate would be drained
    into a `collisions` park against its twin's tasks and list the session as
    waiting forever.
    """
    return (
        (
            await db.execute(
                select(SessionApplication)
                .where(col(SessionApplication.session_id) == session_id)
                .where(col(SessionApplication.job_id) == job_id)
                .where(col(SessionApplication.status) == SessionApplicationStatus.WAITING_IDENTIFY)
            )
        )
        .scalars()
        .first()
    )


async def job_tracks(db: AsyncSession, job: Job) -> list[Track]:
    """Return the job's tracks in index order."""
    return list(
        (await db.execute(select(Track).where(col(Track.job_id) == job.id).order_by(col(Track.index)))).scalars().all()
    )


async def load_transcode_preset(db: AsyncSession, sess: Session) -> TranscodePreset | None:
    """Load the session's transcode preset; None means no preset or a dangling id (see `sess.transcode_preset_id`)."""
    if sess.transcode_preset_id is None:
        return None
    return (
        await db.execute(select(TranscodePreset).where(col(TranscodePreset.id) == sess.transcode_preset_id))
    ).scalar_one_or_none()


async def encode_gate_refusal(
    db: AsyncSession, transcode_preset: TranscodePreset | None
) -> tuple[SkippedReason, str] | None:
    """Return `(skipped_reason, error_detail)` for why an encode apply must be refused now, or None.

    Passthrough presets skip both gates; the transcode_enabled gate runs before the encoder one.
    """
    if is_passthrough_preset(transcode_preset):
        return None
    if not await transcode_enabled_now(db):
        return "transcode_disabled", _TRANSCODE_DISABLED_DETAIL
    # Vendor-pinned encoders (catalog kind "gpu") need a currently-eligible
    # device; refuse the apply up front rather than let it queue a task the
    # dispatcher can only fail once it reaches the front of the line. Runs
    # after the transcode_disabled gate above so a deployment with
    # transcoding off reports that reason even when the encoder would also
    # be unavailable. `is_passthrough_preset` returning False guarantees
    # `transcode_preset` is not None.
    assert transcode_preset is not None
    if not await encoder_available(db, transcode_preset.encoder):
        return "encoder_unavailable", _encoder_unavailable_detail(transcode_preset)
    return None


async def _existing_auto_outcome(db: AsyncSession, session_id: str, job: Job) -> ApplySessionOutcome | None:
    """Return the outcome for the job's existing application of the session, or None if there is none."""
    existing_rows = (
        (
            await db.execute(
                select(SessionApplication)
                .where(col(SessionApplication.session_id) == session_id)
                .where(col(SessionApplication.job_id) == job.id)
            )
        )
        .scalars()
        .all()
    )
    if len(existing_rows) > 1:
        # A job can carry several applications of one session; the extra rows still drain, each into
        # its own collisions park, until someone deletes them.
        logger.warning(
            "job %s has %d applications of session %s; using the first (%s)",
            job.id,
            len(existing_rows),
            session_id,
            existing_rows[0].id,
        )
    existing = existing_rows[0] if existing_rows else None
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
    return None


async def _park_waiting_identify(
    db: AsyncSession, session_id: str, job: Job, created_by_user_id: str | None
) -> ApplySessionOutcome:
    """Return the already-parked application, or park a new waiting_identify one with no tasks."""
    parked = await _existing_parked_application(db, session_id, job.id)
    if parked is not None:
        return ApplySessionOutcome(
            application=parked,
            tasks=[],
            collisions=[],
            idempotent=True,
            skipped_reason=None,
        )
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


def _missing_backup_track(rip_preset: RipPreset, job: Job, tracks: list[Track]) -> bool:
    """Whether a FOLDER session runs on a ripped job that has no usable backup track."""
    return (
        rip_preset.output_mode == OutputMode.FOLDER
        and job.status in POST_RIP_JOB_STATUSES
        and not any(t.kind == TrackKind.DISC_BACKUP and not t.excluded for t in tracks)
    )


def _log_apply_result(
    outcome: ApplySessionOutcome, session_id: str, job: Job, overwrite: bool, source: ApplySource
) -> None:
    """Log how the apply ended: parked with no tracks, parked with no outputs, or fanned out."""
    if outcome.skipped_reason == "no_tracks":
        logger.info(
            "apply: parked session_id=%s job_id=%s (not ripped yet; fans out at rip-complete) source=%s",
            session_id,
            job.id,
            source,
        )
    elif outcome.skipped_reason == "no_outputs":
        logger.info(
            "apply: parked session_id=%s job_id=%s (tracks exist but none resolved an output; stays parked) source=%s",
            session_id,
            job.id,
            source,
        )
    else:
        logger.info(
            "apply session_id=%s job_id=%s tasks=%d overwrite=%s source=%s",
            session_id,
            job.id,
            len(outcome.tasks),
            overwrite,
            source,
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
    # replace a transcoder that's actively writing. The exception is a park
    # (pre-rip or pre-identify): it does no work yet, so a repeat click
    # returns the already-parked row (see `_existing_parked_application`).
    if source == "auto" and (existing := await _existing_auto_outcome(db, session_id, job)) is not None:
        return existing

    transcode_preset = await load_transcode_preset(db, sess)
    if sess.transcode_preset_id is not None and transcode_preset is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"session references missing transcode_preset_id={sess.transcode_preset_id}",
        )

    # The transcode_enabled gate runs before the WAITING_IDENTIFY park so an
    # encode apply is refused (422 on the manual route) in every job state,
    # not accepted-and-parked for jobs still awaiting identity. It sits below
    # the auto idempotency block on purpose: a repeat auto apply of an
    # already-existing application returns that application unchanged.
    refusal = await encode_gate_refusal(db, transcode_preset)
    if refusal is not None:
        skipped_reason, error_detail = refusal
        return ApplySessionOutcome(
            application=None,
            tasks=[],
            collisions=[],
            idempotent=False,
            skipped_reason=skipped_reason,
            error_detail=error_detail,
        )

    # `awaiting_user_id` → park as `waiting_identify` with no tasks.
    # In practice this only happens via the manual route. A placeholder rip
    # that completed without identity (RIPPED_AWAITING_IDENTIFY) parks the
    # same way: transcode is gated on identity, and resolve's after-rip pass
    # promotes the application once the operator supplies it.
    if job.status in APPLY_PARK_JOB_STATUSES:
        return await _park_waiting_identify(db, session_id, job, created_by_user_id)

    if job.status not in APPLY_OK_JOB_STATUSES:
        # Manual route maps this to 409; auto path never reaches here because
        # `maybe_auto_apply_session` gates on RIPPED/RIPPED_PARTIAL.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job is in status {enum_value_str(job.status)}; cannot apply a session",
        )

    rip_preset = (
        await db.execute(select(RipPreset).where(col(RipPreset.id) == sess.rip_preset_id))
    ).scalar_one_or_none()
    if rip_preset is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"session references missing rip_preset_id={sess.rip_preset_id}",
        )

    tracks = await job_tracks(db, job)

    # A FOLDER (disc backup) session files the backup folder. On a job that was
    # ripped as titles its template would file a title's .mkv as an
    # extension-less "Title (Year)" file, so it is a mismatch, not a fan-out.
    # Only once ripped: before the rip there is no backup track to look for yet.
    if _missing_backup_track(rip_preset, job, tracks):
        logger.warning(
            "apply: backup session on a job without a backup track session_id=%s job_id=%s source=%s",
            sess.id,
            job.id,
            source,
        )
        return ApplySessionOutcome(
            application=None,
            tasks=[],
            collisions=[],
            idempotent=False,
            skipped_reason="media_mismatch",
            error_detail=_NO_BACKUP_TRACK_DETAIL,
        )

    outcome = await fan_out_tasks_for_application(
        db,
        application=None,
        job=job,
        sess=sess,
        transcode_preset=transcode_preset,
        tracks=tracks,
        hub=hub,
        source=source,
        overwrite=overwrite,
        created_by_user_id=created_by_user_id,
    )

    if outcome.skipped_reason in ("collisions", "media_mismatch"):
        # Nothing new was persisted in the helper on either branch (both are
        # hard-stop errors, not parks): no commit needed. On the resolve-drain
        # path `outcome.application` may be a pre-existing row the caller
        # passed in, but the helper made no unflushed writes to it here.
        return outcome

    await db.commit()
    if outcome.application is not None:  # pragma: no branch — error branches early-return above
        await db.refresh(outcome.application)
    for task in outcome.tasks:
        await db.refresh(task)

    _log_apply_result(outcome, session_id, job, overwrite, source)

    return outcome


async def _add_application(
    db: AsyncSession,
    sess: Session,
    job: Job,
    status: SessionApplicationStatus,
    overwrite: bool,
    created_by_user_id: str | None,
) -> SessionApplication:
    """Create a SessionApplication row in `status`, add it and flush so its id is populated."""
    application = SessionApplication(
        session_id=sess.id,
        job_id=job.id,
        status=status,
        overwrite=overwrite,
        created_by_user_id=created_by_user_id,
    )
    db.add(application)
    await db.flush()
    return application


def _queue_tasks(
    db: AsyncSession,
    application: SessionApplication,
    resolved: list[ResolvedTask],
) -> list[TranscodeTask]:
    """Add one QUEUED TranscodeTask per resolved output and return them."""
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
    return new_tasks


async def _announce_queued(
    hub: WSHub | None,
    db: AsyncSession,
    application: SessionApplication,
    sess: Session,
    job: Job,
    source: ApplySource,
    new_tasks: list[TranscodeTask],
) -> None:
    """Emit session.queued when there is a hub and at least one new task."""
    if hub is not None and new_tasks:
        await hub.emit(
            topic="session.events",
            event_type="session.queued",
            payload={
                "session_application_id": application.id,
                "session_id": sess.id,
                "job_id": job.id,
                "source": source,
                "task_count": len(new_tasks),
            },
            job_id=job.id,
            session=db,
        )


def _media_mismatch_outcome(
    application: SessionApplication | None,
    job: Job,
    sess: Session,
    source: ApplySource,
) -> ApplySessionOutcome | None:
    """Return the media_mismatch skip when the session and job media types disagree, else None."""
    # routing_media_type, not job.media_type: an audio CD MusicBrainz missed
    # is still music, and a video session on it would fan out nothing.
    job_media_type = routing_media_type(job)
    if (
        job_media_type is not None
        and sess.media_type is not None
        and not media_types_compatible(job_media_type, sess.media_type)
    ):
        # A routed/manually-picked session whose media_type is INCOMPATIBLE
        # with what the job was actually identified as (e.g. a music session
        # applied to a movie job) fans out zero tasks if we let it through —
        # that's silently indistinguishable from a real crash and gets swept
        # as one. Treat it as a first-class skip instead. Only fires when
        # both sides have declared a type; an unidentified job
        # (media_type=None) has nothing to disagree with yet. Compatible
        # pairs (movie/tv, iso-or-data over any video/data job) are let
        # through — see `media_types_compatible`.
        #
        # Like `collisions` (and unlike `no_tracks`), this is a hard-stop
        # error, not a "waiting for more info" park: don't create a new
        # application when the caller passed `application=None` (manual
        # apply, which 422s and has nothing to point the new row at).
        # `application` is only non-None here on the resolve-drain path,
        # where it's an existing WAITING_IDENTIFY row that simply stays
        # untouched/parked.
        logger.warning(
            "apply: media type incompatible session_id=%s job_id=%s session_media_type=%s job_media_type=%s source=%s",
            sess.id,
            job.id,
            enum_value_str(sess.media_type),
            enum_value_str(job_media_type),
            source,
        )
        return ApplySessionOutcome(
            application=application,
            tasks=[],
            collisions=[],
            idempotent=False,
            skipped_reason="media_mismatch",
            error_detail=media_mismatch_detail(job, sess),
        )
    return None


async def _park_before_rip(
    db: AsyncSession,
    application: SessionApplication | None,
    sess: Session,
    job: Job,
    overwrite: bool,
    created_by_user_id: str | None,
) -> ApplySessionOutcome:
    """Park a pre-rip fan-out as no_tracks, reusing or creating a WAITING_IDENTIFY row."""
    if application is None:
        parked = await _existing_parked_application(db, sess.id, job.id)
        if parked is not None:
            return ApplySessionOutcome(
                application=parked,
                tasks=[],
                collisions=[],
                idempotent=True,
                skipped_reason="no_tracks",
            )
        application = await _add_application(
            db, sess, job, SessionApplicationStatus.WAITING_IDENTIFY, overwrite, created_by_user_id
        )
    return ApplySessionOutcome(
        application=application,
        tasks=[],
        collisions=[],
        idempotent=False,
        skipped_reason="no_tracks",
    )


async def _park_no_outputs(
    db: AsyncSession,
    application: SessionApplication | None,
    sess: Session,
    job: Job,
    overwrite: bool,
    created_by_user_id: str | None,
) -> ApplySessionOutcome:
    """Park a post-rip fan-out that resolved no outputs as the terminal no_outputs outcome."""
    # Tracks exist but none resolved to an output (excluded, or none
    # match the session's media_type/track-kind routing). This is its
    # own honest, terminal outcome — never promote an empty QUEUED husk
    # that no drain will ever fill, and never claim "no_tracks" (which
    # promises a rip-complete fan-out that can't happen: the tracks are
    # already here and already don't qualify).
    if application is None:
        application = await _add_application(
            db, sess, job, SessionApplicationStatus.WAITING_IDENTIFY, overwrite, created_by_user_id
        )
    return ApplySessionOutcome(
        application=application,
        tasks=[],
        collisions=[],
        idempotent=False,
        skipped_reason="no_outputs",
    )


async def _handle_collisions(
    db: AsyncSession,
    application: SessionApplication | None,
    collisions: list[CollisionInfo],
    job: Job,
    overwrite: bool,
) -> ApplySessionOutcome | None:
    """Return the collisions outcome when the collisions block the apply.

    Otherwise evict the job's own colliding tasks (on overwrite) and return None.
    """
    if collisions and not overwrite:
        return ApplySessionOutcome(
            application=application,
            tasks=[],
            collisions=collisions,
            idempotent=False,
            skipped_reason="collisions",
        )

    if overwrite and collisions:
        # overwrite=True only ever licenses evicting the *applying* job's own
        # colliding tasks. A collision whose owning job differs, OR whose
        # owning job is unknown for an actual existing task
        # (existing_job_id=None with reason="existing_task": a dangling
        # session_application_id, unreachable in real Postgres via CASCADE
        # but modeled reachable by the fake tier / find_collisions), is
        # never silently clobbered — re-ripping a disc and overwriting must
        # not destroy another job's finished output, and an unowned task
        # can't be proven to belong to THIS job either. Any such cross-job
        # (or unowned-task) collision is a hard skip, even though overwrite
        # was requested; same-job eviction can neither refuse nor safely
        # evict an unowned row, and letting it through would trip the
        # output_path unique index on fan-out.
        #
        # `on_disk`/`duplicate_in_request` collisions always carry
        # existing_job_id=None too (see CollisionInfo: the field is only
        # ever populated for reason="existing_task"), but that's a
        # structurally different "not applicable" sentinel, not an unowned
        # task — there's no task row to misattribute, so those stay
        # evictable/same-job.
        cross_job_collisions = [c for c in collisions if c.reason == "existing_task" and c.existing_job_id != job.id]
        if cross_job_collisions:
            # The cross-job (+ unowned-task) subset is what blocks the
            # apply, but the response should still tell the whole truth
            # about every colliding path — report the full collision list,
            # not just the blocking subset.
            return ApplySessionOutcome(
                application=application,
                tasks=[],
                collisions=collisions,
                idempotent=False,
                skipped_reason="collisions",
            )
        same_job_paths = [
            c.output_path for c in collisions if c.reason != "existing_task" or c.existing_job_id == job.id
        ]
        await evict_colliding_tasks(db, same_job_paths, job_id=job.id)
    return None


async def fan_out_tasks_for_application(
    db: AsyncSession,
    *,
    application: SessionApplication | None,
    job: Job,
    sess: Session,
    transcode_preset: TranscodePreset | None,
    tracks: list[Track],
    hub: WSHub | None,
    source: ApplySource,
    overwrite: bool,
    created_by_user_id: str | None,
) -> ApplySessionOutcome:
    """Compute outputs, check collisions, fan out TranscodeTask rows, emit session.queued.

    Two call modes, controlled by `application`:
      * Manual apply path (`application=None`): a fresh `SessionApplication`
        is created in `QUEUED` state. On collision-without-overwrite no
        application is created — caller sees `skipped_reason='collisions'`
        with `application=None`.
      * Resolve fan-out path (`application=<existing WAITING_IDENTIFY row>`):
        the existing application is flipped to `QUEUED` on success; on
        collision-without-overwrite it is left untouched (still
        WAITING_IDENTIFY) and returned with `skipped_reason='collisions'`.

    Caller is responsible for the commit. The helper only `flush`es so the
    new application's id is populated for downstream task FKs.
    """
    if (mismatch := _media_mismatch_outcome(application, job, sess, source)) is not None:
        return mismatch

    # Park-for-later is keyed on RIP STATE, not on whether Track rows exist.
    # A pre-rip job can already carry Track rows: identify's hold_for_review
    # path persists the scan's titles (`_persist_review_tracks`) so the review
    # card can list them, and rip-start reuses those rows. Fanning out against
    # them would queue transcode tasks for titles that have not been ripped.
    # So every pre-rip fan-out (manual apply, resolve fan-out, transcode
    # re-enable redrain) parks as "no_tracks" with no tasks, and
    # `drain_parked_applications_after_rip` fans it out from rip-complete.
    # Output paths are not resolved here either: a still-strict template
    # token (e.g. `{year}` with no year yet) is checked at drain time, where
    # it surfaces as a parked `template` outcome rather than blocking apply.
    if job.status not in POST_RIP_JOB_STATUSES:
        return await _park_before_rip(db, application, sess, job, overwrite, created_by_user_id)

    # Post-rip, `not resolved` is its own terminal outcome, never
    # "no_tracks". Tracks can exist and still resolve zero outputs (every
    # track excluded, or none match the session's media_type/track-kind
    # routing); parking as "no_tracks" there would promise a rip-complete
    # fan-out that will never come, because the rip is already done.
    resolved = compute_outputs(job, tracks, sess, transcode_preset)

    if not resolved:
        return await _park_no_outputs(db, application, sess, job, overwrite, created_by_user_id)

    paths = [r.output_path for r in resolved]
    media_root = Path(settings.MEDIA_ROOT)
    collisions = await find_collisions(db, paths, media_root)
    if (blocked := await _handle_collisions(db, application, collisions, job, overwrite)) is not None:
        return blocked

    if application is None:
        application = await _add_application(
            db, sess, job, SessionApplicationStatus.QUEUED, overwrite, created_by_user_id
        )
    else:
        application.status = SessionApplicationStatus.QUEUED

    new_tasks = _queue_tasks(db, application, resolved)
    await _announce_queued(hub, db, application, sess, job, source, new_tasks)

    return ApplySessionOutcome(
        application=application,
        tasks=new_tasks,
        collisions=[],
        idempotent=False,
        skipped_reason=None,
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

    Applies the ROUTED session (`resolve_routed_session_id`: pending choice,
    else the compatibility-gated drive default, else `session_routes`) when
    `auto_apply_allowed` says unattended queueing is permitted: an explicit
    per-rip choice always is; the drive default or a route needs
    `Config.auto_transcode_on_idle`.
    """
    if not await auto_apply_allowed(db, job):
        return
    session_id = await resolve_routed_session_id(db, job)
    if session_id is None:
        return
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
