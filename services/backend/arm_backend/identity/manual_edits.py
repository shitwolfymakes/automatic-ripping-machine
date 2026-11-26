"""Applying an operator's manual job and track edits, with identity fields routed through the resolver."""

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.identity.pipeline import resolve_job
from arm_backend.identity.proposals import (
    record_manual_job,
    record_manual_track,
    revert_manual_track,
)
from arm_backend.identity.resolve_service import identity_snapshot
from arm_backend.identity.stage_runner import EpisodeStageRunner
from arm_backend.ws import WSHub
from arm_common import Job
from arm_common.models import Track
from arm_common.schemas import JobUpdateRequest, TrackEditRequest
from arm_common.schemas.identity import JOB_CLAIM_FIELDS, TRACK_CLAIM_FIELDS

# Resolver-owned attributes on TrackEditRequest / JobUpdateRequest: an edit to
# one of these becomes a `manual` identity proposal (with provenance) instead
# of a direct column write, so it goes through the same tiered resolver as
# every other identity source. Everything else is still a plain `setattr`.
# Derived from the claim-field maps so the resolver, the recorders and this
# module cannot drift apart. JobUpdateRequest has no `season` (it is set
# through /resolve), so the job set is the maps' attrs the request can carry.
_IDENTITY_TRACK_ATTRS = frozenset(TRACK_CLAIM_FIELDS.values())
_IDENTITY_JOB_ATTRS = frozenset(JOB_CLAIM_FIELDS.values()).intersection(JobUpdateRequest.model_fields)


def _apply_job_fields(job: Job, req: JobUpdateRequest) -> bool:
    job_fields = req.model_dump(exclude_unset=True, exclude={"tracks"})
    job_identity = {k: v for k, v in job_fields.items() if k in _IDENTITY_JOB_ATTRS}
    for key, value in job_fields.items():
        if key not in _IDENTITY_JOB_ATTRS:
            setattr(job, key, value)
    return record_manual_job(job, job_identity) if job_identity else False


def _apply_track_edit(job: Job, track: Track, edit: TrackEditRequest) -> bool:
    identity_touched = False
    data = edit.model_dump(exclude_unset=True, exclude={"track_id", "revert_fields"})
    identity = {k: v for k, v in data.items() if k in _IDENTITY_TRACK_ATTRS}
    for key, value in data.items():
        if key not in _IDENTITY_TRACK_ATTRS:
            setattr(track, key, value)
    if identity and record_manual_track(job, track, identity):
        identity_touched = True
    if edit.revert_fields:
        revert_manual_track(job, track.source_ref, edit.revert_fields)
        identity_touched = True
    return identity_touched


async def _apply_track_edits(db: AsyncSession, job: Job, edits: list[TrackEditRequest]) -> tuple[list[str], bool]:
    identity_touched = False
    edited_track_ids: list[str] = []
    rows = list((await db.execute(select(Track).where(col(Track.job_id) == job.id))).scalars().all())
    by_id = {t.id: t for t in rows}
    # Duplicate track_ids in req.tracks → last-wins (idempotent setattr);
    # track.updated is emitted once per track (de-duplicated below).
    # Callers needn't deduplicate.
    for edit in edits:
        track = by_id.get(edit.track_id)
        if track is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"unknown track_id {edit.track_id} for job {job.id}",
            )
        if _apply_track_edit(job, track, edit):
            identity_touched = True
        db.add(track)
        edited_track_ids.append(track.id)
    return edited_track_ids, identity_touched


async def _emit_track_updates(
    db: AsyncSession, hub: WSHub, job_id: str, edited_track_ids: list[str], resolver_track_ids: frozenset[str]
) -> None:
    # De-duplicated, stable order: the tracks the request itself edited,
    # followed by any sibling the resolver also changed (e.g. a claim that
    # was never applied until this PATCH ran the resolver) -- resolver-only
    # changes still need a track.updated.
    for tid in list(dict.fromkeys([*edited_track_ids, *sorted(resolver_track_ids)])):
        await hub.emit(
            topic="ripper.events",
            event_type="track.updated",
            payload={"track_id": tid, "job_id": job_id},
            job_id=job_id,
            track_id=tid,
            session=db,
        )


async def apply_manual_edits(
    db: AsyncSession,
    job: Job,
    req: JobUpdateRequest,
    *,
    hub: WSHub,
    stage_runner: EpisodeStageRunner | None,
) -> None:
    before_identity = identity_snapshot(job)

    job_identity_touched = _apply_job_fields(job, req)
    db.add(job)

    edited_track_ids: list[str] = []
    track_identity_touched = False
    if req.tracks is not None:
        edited_track_ids, track_identity_touched = await _apply_track_edits(db, job, req.tracks)

    resolver_track_ids: frozenset[str] = frozenset()
    if job_identity_touched or track_identity_touched:
        outcome = await resolve_job(db, job)
        resolver_track_ids = outcome.track_ids
    await db.flush()
    await _emit_track_updates(db, hub, job.id, edited_track_ids, resolver_track_ids)
    await db.commit()
    await db.refresh(job)
    if stage_runner is not None and identity_snapshot(job) != before_identity:
        stage_runner.schedule(job.id)
