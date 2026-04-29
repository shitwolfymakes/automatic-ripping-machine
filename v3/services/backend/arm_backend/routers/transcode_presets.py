"""Transcode preset CRUD. Built-in protection mirrors sessions.py and rip_presets.py."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.db import get_session
from arm_common import MediaType, Session, TranscodePreset, User
from arm_common.schemas import (
    TranscodePresetCreateRequest,
    TranscodePresetUpdateRequest,
    TranscodePresetView,
)

router = APIRouter(prefix="/api/transcode-presets", tags=["transcode-presets"])


@router.get("", response_model=list[TranscodePresetView])
async def list_transcode_presets(
    media_type: MediaType | None = Query(default=None),
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> list[TranscodePreset]:
    stmt = select(TranscodePreset).order_by(col(TranscodePreset.name).asc())
    if media_type is not None:
        stmt = stmt.where(col(TranscodePreset.media_type) == media_type)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{preset_id}", response_model=TranscodePresetView)
async def get_transcode_preset(
    preset_id: str,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> TranscodePreset:
    row = (await db.execute(select(TranscodePreset).where(col(TranscodePreset.id) == preset_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown transcode_preset_id: {preset_id}")
    return row


@router.post("", response_model=TranscodePresetView, status_code=status.HTTP_201_CREATED)
async def create_transcode_preset(
    req: TranscodePresetCreateRequest,
    user: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> TranscodePreset:
    row = TranscodePreset(
        name=req.name,
        media_type=req.media_type,
        is_builtin=False,
        tool=req.tool,
        preset_ref=req.preset_ref,
        preset_json=req.preset_json,
        container=req.container,
        hw_preference=req.hw_preference,
        extra_args=req.extra_args,
        created_by_user_id=user.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.patch("/{preset_id}", response_model=TranscodePresetView)
async def update_transcode_preset(
    preset_id: str,
    req: TranscodePresetUpdateRequest,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> TranscodePreset:
    row = (await db.execute(select(TranscodePreset).where(col(TranscodePreset.id) == preset_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown transcode_preset_id: {preset_id}")

    fields = req.model_dump(exclude_unset=True)
    if row.is_builtin and set(fields.keys()) - {"name"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="built-in transcode preset: only `name` can be edited",
        )

    for key, value in fields.items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transcode_preset(
    preset_id: str,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> None:
    row = (await db.execute(select(TranscodePreset).where(col(TranscodePreset.id) == preset_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown transcode_preset_id: {preset_id}")
    if row.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="cannot delete built-in transcode preset",
        )

    refs = (
        await db.execute(select(Session.id, Session.name).where(col(Session.transcode_preset_id) == preset_id))
    ).all()
    if refs:
        names = ", ".join(r.name for r in refs)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"transcode preset is referenced by session(s): {names}",
        )

    await db.delete(row)
    await db.commit()
