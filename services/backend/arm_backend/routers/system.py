"""System preflight / paths / stats. Read-only operator diagnostics.
Ports neu's system/preflight + system/paths + system/stats, adapted to v3."""

import importlib.metadata
import os
from datetime import datetime, timezone

import psutil  # type: ignore[import-untyped]

from arm_backend.disk_usage_cache import get_disk_usage

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.config import settings
from arm_backend.db import get_session
from arm_backend.makemkv_status import makemkv_state_detail
from arm_backend.seeders import CONFIG_SINGLETON_ID
from arm_common import Config, Drive, DriveStatus, Event, Job, KeydbState, MakemkvSdfState, User
from arm_common.schemas import (
    MemoryInfo,
    PathsResponse,
    PathStatus,
    PreflightCheck,
    PreflightResponse,
    StatsResponse,
    StorageRoot,
    SystemResourcesResponse,
    SystemVersionResponse,
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

    mk_valid = cfg.makemkv_key_valid if cfg is not None else None
    mk_state = cfg.makemkv_key_state if cfg is not None else None
    if mk_valid is True:
        mk_status, mk_detail = "ok", makemkv_state_detail("valid")
    elif mk_valid is False:
        mk_status, mk_detail = "error", (makemkv_state_detail(mk_state) or "MakeMKV key invalid")
    else:
        mk_status, mk_detail = "warning", "MakeMKV key not yet validated by a ripper"
    checks.append(PreflightCheck(name="makemkv_key", status=mk_status, detail=mk_detail))

    kdb_state = cfg.community_keydb_state if cfg is not None else None
    kdb_count = cfg.community_keydb_vuk_count if cfg is not None else None
    # Compare against KeydbState members (StrEnum, so they equal the stored
    # VARCHAR) rather than bare strings — a renamed member then fails at import
    # instead of silently falling through to the "not yet checked" branch.
    if kdb_state in (KeydbState.OK, KeydbState.FRESH_KEPT):
        kdb_status = "ok"
        kdb_detail = f"{kdb_count} VUK keys installed" if kdb_count else "keydb present"
    elif kdb_state == KeydbState.DISABLED:
        kdb_status, kdb_detail = "ok", "community keydb disabled"
    elif kdb_state in (KeydbState.DOWNLOAD_FAILED, KeydbState.EMPTY, KeydbState.PROBE_FAILED):
        kdb_status, kdb_detail = "warning", "community keydb unavailable; using last keydb if any"
    else:  # None — never reported by a ripper yet
        kdb_status, kdb_detail = "warning", "community keydb not yet checked by a ripper"
    checks.append(PreflightCheck(name="community_keydb", status=kdb_status, detail=kdb_detail))

    sdf_state = cfg.makemkv_sdf_state if cfg is not None else None
    if sdf_state in (MakemkvSdfState.UPDATED, MakemkvSdfState.FRESH_KEPT):
        sdf_status_v, sdf_detail = "ok", "SDF present"
    elif sdf_state == MakemkvSdfState.DISABLED:
        sdf_status_v, sdf_detail = "ok", "SDF refresh disabled (baked SDF in use)"
    elif sdf_state in (MakemkvSdfState.DOWNLOAD_FAILED, MakemkvSdfState.PROBE_FAILED):
        sdf_status_v, sdf_detail = "warning", "SDF refresh failed; using baked/last SDF"
    else:  # None — never reported by a ripper yet
        sdf_status_v, sdf_detail = "warning", "SDF not yet checked by a ripper"
    checks.append(PreflightCheck(name="makemkv_sdf", status=sdf_status_v, detail=sdf_detail))

    dispatcher = getattr(request.app.state, "transcode_dispatcher", None)
    if dispatcher is None:
        tc_status, tc_detail = "warning", "transcoder disabled: docker socket unavailable"
    elif not dispatcher.host_paths_set():
        tc_status, tc_detail = "warning", "transcoder disabled: ARM_HOST_*_PATH not set"
    else:
        tc_status, tc_detail = "ok", None
    checks.append(PreflightCheck(name="transcoder", status=tc_status, detail=tc_detail))

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
    for name, path in _roots(request).items():
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


def _app_version() -> str:
    try:
        return importlib.metadata.version("arm_backend")
    except importlib.metadata.PackageNotFoundError:
        return "0.0.0+unknown"


@router.get("/version", response_model=SystemVersionResponse)
async def system_version(_: User = Depends(require_jwt)) -> SystemVersionResponse:
    return SystemVersionResponse(version=_app_version())
