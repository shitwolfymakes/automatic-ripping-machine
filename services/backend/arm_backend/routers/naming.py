"""Naming variables catalog + per-job filename preview. Reuses the
transcode_apply.compute_outputs resolver so previews never drift from actual
output. Ports neu's naming/variables + jobs/{id}/naming-preview."""

from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.routers._params import JobIdParam
from arm_backend.auth import require_jwt
from arm_backend.db import get_session
from arm_backend.path_sanitize import sanitize_path_component
from arm_backend.path_template import TemplateValidationError, tokens_for_media, validate_template_or_http
from arm_backend.transcode_apply import compute_outputs
from arm_common import Job, Session, Track, TranscodePreset, User
from arm_common.enums import MediaType
from arm_common.schemas import (
    JobNamingPreviewResponse,
    NamingPreviewItem,
    NamingValidateRequest,
    NamingValidateResponse,
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

    track_number_by_id = {t.id: t.index for t in tracks}
    items: list[NamingPreviewItem] = []
    for r in resolved:
        p = PurePosixPath(r.output_path)
        parent = str(p.parent)
        output_dir = "" if parent == "." else parent
        items.append(
            NamingPreviewItem(
                track_id=r.track_id,
                track_number=track_number_by_id.get(r.track_id),
                output_path=r.output_path,
                output_dir=output_dir,
                output_name=p.name,
            )
        )
    job_output_dir = items[0].output_dir if items else ""
    job_output_name = sanitize_path_component(job.title or "")
    return JobNamingPreviewResponse(
        job_output_dir=job_output_dir,
        job_output_name=job_output_name,
        items=items,
    )


@router.post("/api/naming/validate", response_model=NamingValidateResponse)
async def naming_validate(
    req: NamingValidateRequest,
    _: User = Depends(require_jwt),
) -> NamingValidateResponse:
    # validate_template_or_http raises HTTPException(422, detail=<message>) on
    # an invalid template; returns the synthetic expansion on success.
    validate_template_or_http(req.template, req.media_type, req.has_transcode_preset)
    return NamingValidateResponse(valid=True)
