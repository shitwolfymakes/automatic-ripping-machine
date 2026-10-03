"""Every legal transition in spec §1's diagram, and every illegal one -> 409."""

from __future__ import annotations

import asyncio
import os
import secrets
import time

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import httpx  # noqa: E402
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

    def __init__(self, *, fail: str | None = None, host_paths: bool = True) -> None:
        self.fail = fail
        self._host_paths = host_paths
        self.ensured: list[str] = []
        self.removed: list[str] = []

    def host_paths_set(self) -> bool:
        return self._host_paths

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


def test_enroll_503_when_host_paths_are_unset(signing_key: bytes) -> None:
    """A3: a present-but-disabled manager (docker is fine, ARM_HOST_*_PATH
    isn't set) must not be reported as "docker socket not available" — that
    would be a false diagnosis pointing the operator at the wrong fix."""
    db = FakeSession()
    db.rows["drives"] = [_drive(DriveLifecycle.DETECTED)]
    client, auth = _app(db, signing_key, manager=_StubManager(host_paths=False))
    with client:
        r = client.post("/api/drives/drv_1/enroll", headers=auth)
    assert r.status_code == 503 and "ARM_HOST" in r.json()["detail"]
    assert db.rows["drives"][0].lifecycle is DriveLifecycle.DETECTED


def test_enroll_unknown_drive_is_404_even_without_a_manager(signing_key: bytes) -> None:
    """A4: _load_drive runs before _manager, so an unknown drive_id is 404
    regardless of docker's state — no manager to consult means nothing to
    say about docker either."""
    db = FakeSession()
    client, auth = _app(db, signing_key, manager=None)
    with client:
        r = client.post("/api/drives/drv_nope/enroll", headers=auth)
    assert r.status_code == 404


def test_unenroll_unknown_drive_is_404_even_without_a_manager(signing_key: bytes) -> None:
    db = FakeSession()
    client, auth = _app(db, signing_key, manager=None)
    with client:
        r = client.post("/api/drives/drv_nope/unenroll", headers=auth)
    assert r.status_code == 404


# --- A1: concurrent enroll/unenroll on the same drive is serialized ---------
#
# `FakeSession` hands every reader the SAME Drive object instance (it's an
# in-memory list, not a real per-transaction snapshot), and neither handler
# awaits anything between reading the row and flipping `lifecycle` — so two
# *enrolls* racing on the fake session can't actually observe a torn read:
# whichever coroutine's synchronous read-then-flip runs first always wins
# outright before the other resumes. The one `await` that genuinely yields
# control mid-handler is `asyncio.to_thread(manager.ensure_running, ...)` —
# and by the time enroll reaches it, the row is already flipped to ENROLLED
# and committed, so a same-op double-enroll correctly 409s the second caller
# with or without the lock (kept below as a contract test).
#
# The reachable clobber is cross-op: enroll flips to ENROLLED, commits, and
# is still inside `ensure_running`'s to_thread call (creating the container)
# when a concurrent *unenroll* — which only requires ENROLLED — reads the
# now-committed row, passes its lifecycle check, and calls `manager.remove`
# on the very container enroll is still creating. Without the lock both
# calls run concurrently and both return 200; with it, unenroll blocks until
# enroll's docker call + commit finish. That's what the second test proves,
# and it was confirmed to FAIL (both docker calls overlap in time) with
# `_drive_lock` stubbed out to always return a fresh, uncontended Lock.


class _SlowFirstManager:
    """The FIRST ensure_running call blocks for a beat before returning —
    long enough for a concurrent unenroll on the same drive to be scheduled
    and, without the lock, run its own docker call while this one is still
    in flight. `ensure_running`/`remove` are sync and run under
    `asyncio.to_thread` in the real code, so a plain `time.sleep` here
    reproduces the worker-thread occupancy that lets the event loop keep
    scheduling the other request's coroutine."""

    def __init__(self) -> None:
        self.timeline: list[tuple[str, float]] = []
        self._first = True

    def host_paths_set(self) -> bool:
        return True

    def ensure_running(self, drive: Drive) -> str:
        self.timeline.append(("ensure_running enter", time.monotonic()))
        if self._first:
            self._first = False
            time.sleep(0.15)
        self.timeline.append(("ensure_running exit", time.monotonic()))
        return "arm-ripper-test"

    def remove(self, drive_id: str) -> int:
        self.timeline.append(("remove", time.monotonic()))
        return 1


def _build_concurrent_app(db: FakeSession, signing_key: bytes, manager: object) -> tuple[FastAPI, dict[str, str]]:
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.ripper_manager = manager
    app.include_router(drives_router.router)

    async def _s() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _s
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, {"Authorization": f"Bearer {token}"}


async def test_concurrent_enroll_on_the_same_drive_is_serialized(signing_key: bytes) -> None:
    """Contract test: two concurrent POST /enroll on the same drive_id yield
    exactly one 200, one 409 ("cannot enroll a drive in lifecycle
    'enrolled'"), exactly one ensure_running call, and the row ends ENROLLED
    with last_error is None. (This particular shape passes with or without
    the lock against FakeSession — see the note above — but it documents
    the intended, and observed, outcome.)"""
    db = FakeSession()
    db.rows["drives"] = [_drive(DriveLifecycle.DETECTED)]
    manager = _SlowFirstManager()
    app, headers = _build_concurrent_app(db, signing_key, manager)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        r1, r2 = await asyncio.gather(
            client.post("/api/drives/drv_1/enroll", headers=headers),
            client.post("/api/drives/drv_1/enroll", headers=headers),
        )

    statuses = sorted([r1.status_code, r2.status_code])
    assert statuses == [200, 409], (r1.status_code, r1.text, r2.status_code, r2.text)
    loser = r1 if r1.status_code == 409 else r2
    assert "cannot enroll a drive in lifecycle 'enrolled'" in loser.json()["detail"]
    ensure_calls = [n for n, _ in manager.timeline if n == "ensure_running enter"]
    assert ensure_calls == ["ensure_running enter"]  # exactly one ensure_running call
    row = db.rows["drives"][0]
    assert row.lifecycle is DriveLifecycle.ENROLLED
    assert row.last_error is None


async def test_concurrent_unenroll_waits_for_an_in_flight_enrolls_docker_call(signing_key: bytes) -> None:
    """A1, the reachable regression: unenroll started while a concurrent
    enroll on the same drive is still inside its docker call must not run
    `manager.remove` until that `ensure_running` call (and its commit) has
    finished — otherwise the two docker operations overlap on the same
    container. Verified to fail (remove starts before ensure_running exits)
    with `_drive_lock` stubbed to return a fresh, uncontended Lock each call."""
    db = FakeSession()
    db.rows["drives"] = [_drive(DriveLifecycle.DETECTED)]
    manager = _SlowFirstManager()
    app, headers = _build_concurrent_app(db, signing_key, manager)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        enroll_task = asyncio.create_task(client.post("/api/drives/drv_1/enroll", headers=headers))
        # Give enroll time to flip the row to ENROLLED, commit, and enter
        # ensure_running's to_thread sleep before unenroll starts.
        await asyncio.sleep(0.05)
        unenroll_task = asyncio.create_task(client.post("/api/drives/drv_1/unenroll", headers=headers))
        r_enroll, r_unenroll = await asyncio.gather(enroll_task, unenroll_task)

    assert r_enroll.status_code == 200, r_enroll.text
    assert r_unenroll.status_code == 200, r_unenroll.text

    events = {name: t for name, t in manager.timeline}
    assert set(events) == {"ensure_running enter", "ensure_running exit", "remove"}
    # The whole point of the lock: remove must not start until ensure_running
    # (enroll's docker call) has fully finished.
    assert events["remove"] >= events["ensure_running exit"], manager.timeline
