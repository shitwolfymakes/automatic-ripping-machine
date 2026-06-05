"""Pre-flight media_status check on POST /api/jobs/manual.

The ripper sends a heartbeat with the drive's CDROM_DRIVE_STATUS reading;
the backend stores it on `drives.media_status` + `media_status_at`. This
endpoint refuses clicks made against a drive whose latest reading was
NO_DISC / TRAY_OPEN / NOT_READY / UNAVAILABLE — so the user gets a 400
at click-time instead of a doomed identify landing an empty scan_result.

Stale rows (older than _MEDIA_STATUS_FRESHNESS) are treated as "we don't
know" and the request goes through.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import jobs as jobs_router  # noqa: E402
from arm_common import Drive, DriveMediaStatus, DriveStatus, User  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


class _CapturingHub:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def emit(
        self,
        topic: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        persist: bool = True,
        job_id: str | None = None,
        track_id: str | None = None,
        session: Any = None,
    ) -> None:
        self.events.append({"topic": topic, "event_type": event_type, "payload": payload})


def _make_app(signing_key: bytes, db: FakeSession, hub: _CapturingHub) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.ws_hub = hub
    app.include_router(jobs_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed(
    db: FakeSession,
    *,
    media_status: DriveMediaStatus | None,
    media_status_at: datetime | None,
) -> None:
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows["drives"] = [
        Drive(
            id="drv_x",
            hostname="ripper-host",
            device_path="/dev/sr0",
            display_name=None,
            status=DriveStatus.ONLINE,
            default_session_id=None,
            media_status=media_status,
            media_status_at=media_status_at,
        )
    ]
    db.rows["jobs"] = []


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def test_loaded_disc_passes_through(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db, media_status=DriveMediaStatus.LOADED, media_status_at=_now_utc())
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.post("/api/jobs/manual", json={"drive_id": "drv_x"}, headers=_auth(token))
    assert r.status_code == 202, r.text
    # WS event was emitted to the ripper.
    assert any(evt["event_type"] == "manual.trigger" for evt in hub.events)


@pytest.mark.parametrize(
    "media_status,expected_detail_substring",
    [
        (DriveMediaStatus.NO_DISC, "no disc"),
        (DriveMediaStatus.TRAY_OPEN, "tray is open"),
        (DriveMediaStatus.NOT_READY, "spinning up"),
        (DriveMediaStatus.UNAVAILABLE, "device node is gone"),
    ],
)
def test_not_loaded_returns_400(
    signing_key: bytes, media_status: DriveMediaStatus, expected_detail_substring: str
) -> None:
    db = FakeSession()
    _seed(db, media_status=media_status, media_status_at=_now_utc())
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.post("/api/jobs/manual", json={"drive_id": "drv_x"}, headers=_auth(token))
    assert r.status_code == 400, r.text
    assert expected_detail_substring in r.json()["detail"]
    # No WS emit — request is rejected before the manual.trigger goes out.
    assert not any(evt["event_type"] == "manual.trigger" for evt in hub.events)


def test_unknown_status_passes_through(signing_key: bytes) -> None:
    """UNKNOWN comes from drives whose CDROM ioctl is unsupported (rare,
    test rigs). Don't gate the click on a state we can't interpret."""
    db = FakeSession()
    _seed(db, media_status=DriveMediaStatus.UNKNOWN, media_status_at=_now_utc())
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.post("/api/jobs/manual", json={"drive_id": "drv_x"}, headers=_auth(token))
    assert r.status_code == 202, r.text


def test_stale_status_passes_through(signing_key: bytes) -> None:
    """If the heartbeat is older than _MEDIA_STATUS_FRESHNESS we don't
    know the current state — let identify do the talking."""
    db = FakeSession()
    _seed(
        db,
        media_status=DriveMediaStatus.NO_DISC,
        media_status_at=_now_utc() - timedelta(minutes=10),
    )
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.post("/api/jobs/manual", json={"drive_id": "drv_x"}, headers=_auth(token))
    assert r.status_code == 202, r.text


def test_drive_with_no_heartbeat_yet_passes_through(signing_key: bytes) -> None:
    """Brand-new ripper that hasn't sent its first heartbeat — the
    NULL/None columns should not block manual-trigger."""
    db = FakeSession()
    _seed(db, media_status=None, media_status_at=None)
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.post("/api/jobs/manual", json={"drive_id": "drv_x"}, headers=_auth(token))
    assert r.status_code == 202, r.text
