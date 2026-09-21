"""Verify that PATCH /api/jobs/{id} accepts and persists disc_number/disc_total.

Mirrors the harness from test_jobs_router.py (FakeSession + TestClient,
no Postgres, no Docker).
"""

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
from arm_common import (  # noqa: E402
    DiscType,
    Job,
    JobStatus,
    User,
)

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


_JOB_ID = "job_01JZXR7K3M5Q8N4VWA00000003"


def _seed_job(db: FakeSession) -> Job:
    """Seed a minimal CD job in RIPPED state — a terminal-ish state that update_job accepts."""
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    job = Job(
        id=_JOB_ID,
        drive_id="drv_cd",
        disc_type=DiscType.CD,
        title="Abbey Road",
        year=1969,
        disc_number=None,
        disc_total=None,
        status=JobStatus.RIPPED,
        metadata_json={},
        resumed_from_crash=False,
    )
    db.rows["jobs"] = [job]
    db.rows["tracks"] = []
    return job


class _Hub:
    async def emit(self, topic: str, event_type: str, payload: dict, **kwargs: object) -> None:
        pass


def _make_app(signing_key: bytes, db: FakeSession) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.ws_hub = _Hub()
    app.include_router(jobs_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_patch_job_persists_disc_fields(signing_key: bytes) -> None:
    """PATCH with disc_number/disc_total must return 200 and persist the values
    onto the job row — confirmed in both the response body and the DB row."""
    db = FakeSession()
    _seed_job(db)
    app, token = _make_app(signing_key, db)

    with TestClient(app) as client:
        resp = client.patch(
            f"/api/jobs/{_JOB_ID}",
            json={"disc_number": 2, "disc_total": 2},
            headers=_auth(token),
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["disc_number"] == 2
    assert body["disc_total"] == 2

    # Also confirm the DB row was mutated.
    job_row = next(j for j in db.rows["jobs"] if j.id == _JOB_ID)
    assert job_row.disc_number == 2
    assert job_row.disc_total == 2
