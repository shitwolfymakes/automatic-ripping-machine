"""System diagnostics. Read-only operator health report.

Everything the backend can fix silently, it fixes (missing root dirs are
created at startup and re-ensured before every read — see `ensure_roots`);
this endpoint reports only what cannot be healed from inside a container:
a mount that is read-only or wrong-owner (v3 never chowns user mounts —
docs/arch/06-deployment.md), no rippers registered yet, a missing config
row. The ported UI's settings System-Health panel and first-run wizard
render it (Tier-12)."""

import logging
import os

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.config import settings
from arm_backend.db import get_session
from arm_backend.seeders import CONFIG_SINGLETON_ID
from arm_common import Config, Drive, DriveStatus, User
from arm_common.schemas import (
    SystemDiagnosticCheck,
    SystemDiagnosticsResponse,
    PathStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["system"])

_WORST = {"ok": 0, "warning": 1, "error": 2}
_REQUIRED_ROOTS = {"MEDIA_ROOT", "RAW_ROOT", "LOG_DIR"}


def default_roots() -> dict[str, str]:
    # LOG_DIR is the fixed `/logs` mount throughout v3 (see logs.py /
    # log_tailer.py) — convention-over-config, not a Settings field.
    return {
        "MEDIA_ROOT": settings.MEDIA_ROOT,
        "RAW_ROOT": settings.RAW_ROOT,
        "LOG_DIR": "/logs",
    }


def _roots(request: Request) -> dict[str, str]:
    injected: dict[str, str] | None = getattr(request.app.state, "system_paths", None)
    if injected is not None:
        return injected
    return default_roots()


def ensure_roots(roots: dict[str, str]) -> None:
    """Silently create any missing root dir. Never raises: a broken mount
    must not crash-loop the API (the container entrypoint's writability
    guard owns the fatal cases); the failure stays visible as
    exists=False in the diagnostics report."""
    for name, path in roots.items():
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as exc:
            logger.warning("cannot create %s (%s): %s", name, path, exc)


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

    overall = "ok"
    for ch in checks:
        if _WORST[ch.status] > _WORST[overall]:
            overall = ch.status
    return SystemDiagnosticsResponse(status=overall, checks=checks, paths=paths)
