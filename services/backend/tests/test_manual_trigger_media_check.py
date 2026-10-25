"""Pre-flight media_status check on POST /api/jobs/manual.

The ripper sends a heartbeat with the drive's CDROM_DRIVE_STATUS reading;
the backend stores it on `drives.media_status` + `media_status_at`. This
endpoint refuses clicks made against a drive whose latest reading was
NO_DISC / TRAY_OPEN / NOT_READY / UNAVAILABLE — so the user gets a 400
at click-time instead of a doomed identify landing an empty scan_result.

A row without a heartbeat inside _MEDIA_STATUS_FRESHNESS means no ripper
is listening, a detached drive has nothing to rip from, and a ripper that
owns any live job drops the trigger: each of those is a 409 with a detail
the DriveCard can show (D-241).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any


import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from arm_backend.db import get_session
from arm_backend.jwt_utils import issue_access_token
from arm_backend.routers import jobs as jobs_router
from arm_common import DiscType, Drive, DriveMediaStatus, DriveStatus, Job, JobStatus, User
from arm_common.enums import NON_TERMINAL_JOB_STATUSES

from tests._fakes import FakeSession


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
    present: bool = True,
    job_status: JobStatus | None = None,
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
            present=present,
        )
    ]
    db.rows["jobs"] = []
    if job_status is not None:
        db.rows["jobs"].append(
            Job(
                id="job_01JZXR7K3M5Q8N4VWA00000001",
                drive_id="drv_x",
                disc_type=DiscType.DVD,
                status=job_status,
                metadata_json={},
                resumed_from_crash=False,
            )
        )


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
        (DriveMediaStatus.DETACHED, "detached"),
        (DriveMediaStatus.UNAVAILABLE, "could not be opened"),
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


def test_stale_heartbeat_returns_409(signing_key: bytes) -> None:
    """A heartbeat older than _MEDIA_STATUS_FRESHNESS means the ripper
    stopped beating: nobody would act on the trigger, even if the last
    reading still says `loaded`."""
    db = FakeSession()
    _seed(
        db,
        media_status=DriveMediaStatus.LOADED,
        media_status_at=_now_utc() - timedelta(minutes=10),
    )
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.post("/api/jobs/manual", json={"drive_id": "drv_x"}, headers=_auth(token))
    assert r.status_code == 409, r.text
    assert "ripper is offline" in r.json()["detail"]
    assert "last heartbeat 600s ago" in r.json()["detail"]
    assert not any(evt["event_type"] == "manual.trigger" for evt in hub.events)


def test_drive_with_no_heartbeat_yet_returns_409(signing_key: bytes) -> None:
    """A row no ripper has ever reported on (detected but not enrolled, or
    a ripper that has not come up yet) has no listener for the trigger."""
    db = FakeSession()
    _seed(db, media_status=None, media_status_at=None)
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.post("/api/jobs/manual", json={"drive_id": "drv_x"}, headers=_auth(token))
    assert r.status_code == 409, r.text
    assert "ripper is offline (no heartbeat yet)" in r.json()["detail"]
    assert not any(evt["event_type"] == "manual.trigger" for evt in hub.events)


def test_detached_drive_returns_409(signing_key: bytes) -> None:
    """`present` is False once the heartbeat reports DETACHED (or the
    scanner stops seeing an unenrolled node); that outranks a fresh
    reading, the same way the DriveCard shows it."""
    db = FakeSession()
    _seed(db, media_status=DriveMediaStatus.LOADED, media_status_at=_now_utc(), present=False)
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.post("/api/jobs/manual", json={"drive_id": "drv_x"}, headers=_auth(token))
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == "the drive is not connected"
    assert not any(evt["event_type"] == "manual.trigger" for evt in hub.events)


@pytest.mark.parametrize("job_status", sorted(NON_TERMINAL_JOB_STATUSES, key=str))
def test_live_job_returns_409(signing_key: bytes, job_status: JobStatus) -> None:
    """The ripper ignores a trigger while it owns any job, not only a
    RIPPING one, so every non-terminal status is refused up front."""
    db = FakeSession()
    _seed(db, media_status=DriveMediaStatus.LOADED, media_status_at=_now_utc(), job_status=job_status)
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.post("/api/jobs/manual", json={"drive_id": "drv_x"}, headers=_auth(token))
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == f"the drive already has a job in progress ({job_status.value})"
    assert not any(evt["event_type"] == "manual.trigger" for evt in hub.events)


def test_finished_job_does_not_block(signing_key: bytes) -> None:
    """A terminal job on the drive is history, not ownership: the trigger
    goes out."""
    db = FakeSession()
    _seed(db, media_status=DriveMediaStatus.LOADED, media_status_at=_now_utc(), job_status=JobStatus.RIPPED)
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.post("/api/jobs/manual", json={"drive_id": "drv_x"}, headers=_auth(token))
    assert r.status_code == 202, r.text
    assert any(evt["event_type"] == "manual.trigger" for evt in hub.events)
