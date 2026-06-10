"""POST /api/drives/rescan + GET /api/drives/diagnostic (backend-side, no HW)."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import drives as drives_router  # noqa: E402
from arm_common import Drive, DriveStatus, User  # noqa: E402
from arm_common.enums import DriveMediaStatus  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession) -> None:
    now = datetime.now(timezone.utc)
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows["drives"] = [
        Drive(id="drv_frsh000000000000000000001", hostname="h1", device_path="/dev/sr0",
              status=DriveStatus.ONLINE, media_status=DriveMediaStatus.LOADED, media_status_at=now),
        Drive(id="drv_stal000000000000000000002", hostname="h2", device_path="/dev/sr1",
              status=DriveStatus.ONLINE, media_status=DriveMediaStatus.NO_DISC,
              media_status_at=now - timedelta(hours=2)),
    ]


def _make_app(signing_key: bytes, db: FakeSession) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(drives_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_diagnostic_reports_drives(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/drives/diagnostic", headers=_auth(token))
    assert r.status_code == 200, r.text
    by_id = {d["id"]: d for d in r.json()["drives"]}
    assert by_id["drv_frsh000000000000000000001"]["healthy"] is True
    assert by_id["drv_stal000000000000000000002"]["healthy"] is False
    assert by_id["drv_stal000000000000000000002"]["notes"]


def test_rescan_counts_online_and_stale(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post("/api/drives/rescan", headers=_auth(token))
    assert r.status_code == 200, r.text
    # Seed has exactly one fresh+ONLINE drive and one stale drive.
    assert r.json()["online"] == 1
    assert r.json()["stale"] == 1


def test_diagnostic_unauthenticated_401(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, _ = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/drives/diagnostic")
    assert r.status_code == 401


def test_diagnostic_drive_no_heartbeat(signing_key: bytes) -> None:
    """Drive with media_status_at=None → healthy=False, 'no media-status heartbeat' note."""
    db = FakeSession()
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows["drives"] = [
        Drive(id="drv_nohb000000000000000000003", hostname="h3", device_path="/dev/sr2",
              status=DriveStatus.ONLINE, media_status=None, media_status_at=None),
    ]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/drives/diagnostic", headers=_auth(token))
    assert r.status_code == 200, r.text
    item = r.json()["drives"][0]
    assert item["healthy"] is False
    assert any("heartbeat" in n for n in item["notes"])


def test_diagnostic_drive_offline_status(signing_key: bytes) -> None:
    """Drive with status != ONLINE → healthy=False, status note appended."""
    now = datetime.now(timezone.utc)
    db = FakeSession()
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows["drives"] = [
        Drive(id="drv_offl000000000000000000004", hostname="h4", device_path="/dev/sr3",
              status=DriveStatus.OFFLINE, media_status=DriveMediaStatus.UNAVAILABLE,
              media_status_at=now),
    ]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/drives/diagnostic", headers=_auth(token))
    assert r.status_code == 200, r.text
    item = r.json()["drives"][0]
    assert item["healthy"] is False
    assert any("offline" in n for n in item["notes"])


def test_rescan_unauthenticated_401(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, _ = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.post("/api/drives/rescan")
    assert r.status_code == 401


def test_list_drives_returns_all(signing_key: bytes) -> None:
    """GET /api/drives returns the full drive list."""
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/drives", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert len(r.json()) == 2
