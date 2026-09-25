"""Phase 8: shared apply-session core + rip-complete auto-apply hook.

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
from arm_backend.transcode_apply import compute_outputs, find_collisions, is_passthrough_preset, transcode_enabled_now
from arm_backend.ws import WSHub
from arm_common import (
    Config,
    Drive,
    Job,
    JobStatus,
    MediaType,
    RipPreset,
    Session,
    SessionApplication,
    SessionApplicationStatus,
    SessionRoute,
    Track,
    TranscodePreset,
    TranscodeTask,
    TranscodeTaskStatus,
    with_log_context,
)
from arm_common.models._columns import enum_value_str
from arm_common.schemas import ApplySkippedReason, CollisionInfo

logger = logging.getLogger("arm_backend.auto_session")


_APPLY_OK_STATUSES: frozenset[JobStatus] = frozenset({JobStatus.IDENTIFIED, JobStatus.RIPPED, JobStatus.RIPPED_PARTIAL})
_RIPPED_STATUSES: frozenset[JobStatus] = frozenset(
    {JobStatus.RIPPED, JobStatus.RIPPED_PARTIAL, JobStatus.RIPPED_AWAITING_IDENTIFY}
)
_NO_TRACKS_DETAIL = "no tracks yet: the rip has not started; the application fans out when the rip completes"
_NO_OUTPUTS_DETAIL = (
    "tracks exist but none resolved an output for this session (excluded, or none match its "
    "media_type/track routing); the application stays parked"
)
_TRANSCODE_DISABLED_DETAIL = (
    "transcoding is disabled (Settings > Transcoding); only passthrough sessions can be applied"
)


def _media_types_compatible(job_mt: MediaType, sess_mt: MediaType) -> bool:
    """Whether a session of `sess_mt` can meaningfully apply to a job of `job_mt`.

    movie and tv are the same track kind (`TrackKind.VIDEO_TITLE`, see
    `_track_kinds_for_media` in transcode_apply.py) - a TV session applied to
    a job that got identified as a movie (or vice versa) still fans out real
    tasks. An iso/data session consumes a dump of any video disc (or another
    data disc) - no identified job is ever `iso`, so an iso-typed
    drive-default/route must still apply to movie/tv/data jobs. Music is
    strictly music: never compatible with anything else.
    """
    if job_mt == sess_mt:
        return True
    video = {MediaType.MOVIE, MediaType.TV}
    if sess_mt in video and job_mt in video:
        return True
    if sess_mt in (MediaType.ISO, MediaType.DATA) and job_mt in video | {MediaType.DATA}:
        return True
    return False


def media_mismatch_detail(job: Job, sess: Session) -> str:
    """Human-readable detail for `skipped_reason="media_mismatch"`, naming
    both sides. `job.media_type`/`sess.media_type` are both non-None by the
    time this is called (the guard only fires when both are set and
    incompatible). Uses `enum_value_str` rather than `.value` so a
    forward-compat row that loaded as a raw `str` still renders instead of
    raising `AttributeError`."""
    assert job.media_type is not None
    return (
        f"session media type {enum_value_str(sess.media_type)} is not compatible with "
        f"job media type {enum_value_str(job.media_type)}"
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
    # for skipped_reason="media_mismatch" (Fix 76-7). Computed once here, at
    # the guard site where `job`/`sess` are both in hand, so the manual-apply
    # router (jobs.py) can build its 422 straight from this field instead of
    # re-SELECTing the Session and asserting it's non-None — a re-query that
    # a concurrent delete (or `python -O`, which strips asserts) could turn
    # into a 500 instead of the intended 422.
    error_detail: str | None = None


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

    # The transcode_enabled gate runs before the WAITING_IDENTIFY park so an
    # encode apply is refused (422 on the manual route) in every job state,
    # not accepted-and-parked for jobs still awaiting identity. It sits below
    # the auto idempotency block on purpose: a repeat auto apply of an
    # already-existing application returns that application unchanged.
    if not is_passthrough_preset(transcode_preset) and not await transcode_enabled_now(db):
        return ApplySessionOutcome(
            application=None,
            tasks=[],
            collisions=[],
            idempotent=False,
            skipped_reason="transcode_disabled",
            error_detail=_TRANSCODE_DISABLED_DETAIL,
        )

    # `awaiting_user_id` → park as `waiting_identify` with no tasks.
    # In practice this only happens via the manual route. A placeholder rip
    # that completed without identity (RIPPED_AWAITING_IDENTIFY) parks the
    # same way: transcode is gated on identity, and resolve's after-rip pass
    # promotes the application once the operator supplies it.
    if job.status in (JobStatus.AWAITING_USER_ID, JobStatus.RIPPED_AWAITING_IDENTIFY):
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

    tracks = list(
        (await db.execute(select(Track).where(col(Track.job_id) == job.id).order_by(col(Track.index)))).scalars().all()
    )

    outcome = await _fan_out_tasks_for_application(
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

    if outcome.skipped_reason == "no_tracks":
        logger.info(
            "apply: parked session_id=%s job_id=%s (no tracks yet; fans out at rip-complete) source=%s",
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

    return outcome


async def _fan_out_tasks_for_application(
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
    if (
        job.media_type is not None
        and sess.media_type is not None
        and not _media_types_compatible(job.media_type, sess.media_type)
    ):
        # A routed/manually-picked session whose media_type is INCOMPATIBLE
        # with what the job was actually identified as (e.g. a music session
        # applied to a movie job) fans out zero tasks if we let it through —
        # that's silently indistinguishable from a real crash and gets swept
        # as one. Treat it as a first-class skip instead. Only fires when
        # both sides have declared a type; an unidentified job
        # (media_type=None) has nothing to disagree with yet. Compatible
        # pairs (movie/tv, iso-or-data over any video/data job) are let
        # through — see `_media_types_compatible`.
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
            enum_value_str(job.media_type),
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

    resolved = compute_outputs(job, tracks, sess, transcode_preset)

    # Fix 75-7: park-for-later must be keyed on whether TRACKS exist yet
    # (the pre-rip semantics this branch exists for), not on whether
    # compute_outputs resolved any OUTPUTS. Those are different questions:
    # `not tracks` means the ripper hasn't persisted Track rows yet (apply
    # was made between identify and rip-start, or the disc is still
    # counting down in review) — re-applying at rip-complete/resolve, once
    # the tracks exist, is a completely different — and likely different —
    # outcome. `not resolved` alone can ALSO be true with tracks already
    # present (every track excluded, or none match the session's
    # media_type/track-kind routing) — parking as "no_tracks" there would
    # promise a fan-out at rip-complete that will never come, because the
    # rip is already done and the tracks that exist simply don't qualify.
    if not tracks and job.status not in _RIPPED_STATUSES:
        # The ripper persists Track rows at rip-start, so a session applied
        # between identify and rip-start (or resolved before the rip) has
        # nothing to fan out yet. Park the application with no tasks instead
        # of promoting an empty `queued` husk; `drain_parked_applications_after_rip`
        # fans it out from rip-complete once the tracks exist.
        if application is None:
            application = SessionApplication(
                session_id=sess.id,
                job_id=job.id,
                status=SessionApplicationStatus.WAITING_IDENTIFY,
                overwrite=overwrite,
                created_by_user_id=created_by_user_id,
            )
            db.add(application)
            await db.flush()
        return ApplySessionOutcome(
            application=application,
            tasks=[],
            collisions=[],
            idempotent=False,
            skipped_reason="no_tracks",
        )

    if not resolved:
        # Tracks exist but none resolved to an output (excluded, or none
        # match the session's media_type/track-kind routing). This is its
        # own honest, terminal outcome — never promote an empty QUEUED husk
        # that no drain will ever fill, and never claim "no_tracks" (which
        # promises a rip-complete fan-out that can't happen: the tracks are
        # already here and already don't qualify).
        if application is None:
            application = SessionApplication(
                session_id=sess.id,
                job_id=job.id,
                status=SessionApplicationStatus.WAITING_IDENTIFY,
                overwrite=overwrite,
                created_by_user_id=created_by_user_id,
            )
            db.add(application)
            await db.flush()
        return ApplySessionOutcome(
            application=application,
            tasks=[],
            collisions=[],
            idempotent=False,
            skipped_reason="no_outputs",
        )

    paths = [r.output_path for r in resolved]
    media_root = Path(settings.MEDIA_ROOT)
    collisions = await find_collisions(db, paths, media_root)
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
        # evictable/same-job as before.
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
        await _evict_colliding_tasks(db, same_job_paths, job_id=job.id)

    if application is None:
        application = SessionApplication(
            session_id=sess.id,
            job_id=job.id,
            status=SessionApplicationStatus.QUEUED,
            overwrite=overwrite,
            created_by_user_id=created_by_user_id,
        )
        db.add(application)
        await db.flush()
    else:
        application.status = SessionApplicationStatus.QUEUED

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
                "session_id": sess.id,
                "job_id": job.id,
                "source": source,
                "task_count": len(new_tasks),
            },
            job_id=job.id,
            session=db,
        )

    return ApplySessionOutcome(
        application=application,
        tasks=new_tasks,
        collisions=[],
        idempotent=False,
        skipped_reason=None,
    )


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

    tracks = list(
        (await db.execute(select(Track).where(col(Track.job_id) == job.id).order_by(col(Track.index)))).scalars().all()
    )

    outcomes: list[ResolveFanOutOutcome] = []
    for app in apps:
        sess = (await db.execute(select(Session).where(col(Session.id) == app.session_id))).scalar_one_or_none()
        if sess is None:
            outcomes.append(
                ResolveFanOutOutcome(
                    application=app,
                    tasks=[],
                    skipped_reason="session_missing",
                    error_detail=f"session {app.session_id} no longer exists",
                )
            )
            continue

        transcode_preset: TranscodePreset | None = None
        if sess.transcode_preset_id is not None:
            transcode_preset = (
                await db.execute(select(TranscodePreset).where(col(TranscodePreset.id) == sess.transcode_preset_id))
            ).scalar_one_or_none()
            if transcode_preset is None:
                outcomes.append(
                    ResolveFanOutOutcome(
                        application=app,
                        tasks=[],
                        skipped_reason="session_missing",
                        error_detail=f"transcode_preset {sess.transcode_preset_id} no longer exists",
                    )
                )
                continue

        if not is_passthrough_preset(transcode_preset) and not await transcode_enabled_now(db):
            outcomes.append(
                ResolveFanOutOutcome(
                    application=app,
                    tasks=[],
                    skipped_reason="transcode_disabled",
                    error_detail=_TRANSCODE_DISABLED_DETAIL,
                )
            )
            continue

        try:
            outcome = await _fan_out_tasks_for_application(
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
            outcomes.append(
                ResolveFanOutOutcome(
                    application=app,
                    tasks=[],
                    skipped_reason="template",
                    error_detail=str(exc),
                )
            )
            continue

        if outcome.skipped_reason == "collisions":
            outcomes.append(
                ResolveFanOutOutcome(
                    application=app,
                    tasks=[],
                    skipped_reason="collisions",
                    error_detail=f"output path collisions: {len(outcome.collisions)} path(s) already claimed",
                )
            )
            continue

        if outcome.skipped_reason == "no_tracks":
            outcomes.append(
                ResolveFanOutOutcome(
                    application=app,
                    tasks=[],
                    skipped_reason="no_tracks",
                    error_detail=_NO_TRACKS_DETAIL,
                )
            )
            continue

        if outcome.skipped_reason == "media_mismatch":
            outcomes.append(
                ResolveFanOutOutcome(
                    application=app,
                    tasks=[],
                    skipped_reason="media_mismatch",
                    error_detail=outcome.error_detail or media_mismatch_detail(job, sess),
                )
            )
            continue

        if outcome.skipped_reason == "no_outputs":
            outcomes.append(
                ResolveFanOutOutcome(
                    application=app,
                    tasks=[],
                    skipped_reason="no_outputs",
                    error_detail=_NO_OUTPUTS_DETAIL,
                )
            )
            continue

        assert outcome.application is not None
        outcomes.append(
            ResolveFanOutOutcome(
                application=outcome.application,
                tasks=outcome.tasks,
                skipped_reason=None,
                error_detail=None,
            )
        )

    return outcomes


async def after_rip(db: AsyncSession, job: Job, hub: WSHub) -> list[ResolveFanOutOutcome]:
    """Everything that happens once a job's rip is done and its identity is
    known (gap analysis §5.4): drain parked applications, then the
    auto-apply hook. Two callers — `rip-complete` for jobs that ripped
    already identified, and `resolve` when a `ripped_awaiting_identify`
    placeholder gains its identity. Never raises; returns the drain's
    outcomes so resolve can report them.

    Fix 75-4: if the drain promoted at least one parked application to
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

    A session applied (or resolved) before rip-start parks as
    `waiting_identify` with no tasks because the ripper only persists Track
    rows at rip-start. Now that the rip has landed its tracks, promote every
    parked application on the job. Per-application problems stay parked and
    log at WARN; nothing here may break the caller.

    Also reused when transcoding is switched back on (`trigger` labels the
    log lines): encode applications that hit this drain while the toggle was
    off stayed parked with reason `transcode_disabled`.
    """
    try:
        outcomes = await fan_out_waiting_identify_applications(db, job=job, hub=hub)
        if not outcomes:
            return []
        await db.commit()
    except Exception:  # noqa: BLE001 - hook must never break rip-complete
        await db.rollback()
        logger.exception("%s: draining parked session_applications failed job_id=%s", trigger, job.id)
        return []
    for outcome in outcomes:
        if outcome.skipped_reason is None:
            logger.info(
                "%s: fanned out parked session_application=%s job_id=%s tasks=%d",
                trigger,
                outcome.application.id,
                job.id,
                len(outcome.tasks),
            )
        else:
            logger.warning(
                "%s: parked session_application=%s job_id=%s stays parked reason=%s: %s",
                trigger,
                outcome.application.id,
                job.id,
                outcome.skipped_reason,
                outcome.error_detail,
            )
    return outcomes


async def _evict_colliding_tasks(db: AsyncSession, paths: list[str], *, job_id: str) -> None:
    """Delete the *applying job's own* live tasks that claim the
    soon-to-be-reused `paths`.

    Called on the overwrite=True branch of manual apply. We delete the
    QUEUED/DONE/FAILED rows at those paths so the new fan-out doesn't
    trip the partial unique index on `output_path`. IN_PROGRESS at the
    same path is a hard refusal — a live transcoder is actively writing
    and can't be safely displaced; the user should cancel that task
    explicitly first.

    Scoped to `job_id`: eviction only ever removes tasks that belong to
    applications owned by the job doing the applying (G-08). A collision
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


def _pending_session_id(job: Job) -> str | None:
    return job.pending_session_id or None


async def resolve_routed_session_id(db: AsyncSession, job: Job) -> str | None:
    """Which session is ROUTED to this job (gap analysis §5.1, G-02/G-17).

    Resolution order (single source of truth - rip-start's preset choice and
    the naming preview resolve through this same helper so neither can drift
    from the apply path):
      1. `job.pending_session_id` - explicit per-rip choice.
      2. `drive.default_session_id` - the persistent per-drive default, but
         ONLY when it's compatibility-gated: the drive default wins when
         `job.media_type is None` (nothing to disagree with yet) OR the
         drive-default session's media_type is `_media_types_compatible`
         with the job's. Otherwise (e.g. a movie drive default on a music CD
         job) it's skipped in favor of steps 3-4 - a drive default must not
         permanently swallow a media type it was never meant for (G-17). A
         dangling `default_session_id` (the session row no longer exists)
         also falls through to routes, logged at DEBUG.
      3. `session_routes` row matching `(job.media_type, job.disc_type)` exactly.
      4. `session_routes` wildcard row matching `(job.media_type, NULL)`.
      5. None.
    Steps 3-4 are skipped when `job.media_type is None` (never identified) -
    a route is keyed on media_type, so there is nothing to match. No
    `auto_transcode_on_idle` gating: routing shapes the rip and the preview;
    whether rip-complete may QUEUE the routed session unattended is
    `auto_apply_allowed`'s question. Returns None when nothing routes.
    """
    pending = _pending_session_id(job)
    if pending is not None:
        return pending
    drive = (await db.execute(select(Drive).where(col(Drive.id) == job.drive_id))).scalar_one_or_none()
    if drive is not None and drive.default_session_id is not None:
        if job.media_type is None:
            return drive.default_session_id
        default_sess = (
            await db.execute(select(Session).where(col(Session.id) == drive.default_session_id))
        ).scalar_one_or_none()
        if default_sess is None:
            logger.debug(
                "resolve_routed_session_id: drive default session_id=%s missing for drive_id=%s; falling through to routes",
                drive.default_session_id,
                drive.id,
            )
        elif default_sess.media_type is None or _media_types_compatible(job.media_type, default_sess.media_type):
            return drive.default_session_id
        # else: incompatible drive default — fall through to session_routes.

    if job.media_type is None:
        return None

    routes = (
        (await db.execute(select(SessionRoute).where(col(SessionRoute.media_type) == job.media_type))).scalars().all()
    )
    exact = next((r for r in routes if r.disc_type == job.disc_type), None)
    if exact is not None:
        return exact.session_id
    wildcard = next((r for r in routes if r.disc_type is None), None)
    if wildcard is not None:
        return wildcard.session_id
    return None


async def auto_apply_allowed(db: AsyncSession, job: Job) -> bool:
    """May rip-complete queue the ROUTED session (`resolve_routed_session_id`
    — pending choice, else the compatibility-gated drive default, else
    `session_routes`) unattended?

    An explicit per-rip choice is the user opting in for that one rip and
    bypasses the flag; everything else (drive default or a route) needs
    `auto_transcode_on_idle`.
    """
    if _pending_session_id(job) is not None:
        return True
    config_row = (await db.execute(select(Config).where(col(Config.id) == 1))).scalar_one_or_none()
    return config_row is not None and bool(config_row.auto_transcode_on_idle)


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
