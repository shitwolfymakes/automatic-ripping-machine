"""System diagnostics. Read-only operator health report.

Everything the backend can fix silently, it fixes (missing root dirs are
created at startup and re-ensured before every read — see `ensure_roots`);
this endpoint reports only what cannot be healed from inside a container:
a mount that is read-only or wrong-owner (v3 never chowns user mounts —
docs/developers/architecture/06-deployment.md), no rippers registered yet, a missing config
row. The settings System-Health panel and the first-run walkthrough
render it."""

import asyncio
import os

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.config import effective_transcode_capable, settings
from arm_backend.constants import CONFIG_SINGLETON_ID
from arm_backend.makemkv_status import makemkv_state_detail
from arm_backend.ripper_manager import RipperManager
from arm_backend.transcode_dispatcher import TranscodeDispatcher
from arm_backend.transcode_queue import count_queued_encode_tasks
from arm_backend.utils import default_roots
from arm_common import (
    Config,
    Drive,
    DriveKind,
    DriveLifecycle,
    DriveStatus,
    KeydbState,
    MakemkvSdfState,
)
from arm_common.schemas import (
    DiagnosticDetail,
    PathStatus,
    SystemDiagnosticCheck,
    SystemDiagnosticsResponse,
)

_WORST = {"ok": 0, "warning": 1, "error": 2}
_REQUIRED_ROOTS = {"MEDIA_ROOT", "RAW_ROOT", "LOG_DIR"}


def system_roots(request: Request) -> dict[str, str]:
    injected: dict[str, str] | None = getattr(request.app.state, "system_paths", None)
    if injected is not None:
        return injected
    return default_roots()


# Host-side bind source for each container root, so the report can print the
# exact `chown` the operator runs on the server.
_HOST_PATH_SETTING = {
    "MEDIA_ROOT": "ARM_HOST_MEDIA_PATH",
    "RAW_ROOT": "ARM_HOST_RAW_PATH",
    "LOG_DIR": "ARM_HOST_LOGS_PATH",
}


def _path_status(name: str, path: str) -> PathStatus:
    exists = os.path.isdir(path)
    writable = exists and os.access(path, os.W_OK)
    setting = _HOST_PATH_SETTING.get(name)
    host = (getattr(settings, setting, "") or None) if setting else None
    return PathStatus(
        name=name, path=path, exists=exists, writable=writable, host_path=host, uid=os.getuid(), gid=os.getgid()
    )


def _docker_details(image_label: str, ok: bool, detail: str | None) -> list[DiagnosticDetail]:
    """Split one docker probe result into socket + image rows for the UI. The
    probe reports a single message, so an image problem is told apart by its
    wording; anything else is a daemon/socket problem."""
    if ok:
        return [DiagnosticDetail(label="Docker socket", ok=True), DiagnosticDetail(label=image_label, ok=True)]
    if "image" in (detail or "").lower():
        return [
            DiagnosticDetail(label="Docker socket", ok=True),
            DiagnosticDetail(label=image_label, ok=False, message=detail),
        ]
    return [DiagnosticDetail(label="Docker socket", ok=False, message=detail)]


def _config_check(cfg: Config | None) -> SystemDiagnosticCheck:
    return SystemDiagnosticCheck(
        name="config",
        status="ok" if cfg is not None else "error",
        detail=None if cfg is not None else "config singleton missing",
    )


def _path_checks(roots: dict[str, str]) -> tuple[list[PathStatus], list[SystemDiagnosticCheck]]:
    paths: list[PathStatus] = []
    checks: list[SystemDiagnosticCheck] = []
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
    return paths, checks


def _drives_check(drives: list[Drive]) -> SystemDiagnosticCheck:
    return SystemDiagnosticCheck(
        name="drives",
        status="ok" if drives else "warning",
        detail=None if drives else "no online drives registered",
    )


def _makemkv_key_check(cfg: Config | None) -> SystemDiagnosticCheck:
    mk_valid = cfg.makemkv_key_valid if cfg is not None else None
    mk_state = cfg.makemkv_key_state if cfg is not None else None
    if mk_valid is True:
        mk_status, mk_detail = "ok", makemkv_state_detail("valid")
    elif mk_valid is False:
        mk_status, mk_detail = "error", (makemkv_state_detail(mk_state) or "MakeMKV key invalid")
    else:
        mk_status, mk_detail = "warning", "MakeMKV key not yet validated by a ripper"
    return SystemDiagnosticCheck(name="makemkv_key", status=mk_status, detail=mk_detail)


# Table keys are KeydbState members. A StrEnum member hashes and compares equal
# to its value, so a lookup with the stored VARCHAR finds them, and a renamed
# member fails at import instead of silently falling through to the default.
_KEYDB_STATUS: dict[str | None, tuple[str, str]] = {
    KeydbState.DISABLED: ("ok", "community keydb disabled"),
    KeydbState.DOWNLOAD_FAILED: ("warning", "community keydb unavailable; using last keydb if any"),
    KeydbState.EMPTY: ("warning", "community keydb unavailable; using last keydb if any"),
    KeydbState.PROBE_FAILED: ("warning", "community keydb unavailable; using last keydb if any"),
}
# None, or any state not in the table: never reported by a ripper yet.
_KEYDB_DEFAULT = ("warning", "community keydb not yet checked by a ripper")

_SDF_STATUS: dict[str | None, tuple[str, str]] = {
    MakemkvSdfState.UPDATED: ("ok", "SDF present"),
    MakemkvSdfState.FRESH_KEPT: ("ok", "SDF present"),
    MakemkvSdfState.DISABLED: ("ok", "SDF refresh disabled (baked SDF in use)"),
    MakemkvSdfState.DOWNLOAD_FAILED: ("warning", "SDF refresh failed; using baked/last SDF"),
    MakemkvSdfState.PROBE_FAILED: ("warning", "SDF refresh failed; using baked/last SDF"),
}
# None, or any state not in the table: never reported by a ripper yet.
_SDF_DEFAULT = ("warning", "SDF not yet checked by a ripper")


def _keydb_check(cfg: Config | None) -> SystemDiagnosticCheck:
    kdb_state = cfg.community_keydb_state if cfg is not None else None
    kdb_count = cfg.community_keydb_vuk_count if cfg is not None else None
    if kdb_state in (KeydbState.OK, KeydbState.FRESH_KEPT):
        # The detail depends on the VUK count, so these two stay out of the table.
        kdb_status = "ok"
        kdb_detail = f"{kdb_count} VUK keys installed" if kdb_count else "keydb present"
    else:
        kdb_status, kdb_detail = _KEYDB_STATUS.get(kdb_state, _KEYDB_DEFAULT)
    return SystemDiagnosticCheck(name="community_keydb", status=kdb_status, detail=kdb_detail)


def _sdf_check(cfg: Config | None) -> SystemDiagnosticCheck:
    sdf_state = cfg.makemkv_sdf_state if cfg is not None else None
    sdf_status_v, sdf_detail = _SDF_STATUS.get(sdf_state, _SDF_DEFAULT)
    return SystemDiagnosticCheck(name="makemkv_sdf", status=sdf_status_v, detail=sdf_detail)


async def _ripper_only_status(db: AsyncSession) -> tuple[str, str | None]:
    # Ripper-only is a supported deployment, not a degraded one: the
    # dispatcher runs without a docker client by design, so reporting its
    # (absent) container path as a warning would be permanent noise.
    tc_status, tc_detail = "ok", "ripper-only deployment (transcoding not installed)"
    held = await count_queued_encode_tasks(db)
    if held:
        # Queued before the box went ripper-only (or swept back to
        # QUEUED): spawn_pending holds them with nothing to run them.
        tc_status = "warning"
        tc_detail = (
            f"ripper-only deployment: {held} queued encode task(s) are held; "
            "re-run setup without --ripper-only to resume them, or delete them"
        )
    return tc_status, tc_detail


async def _probed_transcoder_status(dispatcher: TranscodeDispatcher) -> tuple[str, str | None, list[DiagnosticDetail]]:
    # probe() pings a possibly-remote ssh docker host; run it off the
    # event loop so a slow/unreachable host doesn't block the server.
    ok, detail = await asyncio.to_thread(dispatcher.probe)
    tc_details = _docker_details("Transcode image", ok, detail)
    if not ok:
        return "warning", detail, tc_details
    if dispatcher.last_spawn_error:
        return "warning", f"last spawn failed: {dispatcher.last_spawn_error}", tc_details
    if dispatcher.backend_url_warning:
        return (
            "warning",
            f"{dispatcher.backend_url_warning} (ARM_TRANSCODE_BACKEND_URL_CHECK=warn: spawning anyway)",
            tc_details,
        )
    return "ok", None, tc_details


async def _transcoder_status(
    dispatcher: TranscodeDispatcher | None, db: AsyncSession
) -> tuple[str, str | None, list[DiagnosticDetail]]:
    if not effective_transcode_capable(settings):
        tc_status, tc_detail = await _ripper_only_status(db)
        return tc_status, tc_detail, []
    if dispatcher is None:
        return "warning", "transcoder dispatcher not running", []
    if not dispatcher.host_paths_set():
        return "warning", "transcoder disabled: ARM_HOST_*_PATH not set", []
    return await _probed_transcoder_status(dispatcher)


def _transcoder_location() -> tuple[str, str | None]:
    remote = settings.ARM_TRANSCODE_DOCKER_HOST or ""
    if not effective_transcode_capable(settings):
        return "none", None
    if remote:
        return "remote", remote.removeprefix("ssh://").split("/", 1)[0] or None
    return "local", None


async def _transcoder_check(dispatcher: TranscodeDispatcher | None, db: AsyncSession) -> SystemDiagnosticCheck:
    tc_status, tc_detail, tc_details = await _transcoder_status(dispatcher, db)
    location, remote_host = _transcoder_location()
    return SystemDiagnosticCheck(
        name="transcoder",
        status=tc_status,
        detail=tc_detail,
        details=tc_details,
        location=location,
        remote_host=remote_host,
    )


async def _ripper_manager_check(manager: RipperManager | None) -> SystemDiagnosticCheck:
    rm_detail: str | None
    if manager is None:
        rm_status, rm_detail = "warning", "ripper manager disabled: docker socket unavailable"
        rm_details = [DiagnosticDetail(label="Docker socket", ok=False, message="docker socket unavailable")]
    elif not manager.host_paths_set():
        rm_status, rm_detail = "warning", "ripper manager disabled: ARM_HOST_*_PATH not set"
        rm_details = [DiagnosticDetail(label="Host paths", ok=False, message="ARM_HOST_*_PATH not set")]
    else:
        ok, detail = await asyncio.to_thread(manager.probe)
        rm_details = _docker_details("Ripper image", ok, detail)
        if not ok:
            rm_status, rm_detail = "warning", detail
        else:
            rm_status, rm_detail = "ok", None
    return SystemDiagnosticCheck(name="ripper_manager", status=rm_status, detail=rm_detail, details=rm_details)


def _worst_status(checks: list[SystemDiagnosticCheck]) -> str:
    overall = "ok"
    for ch in checks:
        if _WORST[ch.status] > _WORST[overall]:
            overall = ch.status
    return overall


async def collect_diagnostics(request: Request, db: AsyncSession) -> SystemDiagnosticsResponse:
    """The diagnostics report, reusable by the setup router's system-step reconciliation."""
    roots = system_roots(request)
    # Heal-on-read: the report never shows a problem the backend could
    # have fixed itself.
    # ensure_roots(roots)
    # DO NOT heal-on-read. These should be guaranteed at launch so if any are missing
    # then that is an error we want to surface when this endpoint is hit.
    # TODO: implement a check for missing roots (low priority, most processes will
    # surface this error)

    checks: list[SystemDiagnosticCheck] = []

    cfg = (await db.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    checks.append(_config_check(cfg))

    paths, path_checks = _path_checks(roots)
    checks.extend(path_checks)

    drives = await online_enrolled_drives(db)
    checks.append(_drives_check(drives))
    checks.append(_makemkv_key_check(cfg))
    checks.append(_keydb_check(cfg))
    checks.append(_sdf_check(cfg))

    dispatcher = getattr(request.app.state, "transcode_dispatcher", None)
    checks.append(await _transcoder_check(dispatcher, db))

    manager = getattr(request.app.state, "ripper_manager", None)
    checks.append(await _ripper_manager_check(manager))

    return SystemDiagnosticsResponse(status=_worst_status(checks), checks=checks, paths=paths)


async def online_enrolled_drives(db: AsyncSession) -> list[Drive]:
    """Online drives a ripper actually serves.

    Scanner-created DETECTED rows and virtual ISO rows are ``online`` by default,
    so ``status`` alone would count a drive that is merely plugged in.
    """
    stmt = (
        select(Drive)
        .where(col(Drive.status) == DriveStatus.ONLINE)
        .where(col(Drive.kind) == DriveKind.OPTICAL)
        .where(col(Drive.lifecycle) == DriveLifecycle.ENROLLED)
    )
    return list((await db.execute(stmt)).scalars().all())
