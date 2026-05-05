"""Tests for DELETE /api/jobs/{id} and DELETE /api/jobs.

Covers the four real failure modes:
  1. Single delete on a terminal job → 204, row gone, no WS emit when delete_raw=False.
  2. Single delete with delete_raw=True → WS `job.deleted` fired on the drive's topic.
  3. Single delete on a non-terminal job → 409, row preserved.
  4. Bulk delete partitions terminal vs non-terminal correctly.
"""

from __future__ import annotations

import os
import secrets
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import jobs as jobs_router  # noqa: E402
from arm_common import DiscType, Job, JobStatus, User  # noqa: E402

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


def _make_job(job_id: str, *, status: JobStatus, drive_id: str = "drv_x") -> Job:
    return Job(
        id=job_id,
        drive_id=drive_id,
        disc_type=DiscType.DVD,
        title="X",
        year=2000,
        status=status,
        metadata_json={},
    )


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


def _seed_admin(db: FakeSession) -> None:
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]


def test_delete_terminal_job_no_raw(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = [_make_job("job_a", status=JobStatus.RIPPED)]
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.delete("/api/jobs/job_a", headers=_auth(token))
    assert r.status_code == 204
    assert db.rows["jobs"] == []
    # No WS emit unless delete_raw=true.
    assert hub.events == []


def test_delete_with_delete_raw_emits_ws(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = [_make_job("job_a", status=JobStatus.RIPPED, drive_id="drv_42")]
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.delete("/api/jobs/job_a?delete_raw=true", headers=_auth(token))
    assert r.status_code == 204
    assert db.rows["jobs"] == []
    assert len(hub.events) == 1
    evt = hub.events[0]
    assert evt["topic"] == "ripper.commands.drv_42"
    assert evt["event_type"] == "job.deleted"
    assert evt["payload"] == {"job_id": "job_a", "drive_id": "drv_42", "delete_raw": True}


@pytest.mark.parametrize(
    "status",
    [
        JobStatus.CREATED,
        JobStatus.AWAITING_USER_ID,
        JobStatus.IDENTIFIED,
        JobStatus.RIPPING,
    ],
)
def test_delete_non_terminal_returns_409(signing_key: bytes, status: JobStatus) -> None:
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = [_make_job("job_a", status=status)]
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.delete("/api/jobs/job_a?delete_raw=true", headers=_auth(token))
    assert r.status_code == 409
    # Row preserved; WS not fired.
    assert len(db.rows["jobs"]) == 1
    assert hub.events == []


def test_delete_unknown_job_returns_404(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = []
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.delete("/api/jobs/job_missing", headers=_auth(token))
    assert r.status_code == 404


def test_bulk_delete_partitions_terminal_and_non_terminal(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = [
        _make_job("job_done", status=JobStatus.RIPPED),
        _make_job("job_partial", status=JobStatus.RIPPED_PARTIAL),
        _make_job("job_failed", status=JobStatus.FAILED),
        _make_job("job_abandoned", status=JobStatus.ABANDONED),
        _make_job("job_running", status=JobStatus.RIPPING),
        _make_job("job_pending_id", status=JobStatus.AWAITING_USER_ID),
    ]
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.delete("/api/jobs", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert sorted(body["deleted_ids"]) == ["job_abandoned", "job_done", "job_failed", "job_partial"]
    assert sorted(body["skipped_non_terminal"]) == ["job_pending_id", "job_running"]
    # Survivors are the non-terminal ones.
    surviving_ids = sorted(j.id for j in db.rows["jobs"])
    assert surviving_ids == ["job_pending_id", "job_running"]
    # No WS unless delete_raw=true.
    assert hub.events == []


def test_bulk_delete_with_raw_emits_one_ws_per_terminal_job(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = [
        _make_job("job_a", status=JobStatus.RIPPED, drive_id="drv_1"),
        _make_job("job_b", status=JobStatus.FAILED, drive_id="drv_2"),
        _make_job("job_active", status=JobStatus.RIPPING, drive_id="drv_3"),
    ]
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.delete("/api/jobs?delete_raw=true", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert sorted(body["deleted_ids"]) == ["job_a", "job_b"]
    assert body["skipped_non_terminal"] == ["job_active"]
    # One WS event per terminal job, on its own drive's topic; the
    # in-flight job gets no event.
    topics = sorted(evt["topic"] for evt in hub.events)
    assert topics == ["ripper.commands.drv_1", "ripper.commands.drv_2"]
    for evt in hub.events:
        assert evt["event_type"] == "job.deleted"
        assert evt["payload"]["delete_raw"] is True


def test_bulk_delete_empty_db_returns_empty_lists(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = []
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub)
    with TestClient(app) as client:
        r = client.delete("/api/jobs", headers=_auth(token))
    assert r.status_code == 200
    assert r.json() == {"deleted_ids": [], "skipped_non_terminal": []}
