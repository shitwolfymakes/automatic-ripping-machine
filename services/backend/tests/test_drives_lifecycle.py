"""Every legal transition in spec §1's diagram, and every illegal one -> 409."""

from __future__ import annotations

import os
import secrets

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import drives as drives_router  # noqa: E402
from arm_common import Drive, DriveLifecycle, DriveStatus, Job, JobStatus, User  # noqa: E402
from arm_common.enums import DiscType  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _app(db: FakeSession, signing_key: bytes) -> tuple[TestClient, dict[str, str]]:
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(drives_router.router)

    async def _s() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _s
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return TestClient(app), {"Authorization": f"Bearer {token}"}


def _drive(lifecycle: DriveLifecycle, present: bool = True) -> Drive:
    return Drive(
        id="drv_1",
        hostname="scan-sr0",
        device_path="/dev/sr0",
        status=DriveStatus.ONLINE,
        lifecycle=lifecycle,
        present=present,
    )


@pytest.mark.parametrize(
    ("start", "op", "end"),
    [
        (DriveLifecycle.DETECTED, "enroll", DriveLifecycle.ENROLLED),
        (DriveLifecycle.IGNORED, "enroll", DriveLifecycle.ENROLLED),
        (DriveLifecycle.DETECTED, "ignore", DriveLifecycle.IGNORED),
        (DriveLifecycle.IGNORED, "unignore", DriveLifecycle.DETECTED),
        (DriveLifecycle.ENROLLED, "unenroll", DriveLifecycle.DETECTED),
    ],
)
def test_legal_transitions(signing_key: bytes, start: DriveLifecycle, op: str, end: DriveLifecycle) -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive(start)]
    client, auth = _app(db, signing_key)
    with client:
        r = client.post(f"/api/drives/drv_1/{op}", headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["lifecycle"] == end.value
    assert db.rows["drives"][0].lifecycle is end


@pytest.mark.parametrize(
    ("start", "op"),
    [
        (DriveLifecycle.ENROLLED, "enroll"),
        (DriveLifecycle.ENROLLED, "ignore"),
        (DriveLifecycle.IGNORED, "ignore"),
        (DriveLifecycle.DETECTED, "unignore"),
        (DriveLifecycle.ENROLLED, "unignore"),
        (DriveLifecycle.DETECTED, "unenroll"),
        (DriveLifecycle.IGNORED, "unenroll"),
    ],
)
def test_illegal_transitions_are_409(signing_key: bytes, start: DriveLifecycle, op: str) -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive(start)]
    client, auth = _app(db, signing_key)
    with client:
        r = client.post(f"/api/drives/drv_1/{op}", headers=auth)
    assert r.status_code == 409, r.text
    assert start.value in r.json()["detail"]
    assert db.rows["drives"][0].lifecycle is start


def test_enroll_requires_presence(signing_key: bytes) -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive(DriveLifecycle.DETECTED, present=False)]
    client, auth = _app(db, signing_key)
    with client:
        r = client.post("/api/drives/drv_1/enroll", headers=auth)
    assert r.status_code == 409 and "not present" in r.json()["detail"]


def test_unenroll_refused_while_ripping(signing_key: bytes) -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive(DriveLifecycle.ENROLLED)]
    db.rows["jobs"] = [Job(id="job_1", drive_id="drv_1", status=JobStatus.RIPPING, disc_type=DiscType.DVD)]
    client, auth = _app(db, signing_key)
    with client:
        r = client.post("/api/drives/drv_1/unenroll", headers=auth)
    assert r.status_code == 409 and "ripping" in r.json()["detail"].lower()
    assert db.rows["drives"][0].lifecycle is DriveLifecycle.ENROLLED


def test_unenroll_absent_drive_deletes_the_row(signing_key: bytes) -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive(DriveLifecycle.ENROLLED, present=False)]
    client, auth = _app(db, signing_key)
    with client:
        r = client.post("/api/drives/drv_1/unenroll", headers=auth)
    assert r.status_code == 204
    assert r.content == b""
    assert db.rows["drives"] == []


def test_unknown_drive_is_404(signing_key: bytes) -> None:
    db = FakeSession()
    client, auth = _app(db, signing_key)
    with client:
        assert client.post("/api/drives/drv_nope/enroll", headers=auth).status_code == 404
