"""The system routes: diagnostics report, stats, resources, version and the TheDiscDB refresh."""

import functools
import importlib.metadata
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil  # type: ignore[import-untyped]

from arm_backend.disk_usage_cache import get_disk_usage

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, func, select

from arm_backend.auth import require_jwt, require_writer
from arm_backend.config import settings
from arm_backend.db import get_session
from arm_backend.constants import CONFIG_SINGLETON_ID
from arm_backend.identity.sources.thediscdb_snapshot import RefreshBusy, refresh as thediscdb_refresh
from arm_backend.identity.sources.thediscdb_snapshot import refresh_running as thediscdb_refresh_running
from arm_backend.system_diagnostics import collect_diagnostics, online_enrolled_drives, system_roots
from arm_common import (
    Config,
    Event,
    Job,
    User,
)
from arm_common.schemas import (
    MemoryInfo,
    StatsResponse,
    StorageRoot,
    SystemDiagnosticsResponse,
    SystemResourcesResponse,
    SystemVersionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/diagnostics", response_model=SystemDiagnosticsResponse)
async def diagnostics(
    request: Request,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> SystemDiagnosticsResponse:
    return await collect_diagnostics(request, db)


@router.get("/stats", response_model=StatsResponse)
async def stats(
    request: Request,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> StatsResponse:
    started_at = getattr(request.app.state, "started_at", None)
    uptime = int((datetime.now(timezone.utc) - started_at).total_seconds()) if started_at is not None else 0

    by_status: dict[str, int] = {}
    for job_status, n in (await db.execute(select(Job.status, func.count()).group_by(col(Job.status)))).all():
        key = job_status.value if hasattr(job_status, "value") else str(job_status)
        by_status[key] = n

    drives_online = len(await online_enrolled_drives(db))

    events_unsent = (
        await db.execute(select(func.count()).select_from(Event).where(col(Event.notified_at).is_(None)))
    ).scalar_one()

    return StatsResponse(
        uptime_seconds=uptime,
        jobs_by_status=by_status,
        drives_online=drives_online,
        events_unsent=events_unsent,
    )


_GiB = 1073741824
_CPU_TEMP_KEYS = ("coretemp", "cpu_thermal", "k10temp")


def _cpu_temp() -> float:
    try:
        temps = psutil.sensors_temperatures()
    except AttributeError, OSError:
        return 0.0
    for key in _CPU_TEMP_KEYS:
        readings = temps.get(key)
        if readings:
            return float(readings[0].current)
    return 0.0


@router.get("/resources", response_model=SystemResourcesResponse)
async def resources(
    request: Request,
    _: User = Depends(require_jwt),
) -> SystemResourcesResponse:
    cpu_percent = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()
    memory = MemoryInfo(
        total_gb=round(mem.total / _GiB, 1),
        used_gb=round(mem.used / _GiB, 1),
        free_gb=round(mem.available / _GiB, 1),
        percent=mem.percent,
    )
    storage: list[StorageRoot] = []
    for name, path in system_roots(request).items():
        usage = get_disk_usage(path)
        if usage is None:
            continue
        storage.append(
            StorageRoot(
                name=name,
                path=path,
                total_gb=round(usage["total"] / _GiB, 1),
                used_gb=round(usage["used"] / _GiB, 1),
                free_gb=round(usage["free"] / _GiB, 1),
                percent=usage["percent"],
            )
        )
    return SystemResourcesResponse(
        cpu_percent=cpu_percent,
        cpu_temp=_cpu_temp(),
        memory=memory,
        storage=storage,
    )


# The canonical release version lives in the repo-root VERSION file, baked
# into the image at /app/VERSION; the workspace member's pyproject pins a
# static 0.0.0, so importlib.metadata is only a last resort. Resolution:
# ARM_VERSION env > VERSION file > package metadata > sentinel.
_VERSION_FILE_CANDIDATES: tuple[Path, ...] = (
    Path("/app/VERSION"),
    Path(__file__).resolve().parents[4] / "VERSION",  # repo root (dev checkout)
)


@functools.cache
def _app_version() -> str:
    env = os.environ.get("ARM_VERSION")
    if env:
        return env.strip()
    for candidate in _VERSION_FILE_CANDIDATES:
        try:
            text = candidate.read_text().strip()
        except OSError:
            continue
        if text:
            return text
    try:
        return importlib.metadata.version("arm_backend")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0+unknown"


@router.get("/version", response_model=SystemVersionResponse)
async def system_version(_: User = Depends(require_jwt)) -> SystemVersionResponse:
    return SystemVersionResponse(version=_app_version())


@router.post("/thediscdb/refresh", dependencies=[Depends(require_writer)])
async def thediscdb_refresh_now(request: Request, session: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    """Rebuild the TheDiscDB snapshot index from GitHub, on demand."""
    if thediscdb_refresh_running():
        raise HTTPException(status_code=409, detail="thediscdb refresh already in progress")
    try:
        count = await thediscdb_refresh(request.app.state.http, Path(settings.ARM_THEDISCDB_PATH))
    except RefreshBusy as e:
        # The daily loop took the lock between the check above and the call.
        raise HTTPException(status_code=409, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001 — network/tar/sqlite: report, keep old index
        raise HTTPException(status_code=502, detail=f"thediscdb refresh failed: {e}") from e
    now = datetime.now(timezone.utc)
    cfg = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one()
    cfg.thediscdb_refreshed_at = now
    session.add(cfg)
    await session.commit()
    return {"discs": count, "refreshed_at": now.isoformat()}
