"""System preflight / paths / stats. Read-only operator diagnostics.
Ports neu's system/preflight + system/paths + system/stats, adapted to v3."""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.config import settings
from arm_backend.db import get_session
from arm_backend.seeders import CONFIG_SINGLETON_ID
from arm_common import Config, Drive, DriveStatus, Event, Job, User
from arm_common.schemas import (
    PathsResponse,
    PathStatus,
    PreflightCheck,
    PreflightResponse,
    StatsResponse,
)

router = APIRouter(prefix="/api/system", tags=["system"])

_WORST = {"ok": 0, "warning": 1, "error": 2}
_REQUIRED_ROOTS = {"MEDIA_ROOT", "RAW_ROOT", "LOG_DIR"}


def _roots(request: Request) -> dict[str, str]:
    injected: dict[str, str] | None = getattr(request.app.state, "system_paths", None)
    if injected is not None:
        return injected
    # LOG_DIR is the fixed `/logs` mount throughout v3 (see logs.py /
    # log_tailer.py) — convention-over-config, not a Settings field.
    return {
        "MEDIA_ROOT": settings.MEDIA_ROOT,
        "RAW_ROOT": settings.RAW_ROOT,
        "ISO_INGRESS_ROOT": settings.ISO_INGRESS_ROOT,
        "LOG_DIR": "/logs",
    }


def _path_status(name: str, path: str) -> PathStatus:
    exists = os.path.isdir(path)
    writable = exists and os.access(path, os.W_OK)
    return PathStatus(name=name, path=path, exists=exists, writable=writable)


@router.get("/preflight", response_model=PreflightResponse)
async def preflight(
    request: Request,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> PreflightResponse:
    checks: list[PreflightCheck] = []

    cfg = (await db.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    checks.append(
        PreflightCheck(
            name="config",
            status="ok" if cfg is not None else "error",
            detail=None if cfg is not None else "config singleton missing",
        )
    )

    for name, path in _roots(request).items():
        ps = _path_status(name, path)
        if ps.exists and ps.writable:
            checks.append(PreflightCheck(name=name, status="ok"))
        else:
            sev = "error" if name in _REQUIRED_ROOTS else "warning"
            checks.append(
                PreflightCheck(name=name, status=sev, detail=f"{path}: exists={ps.exists} writable={ps.writable}")
            )

    drives = list((await db.execute(select(Drive).where(col(Drive.status) == DriveStatus.ONLINE))).scalars().all())
    checks.append(
        PreflightCheck(
            name="drives",
            status="ok" if drives else "warning",
            detail=None if drives else "no online drives registered",
        )
    )

    overall = "ok"
    for ch in checks:
        if _WORST[ch.status] > _WORST[overall]:
            overall = ch.status
    return PreflightResponse(status=overall, checks=checks)


@router.get("/paths", response_model=PathsResponse)
async def paths(request: Request, _: User = Depends(require_jwt)) -> PathsResponse:
    return PathsResponse(paths=[_path_status(name, path) for name, path in _roots(request).items()])


@router.get("/stats", response_model=StatsResponse)
async def stats(
    request: Request,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> StatsResponse:
    started_at = getattr(request.app.state, "started_at", None)
    uptime = int((datetime.now(timezone.utc) - started_at).total_seconds()) if started_at is not None else 0

    jobs = list((await db.execute(select(Job))).scalars().all())
    by_status: dict[str, int] = {}
    for j in jobs:
        key = j.status.value if hasattr(j.status, "value") else str(j.status)
        by_status[key] = by_status.get(key, 0) + 1

    drives_online = len(
        list((await db.execute(select(Drive).where(col(Drive.status) == DriveStatus.ONLINE))).scalars().all())
    )

    # Fetch all events and filter in Python — mirrors the notification_dispatcher
    # pattern to stay compatible with the in-memory FakeSession (which cannot
    # evaluate .is_(None) clauses).
    all_events = list((await db.execute(select(Event))).scalars().all())
    events_unsent = len([e for e in all_events if e.notified_at is None])

    return StatsResponse(
        uptime_seconds=uptime,
        jobs_by_status=by_status,
        drives_online=drives_online,
        events_unsent=events_unsent,
    )
