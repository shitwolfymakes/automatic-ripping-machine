"""GPU inventory management — /api/gpus.

The `gpus` table is DB-authoritative (ARM_GPUS only seeds an empty table at
boot; see `main._refresh_gpu_inventory`), so this router is where operators
manage the inventory: list devices, flip the enabled switch, delete a row.
Deleting every row and restarting the backend re-seeds from the env
descriptor — the Settings > GPUs card documents that path.

Reads need a session (any authenticated principal — the preset form's
inventory hint uses it); writes require the writer role like the rest of
the config surface.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt, require_writer
from arm_backend.db import get_session
from arm_common import Gpu, User
from arm_common.schemas import GpuUpdateRequest, GpuView

router = APIRouter(prefix="/api/gpus", tags=["gpus"])


@router.get("", response_model=list[GpuView])
async def list_gpus(
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> list[GpuView]:
    gpus = (await db.execute(select(Gpu).order_by(col(Gpu.vendor), col(Gpu.device_path)))).scalars().all()
    return [GpuView.model_validate(g, from_attributes=True) for g in gpus]


@router.patch("/{gpu_id}", response_model=GpuView)
async def update_gpu(
    gpu_id: str,
    body: GpuUpdateRequest,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> GpuView:
    gpu = (await db.execute(select(Gpu).where(col(Gpu.id) == gpu_id))).scalar_one_or_none()
    if gpu is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="gpu not found")
    gpu.enabled = body.enabled
    db.add(gpu)
    await db.commit()
    await db.refresh(gpu)
    return GpuView.model_validate(gpu, from_attributes=True)


@router.delete("/{gpu_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_gpu(
    gpu_id: str,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> None:
    gpu = (await db.execute(select(Gpu).where(col(Gpu.id) == gpu_id))).scalar_one_or_none()
    if gpu is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="gpu not found")
    if gpu.claimed_by_task_id is not None:
        # A running transcode holds this device — deleting the row would
        # orphan the claim bookkeeping. Disable it instead, or wait.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="gpu is in use by a running transcode",
        )
    await db.delete(gpu)
    await db.commit()
