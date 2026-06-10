"""GET /api/system/preflight, /paths, /stats."""

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
from arm_backend.routers import system as system_router  # noqa: E402
from arm_common import Config, DiscType, Drive, DriveStatus, Event, Job, JobStatus, User  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession) -> None:
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows["config"] = [Config(id=1)]
    db.rows["drives"] = [
        Drive(id="drv_on0000000000000000000001", hostname="h1", device_path="/dev/sr0", status=DriveStatus.ONLINE),
        Drive(id="drv_off000000000000000000002", hostname="h2", device_path="/dev/sr1", status=DriveStatus.OFFLINE),
    ]
    db.rows["jobs"] = [
        Job(id="job_0000000000000000000000001", drive_id="drv_on0000000000000000000001",
            disc_type=DiscType.DVD, status=JobStatus.RIPPING),
        Job(id="job_0000000000000000000000002", drive_id="drv_on0000000000000000000001",
            disc_type=DiscType.DVD, status=JobStatus.RIPPED),
    ]
    db.rows["events"] = [
        Event(id="evt_0000000000000000000000001", event_type="rip.completed", notified_at=None),
        Event(id="evt_0000000000000000000000002", event_type="rip.completed",
              notified_at=datetime.now(timezone.utc)),
    ]


def _make_app(signing_key: bytes, db: FakeSession, *, ingress_ok: bool, tmp) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.started_at = datetime.now(timezone.utc) - timedelta(seconds=42)
    media = tmp / "media"; media.mkdir()
    raw = tmp / "raw"; raw.mkdir()
    logs = tmp / "logs"; logs.mkdir()
    ingress = tmp / "ingress"
    if ingress_ok:
        ingress.mkdir()
    app.state.system_paths = {
        "MEDIA_ROOT": str(media),
        "RAW_ROOT": str(raw),
        "LOG_DIR": str(logs),
        "ISO_INGRESS_ROOT": str(ingress),
    }
    app.include_router(system_router.router)

    async def _override() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def test_preflight_ok(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["status"] in {"ok", "warning"}
    names = {ch["name"] for ch in r.json()["checks"]}
    assert "MEDIA_ROOT" in names


def test_preflight_missing_ingress_is_warning(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, ingress_ok=False, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    assert r.status_code == 200, r.text
    ingress = next(ch for ch in r.json()["checks"] if ch["name"] == "ISO_INGRESS_ROOT")
    assert ingress["status"] == "warning"


def test_preflight_missing_required_root_is_error(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    # Point MEDIA_ROOT at a non-existent dir.
    app.state.system_paths["MEDIA_ROOT"] = str(tmp_path / "does-not-exist")
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "error"
    media = next(ch for ch in r.json()["checks"] if ch["name"] == "MEDIA_ROOT")
    assert media["status"] == "error"


def test_paths_shape(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/paths", headers=_auth(token))
    assert r.status_code == 200, r.text
    media = next(p for p in r.json()["paths"] if p["name"] == "MEDIA_ROOT")
    assert media["exists"] is True and media["writable"] is True


def test_stats_counts(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/stats", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["uptime_seconds"] >= 40
    assert body["drives_online"] == 1
    assert body["events_unsent"] == 1
    assert body["jobs_by_status"].get("ripping") == 1


def test_preflight_no_drives_is_warning(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["drives"] = []
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    assert r.status_code == 200, r.text
    drives = next(ch for ch in r.json()["checks"] if ch["name"] == "drives")
    assert drives["status"] == "warning"


def test_preflight_unauthenticated_401(signing_key: bytes, tmp_path) -> None:
    db = FakeSession()
    _seed(db)
    app, _ = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/preflight")
    assert r.status_code == 401


def test_preflight_config_missing_is_error(signing_key: bytes, tmp_path) -> None:
    """If the config singleton is absent, the config check should be 'error'."""
    db = FakeSession()
    _seed(db)
    db.rows["config"] = []
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/system/preflight", headers=_auth(token))
    assert r.status_code == 200, r.text
    cfg_check = next(ch for ch in r.json()["checks"] if ch["name"] == "config")
    assert cfg_check["status"] == "error"
    assert r.json()["status"] == "error"


def test_stats_no_started_at(signing_key: bytes, tmp_path) -> None:
    """When started_at is not set on app.state, uptime_seconds should be 0."""
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, ingress_ok=True, tmp=tmp_path)
    del app.state.started_at
    with TestClient(app) as c:
        r = c.get("/api/system/stats", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["uptime_seconds"] == 0


def test_paths_uses_settings_fallback(signing_key: bytes) -> None:
    """When system_paths is absent from app.state, _roots falls back to settings."""
    db = FakeSession()
    _seed(db)
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(system_router.router)

    async def _override() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override
    token, _ = issue_access_token("usr_admin", "admin", signing_key)

    with TestClient(app) as c:
        r = c.get("/api/system/paths", headers=_auth(token))
    assert r.status_code == 200, r.text
    names = {p["name"] for p in r.json()["paths"]}
    # settings defaults include MEDIA_ROOT, RAW_ROOT, ISO_INGRESS_ROOT, LOG_DIR
    assert "MEDIA_ROOT" in names
