"""GPU inventory management — /api/gpus.

The `gpus` table is DB-authoritative (ARM_GPUS only seeds an empty table at
boot; see `main._refresh_gpu_inventory`), so this router is where operators
manage the inventory: list devices, flip the enabled switch, delete a row.
Deleting every row and restarting the backend re-seeds from the env
descriptor — the Settings > GPUs card documents that path.

Re-probing (`POST /api/gpus/{id}/probe`, `POST /api/gpus/probe`) schedules
the backend-spawned device probe (`gpu_probe_runner`) in the background and
returns 202; the row updates when `gpu.probed` arrives on `transcode.events`.

Reads need a session (any authenticated principal — the preset form's
inventory hint uses it); writes require the writer role like the rest of
the config surface.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt, require_writer
from arm_backend.db import get_session
from arm_backend.transcode_dispatcher import NO_DOCKER_CLIENT_DETAIL
from arm_common import Gpu, User
from arm_common.schemas import GpuProbeAllScheduled, GpuProbeScheduled, GpuUpdateRequest, GpuView

router = APIRouter(prefix="/api/gpus", tags=["gpus"])

_IN_USE_DETAIL = "gpu is in use by a running transcode"


def _capable_runner(request: Request) -> Any:
    """The app's GpuProbeRunner, or 409 when probes can't run here (no
    runner, or a deployment without a docker client for transcodes)."""
    runner = getattr(request.app.state, "gpu_probe_runner", None)
    if runner is None or not runner.capable():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=NO_DOCKER_CLIENT_DETAIL)
    return runner


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
    request: Request,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> GpuView:
    # Enabling a never-probed row also schedules its probe. When a probe can't
    # start (the row is busy or already being probed, or this host can't run
    # probes) the update still succeeds and the row stays unprobed.
    gpu =(await db.execute(select(Gpu).where(col(Gpu.id) == gpu_id))).scalar_one_or_none()
    if gpu is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="gpu not found")
    newly_enabled = body.enabled and not gpu.enabled
    gpu.enabled = body.enabled
    db.add(gpu)
    await db.commit()
    await db.refresh(gpu)
    if newly_enabled and gpu.probed_at is None:
        runner = getattr(request.app.state, "gpu_probe_runner", None)
        if runner is not None and runner.capable() and not runner.gpu_in_use(gpu):
            runner.start_probe(gpu_id)
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
            detail=_IN_USE_DETAIL,
        )
    await db.delete(gpu)
    await db.commit()


@router.post("/probe", status_code=status.HTTP_202_ACCEPTED, response_model=GpuProbeAllScheduled)
async def probe_all_gpus(
    request: Request,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> GpuProbeAllScheduled:
    """Re-probe every enabled row that isn't running a transcode. Rows already
    being probed are left to that probe and not listed."""
    runner = _capable_runner(request)
    gpus = (await db.execute(select(Gpu).order_by(col(Gpu.vendor), col(Gpu.device_path)))).scalars().all()
    scheduled = [g.id for g in gpus if g.enabled and not runner.gpu_in_use(g) and runner.start_probe(g.id)]
    return GpuProbeAllScheduled(scheduled=scheduled)


@router.post("/{gpu_id}/probe", status_code=status.HTTP_202_ACCEPTED, response_model=GpuProbeScheduled)
async def probe_gpu(
    gpu_id: str,
    request: Request,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> GpuProbeScheduled:
    """Re-probe one row (enabled or not: a disabled row may be re-probed
    before an operator turns it back on)."""
    gpu = (await db.execute(select(Gpu).where(col(Gpu.id) == gpu_id))).scalar_one_or_none()
    if gpu is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="gpu not found")
    runner = _capable_runner(request)
    if runner.gpu_in_use(gpu):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_IN_USE_DETAIL)
    if not runner.start_probe(gpu_id):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="gpu probe already running")
    return GpuProbeScheduled(scheduled=True)
