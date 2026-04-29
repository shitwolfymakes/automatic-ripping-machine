"""Rip preset CRUD. Built-in protection mirrors sessions.py.

`track_filters_json` is required iff `track_selection==CUSTOM`; the body is
validated against the `TrackFilters` Pydantic model before write so a
malformed JSON blob never reaches the rip pipeline.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.db import get_session
from arm_common import MediaType, RipPreset, Session, TrackSelection, User
from arm_common.schemas import (
    RipPresetCreateRequest,
    RipPresetUpdateRequest,
    RipPresetView,
    TrackFilters,
)

router = APIRouter(prefix="/api/rip-presets", tags=["rip-presets"])


def _validate_filters(track_selection: TrackSelection, track_filters_json: dict[str, object] | None) -> None:
    if track_selection == TrackSelection.CUSTOM:
        if track_filters_json is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="track_filters_json is required when track_selection=custom",
            )
        try:
            TrackFilters.model_validate(track_filters_json)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"invalid track_filters_json: {exc.errors()}",
            ) from exc
    else:
        if track_filters_json is not None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="track_filters_json is only allowed when track_selection=custom",
            )


@router.get("", response_model=list[RipPresetView])
async def list_rip_presets(
    media_type: MediaType | None = Query(default=None),
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> list[RipPreset]:
    stmt = select(RipPreset).order_by(col(RipPreset.name).asc())
    if media_type is not None:
        stmt = stmt.where(col(RipPreset.media_type) == media_type)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/{preset_id}", response_model=RipPresetView)
async def get_rip_preset(
    preset_id: str,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> RipPreset:
    row = (await db.execute(select(RipPreset).where(col(RipPreset.id) == preset_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown rip_preset_id: {preset_id}")
    return row


@router.post("", response_model=RipPresetView, status_code=status.HTTP_201_CREATED)
async def create_rip_preset(
    req: RipPresetCreateRequest,
    user: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> RipPreset:
    _validate_filters(req.track_selection, req.track_filters_json)
    row = RipPreset(
        name=req.name,
        media_type=req.media_type,
        is_builtin=False,
        track_selection=req.track_selection,
        identification_mode=req.identification_mode,
        output_mode=req.output_mode,
        track_filters_json=req.track_filters_json,
        created_by_user_id=user.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


@router.patch("/{preset_id}", response_model=RipPresetView)
async def update_rip_preset(
    preset_id: str,
    req: RipPresetUpdateRequest,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> RipPreset:
    row = (await db.execute(select(RipPreset).where(col(RipPreset.id) == preset_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown rip_preset_id: {preset_id}")

    fields = req.model_dump(exclude_unset=True)
    if row.is_builtin and set(fields.keys()) - {"name"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="built-in rip preset: only `name` can be edited; clone it via a new preset to customise",
        )

    new_track_selection = fields.get("track_selection", row.track_selection)
    new_filters = fields.get("track_filters_json", row.track_filters_json)
    if "track_selection" in fields or "track_filters_json" in fields:
        _validate_filters(new_track_selection, new_filters)

    for key, value in fields.items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return row


@router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_rip_preset(
    preset_id: str,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> None:
    row = (await db.execute(select(RipPreset).where(col(RipPreset.id) == preset_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown rip_preset_id: {preset_id}")
    if row.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="cannot delete built-in rip preset",
        )

    refs = (await db.execute(select(Session.id, Session.name).where(col(Session.rip_preset_id) == preset_id))).all()
    if refs:
        names = ", ".join(r.name for r in refs)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"rip preset is referenced by session(s): {names}",
        )

    await db.delete(row)
    await db.commit()
