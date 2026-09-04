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
from arm_backend.ripper_manager import RipperManagerError  # noqa: E402
from arm_backend.routers import drives as drives_router  # noqa: E402
from arm_common import Drive, DriveLifecycle, DriveStatus, Job, JobStatus, User  # noqa: E402
from arm_common.enums import DiscType  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


class _StubManager:
    """Records calls; raises when told to. Sync methods, like the real one."""

    def __init__(self, *, fail: str | None = None) -> None:
        self.fail = fail
        self.ensured: list[str] = []
        self.removed: list[str] = []

    def ensure_running(self, drive: Drive) -> str:
        if self.fail:
            raise RipperManagerError(self.fail)
        self.ensured.append(drive.id)
        return "arm-ripper-test"

    def remove(self, drive_id: str) -> int:
        if self.fail:
            raise RipperManagerError(self.fail)
        self.removed.append(drive_id)
        return 1


def _app(
    db: FakeSession, signing_key: bytes, *, manager: _StubManager | None | object = "default"
) -> tuple[TestClient, dict[str, str]]:
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.ripper_manager = _StubManager() if manager == "default" else manager
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


def test_enroll_creates_the_container(signing_key: bytes) -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive(DriveLifecycle.DETECTED)]
    manager = _StubManager()
    client, auth = _app(db, signing_key, manager=manager)
    with client:
        r = client.post("/api/drives/drv_1/enroll", headers=auth)
    assert r.status_code == 200, r.text
    assert manager.ensured == ["drv_1"]
    assert db.rows["drives"][0].lifecycle is DriveLifecycle.ENROLLED
    assert db.rows["drives"][0].last_error is None


@pytest.mark.parametrize("start", [DriveLifecycle.DETECTED, DriveLifecycle.IGNORED])
def test_enroll_docker_failure_reverts_the_row_and_records_the_error(signing_key: bytes, start: DriveLifecycle) -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive(start)]
    client, auth = _app(db, signing_key, manager=_StubManager(fail="ImageNotFound: arm-ripper:latest"))
    with client:
        r = client.post("/api/drives/drv_1/enroll", headers=auth)
    assert r.status_code == 502, r.text
    assert "ImageNotFound" in r.json()["detail"]
    row = db.rows["drives"][0]
    assert row.lifecycle is start
    assert row.last_error == "ImageNotFound: arm-ripper:latest"


def test_enroll_503_without_a_manager(signing_key: bytes) -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive(DriveLifecycle.DETECTED)]
    client, auth = _app(db, signing_key, manager=None)
    with client:
        r = client.post("/api/drives/drv_1/enroll", headers=auth)
    assert r.status_code == 503 and "docker" in r.json()["detail"]
    assert db.rows["drives"][0].lifecycle is DriveLifecycle.DETECTED


def test_unenroll_removes_the_container(signing_key: bytes) -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive(DriveLifecycle.ENROLLED)]
    manager = _StubManager()
    client, auth = _app(db, signing_key, manager=manager)
    with client:
        r = client.post("/api/drives/drv_1/unenroll", headers=auth)
    assert r.status_code == 200, r.text
    assert manager.removed == ["drv_1"]
    assert db.rows["drives"][0].lifecycle is DriveLifecycle.DETECTED


def test_unenroll_docker_failure_keeps_the_row_enrolled(signing_key: bytes) -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive(DriveLifecycle.ENROLLED)]
    client, auth = _app(db, signing_key, manager=_StubManager(fail="APIError: cannot stop"))
    with client:
        r = client.post("/api/drives/drv_1/unenroll", headers=auth)
    assert r.status_code == 502 and "cannot stop" in r.json()["detail"]
    row = db.rows["drives"][0]
    assert row.lifecycle is DriveLifecycle.ENROLLED and row.last_error == "APIError: cannot stop"


def test_unenroll_503_without_a_manager(signing_key: bytes) -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive(DriveLifecycle.ENROLLED)]
    client, auth = _app(db, signing_key, manager=None)
    with client:
        r = client.post("/api/drives/drv_1/unenroll", headers=auth)
    assert r.status_code == 503
    assert db.rows["drives"][0].lifecycle is DriveLifecycle.ENROLLED


def test_unenroll_refused_when_the_drive_status_is_ripping(signing_key: bytes) -> None:
    db = FakeSession()
    drive = _drive(DriveLifecycle.ENROLLED)
    drive.status = DriveStatus.RIPPING
    db.rows["drives"] = [drive]
    manager = _StubManager()
    client, auth = _app(db, signing_key, manager=manager)
    with client:
        r = client.post("/api/drives/drv_1/unenroll", headers=auth)
    assert r.status_code == 409 and "ripping" in r.json()["detail"].lower()
    assert manager.removed == []
