"""Naming variables catalog + per-job filename preview. Reuses the
transcode_apply.compute_outputs resolver so previews never drift from actual
output. Ports neu's naming/variables + jobs/{id}/naming-preview."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.routers._params import JobIdParam
from arm_backend.auth import require_jwt
from arm_backend.db import get_session
from arm_backend.path_template import TemplateValidationError, tokens_for_media
from arm_backend.transcode_apply import compute_outputs
from arm_common import Job, Session, Track, TranscodePreset, User
from arm_common.enums import MediaType
from arm_common.schemas import (
    JobNamingPreviewResponse,
    NamingPreviewItem,
    NamingVariable,
    NamingVariablesResponse,
)

router = APIRouter(tags=["naming"])


@router.get("/api/naming/variables", response_model=NamingVariablesResponse)
async def naming_variables(
    media_type: MediaType | None = None,
    _: User = Depends(require_jwt),
) -> NamingVariablesResponse:
    types = [media_type] if media_type is not None else list(MediaType)
    variables = {mt.value: [NamingVariable(**tok) for tok in tokens_for_media(mt)] for mt in types}
    return NamingVariablesResponse(variables=variables)


@router.get("/api/jobs/{job_id}/naming-preview", response_model=JobNamingPreviewResponse)
async def job_naming_preview(
    job_id: JobIdParam,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> JobNamingPreviewResponse:
    job = (await db.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown job_id: {job_id}")

    # pending_session_id is stored in metadata_json (set by the ripper at scan time)
    session_id: str | None = (job.metadata_json or {}).get("pending_session_id")
    sess: Session | None = None
    if session_id is not None:
        sess = (await db.execute(select(Session).where(col(Session.id) == session_id))).scalar_one_or_none()
    if sess is None or not sess.output_path_template:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="job has no output template")

    # Resolve the session's transcode preset (may be None — compute_outputs then
    # leaves {transcode_slug}/{ext} empty, which validate_template already
    # forbids for non-iso templates that reference them). Mirrors auto_session.py.
    transcode_preset: TranscodePreset | None = None
    if sess.transcode_preset_id is not None:
        transcode_preset = (
            await db.execute(select(TranscodePreset).where(col(TranscodePreset.id) == sess.transcode_preset_id))
        ).scalar_one_or_none()

    tracks = list((await db.execute(select(Track).where(col(Track.job_id) == job_id))).scalars().all())

    try:
        resolved = compute_outputs(job, tracks, sess, transcode_preset)
    except TemplateValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    items = [NamingPreviewItem(track_id=r.track_id, filename=r.output_path) for r in resolved]
    return JobNamingPreviewResponse(items=items)
