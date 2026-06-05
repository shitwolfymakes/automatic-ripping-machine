"""POST /api/ripper/heartbeat — service-token-gated, writes
media_status / media_status_at / last_seen_at on the drive row."""

from __future__ import annotations

import os
import secrets

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.routers import ripper as ripper_router  # noqa: E402
from arm_common import Drive, DriveMediaStatus, DriveStatus  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _make_app(db: FakeSession) -> FastAPI:
    app = FastAPI()
    app.include_router(ripper_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    return app


def _service_auth() -> dict[str, str]:
    return {"Authorization": "Bearer tok-service"}


def _seed(db: FakeSession) -> Drive:
    drive = Drive(
        id="drv_x",
        hostname="ripper-host",
        device_path="/dev/sr0",
        display_name=None,
        status=DriveStatus.ONLINE,
        default_session_id=None,
        media_status=None,
        media_status_at=None,
    )
    db.rows["drives"] = [drive]
    return drive


def test_heartbeat_persists_media_status() -> None:
    db = FakeSession()
    drive = _seed(db)
    app = _make_app(db)
    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/heartbeat",
            json={"drive_id": "drv_x", "media_status": "loaded"},
            headers=_service_auth(),
        )
    assert r.status_code == 204, r.text
    assert drive.media_status == DriveMediaStatus.LOADED
    assert drive.media_status_at is not None
    # last_seen_at also bumped (no separate liveness ping needed).
    assert drive.last_seen_at == drive.media_status_at


def test_heartbeat_unknown_drive_returns_404() -> None:
    db = FakeSession()
    db.rows["drives"] = []
    app = _make_app(db)
    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/heartbeat",
            json={"drive_id": "drv_missing", "media_status": "loaded"},
            headers=_service_auth(),
        )
    assert r.status_code == 404


def test_heartbeat_requires_service_token() -> None:
    db = FakeSession()
    _seed(db)
    app = _make_app(db)
    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/heartbeat",
            json={"drive_id": "drv_x", "media_status": "loaded"},
        )
    assert r.status_code in (401, 403)
