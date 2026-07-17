"""GET /api/jobs/stats — dashboard aggregates."""

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
from arm_backend.routers import jobs as jobs_router  # noqa: E402
from arm_common import DiscType, Drive, DriveStatus, Job, JobStatus, User  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _make_app(signing_key: bytes, db: FakeSession) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(jobs_router.router)

    async def _override() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _seed(db: FakeSession) -> None:
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows["drives"] = [
        Drive(id="drv_0000000000000000000000001", hostname="h1", device_path="/dev/sr0", status=DriveStatus.ONLINE),
    ]
    db.rows["jobs"] = [
        Job(
            id="job_0000000000000000000000001",
            drive_id="drv_0000000000000000000000001",
            disc_type=DiscType.DVD,
            status=JobStatus.RIPPING,
        ),
        Job(
            id="job_0000000000000000000000002",
            drive_id="drv_0000000000000000000000001",
            disc_type=DiscType.DVD,
            status=JobStatus.RIPPED,
        ),
        Job(
            id="job_0000000000000000000000003",
            drive_id="drv_0000000000000000000000001",
            disc_type=DiscType.CD,
            status=JobStatus.RIPPED,
        ),
    ]


def test_stats_aggregates(signing_key: bytes) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/jobs/stats", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 3
    assert body["by_status"] == {"ripping": 1, "ripped": 2}
    assert body["by_type"] == {"dvd": 2, "cd": 1}


def test_stats_empty_db(signing_key: bytes) -> None:
    db = FakeSession()
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/jobs/stats", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json() == {"total": 0, "by_status": {}, "by_type": {}}


def test_stats_unauthenticated_401(signing_key: bytes) -> None:
    db = FakeSession()
    app, _ = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/jobs/stats")
    assert r.status_code == 401


def test_stats_not_shadowed_by_job_id_route(signing_key: bytes) -> None:
    """`/stats` must be declared before `/{job_id}` — a 404 'job stats not
    found' here would mean the literal segment was captured as an id."""
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/jobs/stats", headers=_auth(token))
    assert r.status_code == 200
