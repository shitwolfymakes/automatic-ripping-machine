"""GET /api/drives/diagnostic: lifecycle-aware notes, container state, scanner
and ripper-manager health (Plan 6 task 2)."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import drives as drives_router  # noqa: E402
from arm_common import Config, Drive, DriveLifecycle, DriveStatus, User  # noqa: E402
from arm_common.enums import DriveIdentityKind, DriveMediaStatus  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


class _StubScanner:
    def __init__(self, *, last_scan_at=None, last_error=None, disk_root: Path | None = None) -> None:
        self.last_scan_at = last_scan_at
        self.last_error = last_error
        self._disk_root = disk_root

    @property
    def disk_root(self) -> Path | None:
        return self._disk_root


class _StubManager:
    def __init__(self, *, host_paths=True, probe=(True, None), statuses=None) -> None:
        self._host_paths = host_paths
        self._probe = probe
        self._statuses = statuses or {}

    def host_paths_set(self) -> bool:
        return self._host_paths

    def probe(self):
        return self._probe

    def container_statuses(self, drive_ids):
        return {d: self._statuses.get(d, ("missing", None)) for d in drive_ids}


def _app(
    db: FakeSession, signing_key: bytes, *, scanner: _StubScanner | None, manager: _StubManager | None
) -> tuple[TestClient, dict[str, str]]:
    db.rows.setdefault("users", [])
    if not any(isinstance(u, User) and u.id == "usr_admin" for u in db.rows["users"]):
        db.rows["users"].append(User(id="usr_admin", username="admin", password_hash="x", password_must_change=False))
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.drive_scanner = scanner
    app.state.ripper_manager = manager
    app.include_router(drives_router.router)

    async def _s() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _s
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return TestClient(app), {"Authorization": f"Bearer {token}"}


def _drive(
    lifecycle: DriveLifecycle,
    *,
    id: str = "drv_1",
    present: bool = True,
    status: DriveStatus = DriveStatus.ONLINE,
    media_status: DriveMediaStatus | None = None,
    media_status_at: datetime | None = None,
    last_error: str | None = None,
    last_seen_at: datetime | None = None,
    identity_kind: DriveIdentityKind | None = DriveIdentityKind.BY_ID,
    serial: str | None = "AAAABBBB000E",
    by_id_name: str | None = "usb-PIONEER_BD-RW_BDR-S12JX_AAAABBBB000E-0:0",
) -> Drive:
    return Drive(
        id=id,
        hostname=f"scan-{id}",
        device_path="/dev/sr0",
        status=status,
        lifecycle=lifecycle,
        present=present,
        media_status=media_status,
        media_status_at=media_status_at,
        last_error=last_error,
        last_seen_at=last_seen_at,
        identity_kind=identity_kind,
        serial=serial,
        by_id_name=by_id_name,
    )


def _get(client, auth):
    r = client.get("/api/drives/diagnostic", headers=auth)
    assert r.status_code == 200, r.text
    return r.json()


def test_enrolled_healthy_drive_has_no_notes(signing_key, tmp_path) -> None:
    now = datetime.now(timezone.utc)
    db = FakeSession()
    db.rows["drives"] = [_drive(DriveLifecycle.ENROLLED, media_status=DriveMediaStatus.NO_DISC, media_status_at=now)]
    (tmp_path / "by-id").mkdir()
    client, auth = _app(
        db,
        signing_key,
        scanner=_StubScanner(last_scan_at=now, disk_root=tmp_path),
        manager=_StubManager(statuses={"drv_1": ("running", True)}),
    )
    with client:
        body = _get(client, auth)
    d = body["drives"][0]
    assert d["healthy"] is True and d["notes"] == [] and d["container"] == "running" and d["lifecycle"] == "enrolled"
    assert body["system"] == []


@pytest.mark.parametrize(
    ("row_kw", "container", "expect"),
    [
        (
            dict(status=DriveStatus.OFFLINE, present=False, media_status=DriveMediaStatus.DETACHED),
            ("running", True),
            "drive is detached — reconnect it",
        ),
        (dict(status=DriveStatus.OFFLINE, present=True), ("running", True), "ripper heartbeat is stale"),
        (
            dict(status=DriveStatus.ERROR, last_error="identity mismatch: x"),
            ("running", True),
            "error: identity mismatch: x",
        ),
        (dict(), ("missing", None), "no ripper container — restart the backend or re-enroll"),
        (dict(), ("exited", True), "ripper container is not running"),
        (
            dict(),
            ("running", False),
            "ripper runs an older image — it is recreated at the next backend restart while idle",
        ),
        (dict(), ("unknown", None), "cannot inspect the ripper container"),
        (
            dict(identity_kind=DriveIdentityKind.PORT, serial=None, by_id_name=None),
            ("running", True),
            "no by-id link — identified by port; a replug on another port creates a new drive",
        ),
    ],
)
def test_enrolled_notes(signing_key, tmp_path, row_kw, container, expect) -> None:
    now = datetime.now(timezone.utc)
    db = FakeSession()
    base_kw = {"media_status": DriveMediaStatus.NO_DISC, "media_status_at": now}
    base_kw.update(row_kw)
    db.rows["drives"] = [_drive(DriveLifecycle.ENROLLED, **base_kw)]
    (tmp_path / "by-id").mkdir()
    client, auth = _app(
        db,
        signing_key,
        scanner=_StubScanner(last_scan_at=now, disk_root=tmp_path),
        manager=_StubManager(statuses={"drv_1": container}),
    )
    with client:
        d = _get(client, auth)["drives"][0]
    assert expect in d["notes"] and d["healthy"] is False


def test_detected_and_ignored_rows(signing_key, tmp_path) -> None:
    now = datetime.now(timezone.utc)
    db = FakeSession()
    db.rows["drives"] = [
        _drive(DriveLifecycle.DETECTED, id="drv_d", present=False, last_seen_at=now - timedelta(days=1)),
        _drive(DriveLifecycle.DETECTED, id="drv_p", present=True),
        _drive(DriveLifecycle.IGNORED, id="drv_i"),
    ]
    (tmp_path / "by-id").mkdir()
    client, auth = _app(
        db, signing_key, scanner=_StubScanner(last_scan_at=now, disk_root=tmp_path), manager=_StubManager()
    )
    with client:
        by_id = {d["id"]: d for d in _get(client, auth)["drives"]}
    assert by_id["drv_d"]["healthy"] is False and any(
        n.startswith("not connected since") for n in by_id["drv_d"]["notes"]
    )
    assert by_id["drv_p"]["healthy"] is True
    assert "not enrolled — enroll it on the Drives page to rip with it" in by_id["drv_p"]["notes"]
    assert by_id["drv_i"] == {**by_id["drv_i"], "healthy": True, "notes": ["ignored"], "container": None}


def test_detected_never_connected_uses_not_connected(signing_key, tmp_path) -> None:
    now = datetime.now(timezone.utc)
    db = FakeSession()
    db.rows["drives"] = [_drive(DriveLifecycle.DETECTED, id="drv_never", present=False, last_seen_at=None)]
    (tmp_path / "by-id").mkdir()
    client, auth = _app(
        db, signing_key, scanner=_StubScanner(last_scan_at=now, disk_root=tmp_path), manager=_StubManager()
    )
    with client:
        d = _get(client, auth)["drives"][0]
    assert "not connected" in d["notes"]
    assert not any(n.startswith("not connected since") for n in d["notes"])


def test_system_notes(signing_key, tmp_path) -> None:
    db = FakeSession()
    db.rows["config"] = [
        Config(
            id=1,
            drive_scan_interval_seconds=10,
            drive_detected_prune_days=7,
            community_keydb_enabled=True,
            makemkv_sdf_enabled=True,
        )
    ]
    client, auth = _app(db, signing_key, scanner=None, manager=None)
    with client:
        body = _get(client, auth)
    assert "drive scanner is not running" in body["system"]
    assert "ripper manager is not running — enroll is unavailable" in body["system"]

    old = datetime.now(timezone.utc) - timedelta(seconds=120)
    client, auth = _app(
        db,
        signing_key,
        scanner=_StubScanner(last_scan_at=old, last_error="OSError: boom", disk_root=tmp_path),
        manager=_StubManager(host_paths=False),
    )
    with client:
        body = _get(client, auth)
    assert any(
        s.startswith("last scan was ") and s.endswith("s ago — the scanner may be stuck") for s in body["system"]
    )
    assert "last scan failed: OSError: boom" in body["system"]
    assert "/host-disk/by-id is not mounted — drives cannot be identified" in body["system"]
    assert "ripper manager disabled: ARM_HOST_*_PATH not set" in body["system"]

    client, auth = _app(
        db,
        signing_key,
        scanner=_StubScanner(last_scan_at=datetime.now(timezone.utc), disk_root=tmp_path),
        manager=_StubManager(probe=(False, "image arm-ripper:latest not present on docker host")),
    )
    (tmp_path / "by-id").mkdir(exist_ok=True)
    with client:
        body = _get(client, auth)
    assert "ripper manager: image arm-ripper:latest not present on docker host" in body["system"]
