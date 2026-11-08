"""Judges drive rows and the scanner and ripper manager for the diagnostic view."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from arm_backend.drive_scanner import DriveScanner, scan_tunables
from arm_backend.ripper_manager import RipperManager
from arm_common import Drive, DriveIdentityKind, DriveLifecycle, DriveStatus
from arm_common.schemas import DriveDiagnosticItem

# A drive whose last media-status update is older than this is considered
# stale (its ripper likely stopped heart-beating). Deliberately looser than the
# 90s manual-trigger pre-check window (jobs.py `_MEDIA_STATUS_FRESHNESS`): that
# gate fast-fails a rip on a momentarily-quiet drive, whereas this is an
# operator-facing health view that shouldn't flap on a single missed heartbeat.
_STALE_AFTER = timedelta(minutes=5)

_PORT_NOTE = "no by-id link, identified by port: a replug on another port creates a new drive"


def _aware(dt: datetime) -> datetime:
    """SQLite (and some drivers) hand back naive datetimes; everything here
    is compared against `datetime.now(timezone.utc)`, so treat naive as UTC —
    same convention as drive_scanner.reconcile_drives."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


_ContainerStatuses = dict[str, tuple[str, bool | None]]


def heartbeat_stale(at: datetime, now: datetime) -> bool:
    """True when a heartbeat timestamp is older than `_STALE_AFTER`."""
    return now - at > _STALE_AFTER


async def container_statuses(manager: RipperManager | None, drives: list[Drive]) -> _ContainerStatuses | None:
    """Ripper container state per enrolled drive; None without a manager."""
    if manager is None:
        return None
    enrolled_ids = [d.id for d in drives if d.lifecycle is DriveLifecycle.ENROLLED]
    return await asyncio.to_thread(manager.container_statuses, enrolled_ids)


def _container_finding(state: str, current: bool | None) -> tuple[str, str | None]:
    """The container value for a ripper container state, with its note (None when healthy)."""
    if state == "missing":
        return "missing", "no ripper container: restart the backend or re-enroll"
    if state == "unknown":
        return "unknown", "cannot inspect the ripper container"
    if state != "running":
        return state, "ripper container is not running"
    if current is False:
        return "stale-image", "ripper runs an older image: it is recreated at the next backend restart while idle"
    return "running", None


def _enrolled_findings(d: Drive, now: datetime, statuses: _ContainerStatuses | None) -> tuple[str | None, list[str]]:
    """Container value and notes for an enrolled drive; `statuses` is None without a manager."""
    notes: list[str] = []
    if d.media_status_at is None:
        notes.append("no media-status heartbeat recorded")
    elif heartbeat_stale(_aware(d.media_status_at), now):
        notes.append("media-status heartbeat is stale")
    if d.status is DriveStatus.OFFLINE:
        notes.append("drive is detached: reconnect it" if not d.present else "ripper heartbeat is stale")
    elif d.status is DriveStatus.ERROR:
        notes.append(f"error: {d.last_error or 'unknown'}")
    container: str | None = None
    if statuses is not None:
        state, current = statuses[d.id]
        container, note = _container_finding(state, current)
        if note is not None:
            notes.append(note)
    return container, notes


def _detected_findings(d: Drive) -> tuple[bool, list[str]]:
    """Healthy flag and notes for a detected (not enrolled) drive."""
    notes: list[str] = []
    if not d.present:
        seen = f"since {_aware(d.last_seen_at):%Y-%m-%d %H:%M} UTC" if d.last_seen_at else ""
        notes.append(f"not connected {seen}".rstrip())
    notes.append("not enrolled: enroll it on the Drives page to rip with it")
    return d.present, notes


def _diagnostic_item(d: Drive, container: str | None, healthy: bool, notes: list[str]) -> DriveDiagnosticItem:
    return DriveDiagnosticItem(
        id=d.id,
        lifecycle=d.lifecycle,
        present=d.present,
        identity_kind=d.identity_kind,
        device_path=d.device_path,
        status=d.status,
        media_status=d.media_status,
        media_status_at=d.media_status_at,
        container=container,
        last_error=d.last_error,
        healthy=healthy,
        notes=notes,
    )


def diagnose_drive(d: Drive, now: datetime, statuses: _ContainerStatuses | None) -> DriveDiagnosticItem:
    """Judge one drive row against the lifecycle model."""
    container: str | None = None
    if d.lifecycle is DriveLifecycle.ENROLLED:
        container, notes = _enrolled_findings(d, now, statuses)
        healthy = not notes
    elif d.lifecycle is DriveLifecycle.DETECTED:
        healthy, notes = _detected_findings(d)
    else:
        notes = ["ignored"]
        healthy = True
    if d.identity_kind is DriveIdentityKind.PORT:
        notes.append(_PORT_NOTE)
        if d.lifecycle is DriveLifecycle.ENROLLED:
            healthy = False
    return _diagnostic_item(d, container, healthy, notes)


async def scanner_findings(scanner: DriveScanner | None, db: AsyncSession, now: datetime) -> list[str]:
    """Health findings for the drive scanner and the host's by-id mount."""
    if scanner is None:
        return ["drive scanner is not running"]
    findings: list[str] = []
    if scanner.last_error:
        findings.append(f"last scan failed: {scanner.last_error}")
    interval, _prune_days = await scan_tunables(db)
    if scanner.last_scan_at is not None:
        age = int((now - _aware(scanner.last_scan_at)).total_seconds())
        if age > 3 * interval:
            findings.append(f"last scan was {age}s ago: the scanner may be stuck")
    if not (Path(scanner.disk_root) / "by-id").is_dir():
        findings.append("/host-disk/by-id is not mounted: drives cannot be identified")
    return findings


async def manager_findings(manager: RipperManager | None) -> list[str]:
    """Health findings for the ripper manager."""
    if manager is None:
        return ["ripper manager is not running: enroll is unavailable"]
    if not manager.host_paths_set():
        return ["ripper manager disabled: ARM_HOST_*_PATH not set"]
    ok, detail = await asyncio.to_thread(manager.probe)
    return [] if ok else [f"ripper manager: {detail}"]
