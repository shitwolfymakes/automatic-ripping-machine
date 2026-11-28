"""D24: stage a track as soon as it finishes ripping, while later titles still rip.

A track is staged early only when the session that would auto-apply at rip-complete runs an encode preset
that includes it, and the job is not held for review. Fan-out later finds the row already there."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auto_session import job_tracks, load_transcode_preset
from arm_backend.config import settings
from arm_backend.path_template import TemplateValidationError
from arm_backend.session_routing import auto_apply_allowed, resolve_routed_session_id
from arm_backend.stager import wake_active_stager
from arm_backend.staging import ensure_stage_rows
from arm_backend.title_map_service import job_stereo_3d_refs
from arm_backend.transcode_apply import compute_outputs, is_passthrough_preset
from arm_backend.ws import WSHub
from arm_common import Job, JobStatus, Session, Track

logger = logging.getLogger("arm_backend.early_staging")


def is_held_for_review(job: Job) -> bool:
    """Whether the job waits for the operator, so its track selection is not final yet."""
    return job.status == JobStatus.AWAITING_REVIEW or job.manual_pause


async def _auto_apply_session(db: AsyncSession, job: Job) -> Session | None:
    """The session `maybe_auto_apply_session` would apply to the job at rip-complete, if it would apply one."""
    if not await auto_apply_allowed(db, job):
        return None
    session_id = await resolve_routed_session_id(db, job)
    if session_id is None:
        return None
    return (await db.execute(select(Session).where(col(Session.id) == session_id))).scalar_one_or_none()


async def _encodes_track(db: AsyncSession, job: Job, sess: Session, track: Track) -> bool:
    """Whether the session runs an encode preset with an output for the track."""
    preset = await load_transcode_preset(db, sess)
    if is_passthrough_preset(preset):
        return False
    try:
        resolved = compute_outputs(job, await job_tracks(db, job), sess, preset, job_stereo_3d_refs(job))
    except TemplateValidationError:
        return False
    return any(r.track_id == track.id for r in resolved)


async def stage_finished_track(db: AsyncSession, hub: WSHub, track: Track) -> None:
    """Queue a stage row for a track that just finished ripping, when the auto-apply session will encode it.

    Commits when it queued one. Never raises: it is a head start for the later fan-out, not part of the rip."""
    try:
        job = (await db.execute(select(Job).where(col(Job.id) == track.job_id))).scalar_one_or_none()
        if job is None or is_held_for_review(job):
            return
        sess = await _auto_apply_session(db, job)
        if sess is None or not await _encodes_track(db, job, sess, track):
            return
        if await ensure_stage_rows(db, settings, [track], hub):
            await db.commit()
            wake_active_stager()
    except Exception as exc:  # noqa: BLE001 - must never fail the track's DONE update
        await db.rollback()
        logger.warning("early staging skipped track_id=%s: %s", track.id, exc)
