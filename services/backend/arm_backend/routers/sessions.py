"""Session CRUD, clone, and template preview.

Built-in protection: `is_builtin=true` rows can be renamed (so users can
disambiguate "Plex 1080p" → "Plex 1080p (legacy)") but every other field is
locked, and `DELETE` is refused. Cloning a built-in is the supported escape
hatch and produces a fresh non-builtin row owned by the caller.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.db import get_session
from arm_backend.path_template import TemplateValidationError, validate_template, validate_template_or_http
from arm_common import Drive, RipPreset, Session, TranscodePreset, User
from arm_common.schemas import (
    SessionCloneRequest,
    SessionCreateRequest,
    SessionUpdateRequest,
    SessionView,
    TemplatePreviewRequest,
    TemplatePreviewResponse,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


async def _load_rip_preset(db: AsyncSession, rip_preset_id: str) -> RipPreset:
    rp = (await db.execute(select(RipPreset).where(col(RipPreset.id) == rip_preset_id))).scalar_one_or_none()
    if rp is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"unknown rip_preset_id: {rip_preset_id}")
    return rp


async def _load_transcode_preset(db: AsyncSession, transcode_preset_id: str | None) -> TranscodePreset | None:
    if transcode_preset_id is None:
        return None
    tp = (
        await db.execute(select(TranscodePreset).where(col(TranscodePreset.id) == transcode_preset_id))
    ).scalar_one_or_none()
    if tp is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown transcode_preset_id: {transcode_preset_id}",
        )
    return tp


@router.get("", response_model=list[SessionView])
async def list_sessions(
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> list[Session]:
    result = await db.execute(select(Session).order_by(col(Session.name).asc()))
    return list(result.scalars().all())


@router.get("/{session_id}", response_model=SessionView)
async def get_session_by_id(
    session_id: str,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> Session:
    row = (await db.execute(select(Session).where(col(Session.id) == session_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown session_id: {session_id}")
    return row


@router.post("", response_model=SessionView, status_code=status.HTTP_201_CREATED)
async def create_session(
    req: SessionCreateRequest,
    user: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> Session:
    rip_preset = await _load_rip_preset(db, req.rip_preset_id)
    if rip_preset.media_type != req.media_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"rip_preset.media_type={rip_preset.media_type.value} != session.media_type={req.media_type.value}",
        )
    transcode_preset = await _load_transcode_preset(db, req.transcode_preset_id)
    if transcode_preset is not None and transcode_preset.media_type != req.media_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"transcode_preset.media_type={transcode_preset.media_type.value} "
                f"!= session.media_type={req.media_type.value}"
            ),
        )

    try:
        validate_template(
            req.output_path_template,
            req.media_type,
            has_transcode_preset=transcode_preset is not None,
        )
    except TemplateValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    row = Session(
        name=req.name,
        media_type=req.media_type,
        is_builtin=False,
        rip_preset_id=req.rip_preset_id,
        transcode_preset_id=req.transcode_preset_id,
        output_path_template=req.output_path_template,
        overrides_json=req.overrides_json,
        created_by_user_id=user.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.patch("/{session_id}", response_model=SessionView)
async def update_session(
    session_id: str,
    req: SessionUpdateRequest,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> Session:
    row = (await db.execute(select(Session).where(col(Session.id) == session_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown session_id: {session_id}")

    fields = req.model_dump(exclude_unset=True)
    if row.is_builtin and set(fields.keys()) - {"name"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="built-in session: only `name` can be edited; clone it to customise",
        )

    new_rip_preset_id = fields.get("rip_preset_id", row.rip_preset_id)
    if "rip_preset_id" in fields:
        rp = await _load_rip_preset(db, new_rip_preset_id)
        if rp.media_type != row.media_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"rip_preset.media_type={rp.media_type.value} != session.media_type={row.media_type.value}",
            )

    new_transcode_preset_id: str | None
    if "transcode_preset_id" in fields:
        new_transcode_preset_id = fields["transcode_preset_id"]
    else:
        new_transcode_preset_id = row.transcode_preset_id
    transcode_preset = await _load_transcode_preset(db, new_transcode_preset_id)
    if transcode_preset is not None and transcode_preset.media_type != row.media_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"transcode_preset.media_type={transcode_preset.media_type.value} "
                f"!= session.media_type={row.media_type.value}"
            ),
        )

    new_template = fields.get("output_path_template", row.output_path_template)
    if "output_path_template" in fields or "transcode_preset_id" in fields:
        try:
            validate_template(
                new_template,
                row.media_type,
                has_transcode_preset=transcode_preset is not None,
            )
        except TemplateValidationError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    for key, value in fields.items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session_id: str,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> None:
    row = (await db.execute(select(Session).where(col(Session.id) == session_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown session_id: {session_id}")
    if row.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="cannot delete built-in session; clone it first",
        )

    referenced = (
        await db.execute(select(Drive.id, Drive.display_name).where(col(Drive.default_session_id) == session_id))
    ).all()
    if referenced:
        names = ", ".join(r.display_name or r.id for r in referenced)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"session is the default for drive(s): {names}",
        )

    await db.delete(row)
    await db.commit()


@router.post("/{session_id}/clone", response_model=SessionView, status_code=status.HTTP_201_CREATED)
async def clone_session(
    session_id: str,
    req: SessionCloneRequest,
    user: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> Session:
    src = (await db.execute(select(Session).where(col(Session.id) == session_id))).scalar_one_or_none()
    if src is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown session_id: {session_id}")

    clone = Session(
        name=req.name,
        media_type=src.media_type,
        is_builtin=False,
        rip_preset_id=src.rip_preset_id,
        transcode_preset_id=src.transcode_preset_id,
        output_path_template=src.output_path_template,
        overrides_json=dict(src.overrides_json) if src.overrides_json is not None else None,
        created_by_user_id=user.id,
    )
    db.add(clone)
    await db.commit()
    await db.refresh(clone)
    return clone


@router.post("/preview", response_model=TemplatePreviewResponse)
async def preview_template(
    req: TemplatePreviewRequest,
    _: User = Depends(require_jwt),
) -> TemplatePreviewResponse:
    expansion = validate_template_or_http(req.template, req.media_type, req.has_transcode_preset)
    return TemplatePreviewResponse(expansion=expansion)
