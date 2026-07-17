"""System diagnostics. Read-only operator health report.

Everything the backend can fix silently, it fixes (missing root dirs are
created at startup and re-ensured before every read — see `ensure_roots`);
this endpoint reports only what cannot be healed from inside a container:
a mount that is read-only or wrong-owner (v3 never chowns user mounts —
docs/arch/06-deployment.md), no rippers registered yet, a missing config
row. The ported UI's settings System-Health panel and first-run wizard
render it (Tier-12)."""

import functools
import importlib.metadata
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.db import get_session
from arm_backend.makemkv_status import makemkv_state_detail
from arm_backend.seeders import CONFIG_SINGLETON_ID
from arm_backend.utils import default_roots
from arm_common import Config, Drive, DriveStatus, Event, Job, User
from arm_common.schemas import (
    PathStatus,
    StatsResponse,
    SystemDiagnosticCheck,
    SystemDiagnosticsResponse,
    SystemVersionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system"])

_WORST = {"ok": 0, "warning": 1, "error": 2}
_REQUIRED_ROOTS = {"MEDIA_ROOT", "RAW_ROOT", "LOG_DIR"}


def _roots(request: Request) -> dict[str, str]:
    injected: dict[str, str] | None = getattr(request.app.state, "system_paths", None)
    if injected is not None:
        return injected
    return default_roots()


def _path_status(name: str, path: str) -> PathStatus:
    exists = os.path.isdir(path)
    writable = exists and os.access(path, os.W_OK)
    return PathStatus(name=name, path=path, exists=exists, writable=writable)


@router.get("/diagnostics", response_model=SystemDiagnosticsResponse)
async def diagnostics(
    request: Request,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> SystemDiagnosticsResponse:
    roots = _roots(request)
    # Heal-on-read: the report never shows a problem the backend could
    # have fixed itself.
    # ensure_roots(roots)
    # DO NOT heal-on-read. These should be guaranteed at launch so if any are missing
    # then that is an error we want to surface when this endpoint is hit.
    # TODO: implement a check for missing roots (low priority, most processes will
    # surface this error)

    checks: list[SystemDiagnosticCheck] = []

    cfg = (await db.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    checks.append(
        SystemDiagnosticCheck(
            name="config",
            status="ok" if cfg is not None else "error",
            detail=None if cfg is not None else "config singleton missing",
        )
    )

    paths: list[PathStatus] = []
    for name, path in roots.items():
        ps = _path_status(name, path)
        paths.append(ps)
        if ps.exists and ps.writable:
            checks.append(SystemDiagnosticCheck(name=name, status="ok"))
        else:
            sev = "error" if name in _REQUIRED_ROOTS else "warning"
            checks.append(
                SystemDiagnosticCheck(
                    name=name, status=sev, detail=f"{path}: exists={ps.exists} writable={ps.writable}"
                )
            )

    drives = list((await db.execute(select(Drive).where(col(Drive.status) == DriveStatus.ONLINE))).scalars().all())
    checks.append(
        SystemDiagnosticCheck(
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
    checks.append(SystemDiagnosticCheck(name="makemkv_key", status=mk_status, detail=mk_detail))

    dispatcher = getattr(request.app.state, "transcode_dispatcher", None)
    if dispatcher is None:
        tc_status, tc_detail = "warning", "transcoder disabled: docker socket unavailable"
    elif not dispatcher.host_paths_set():
        tc_status, tc_detail = "warning", "transcoder disabled: ARM_HOST_*_PATH not set"
    else:
        tc_status, tc_detail = "ok", None
    checks.append(SystemDiagnosticCheck(name="transcoder", status=tc_status, detail=tc_detail))

    overall = "ok"
    for ch in checks:
        if _WORST[ch.status] > _WORST[overall]:
            overall = ch.status
    return SystemDiagnosticsResponse(status=overall, checks=checks, paths=paths)


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
