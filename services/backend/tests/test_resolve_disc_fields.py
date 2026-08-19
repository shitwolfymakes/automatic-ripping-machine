"""Verify that POST /api/jobs/{id}/resolve accepts and persists disc_number/disc_total.

Mirrors the harness from test_resolve_fanout.py (FakeSession + TestClient,
no Postgres, no Docker).
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

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


class _CapturingHub:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def emit(
        self,
        topic: str,
        event_type: str,
        payload: dict,
        *,
        persist: bool = True,
        job_id: str | None = None,
        track_id: str | None = None,
        session: object = None,
    ) -> None:
        self.events.append({"topic": topic, "event_type": event_type, "payload": payload})


_JOB_ID = "job_01JZXR7K3M5Q8N4VWA00000002"


def _seed_cd_job(db: FakeSession) -> Job:
    """Seed a minimal CD job in AWAITING_USER_ID — no session/app needed for disc-field test."""
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    job = Job(
        id=_JOB_ID,
        drive_id="drv_cd",
        disc_type=DiscType.CD,
        title=None,
        year=None,
        disc_number=None,
        disc_total=None,
        status=JobStatus.AWAITING_USER_ID,
        metadata_json={},
        resumed_from_crash=False,
    )
    db.rows["jobs"] = [job]
    db.rows["session_applications"] = []
    db.rows["sessions"] = []
    db.rows["rip_presets"] = []
    db.rows["transcode_presets"] = []
    db.rows["tracks"] = []
    db.rows["transcode_tasks"] = []
    db.rows["drives"] = []
    return job


def _make_app(signing_key: bytes, db: FakeSession, tmp_path: Path) -> tuple[FastAPI, str]:
    from arm_backend import config as bcfg

    bcfg.settings.MEDIA_ROOT = str(tmp_path)

    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.ws_hub = _CapturingHub()
    app.include_router(jobs_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_resolve_persists_disc_fields(signing_key: bytes, tmp_path: Path) -> None:
    """A resolvable CD job + a resolve call carrying disc_number/disc_total
    must persist them onto the job row and return them in the response."""
    db = FakeSession()
    _seed_cd_job(db)
    app, token = _make_app(signing_key, db, tmp_path)

    with TestClient(app) as client:
        resp = client.post(
            f"/api/jobs/{_JOB_ID}/resolve",
            json={
                "title": "Abbey Road",
                "year": 1969,
                "disc_number": 1,
                "disc_total": 2,
                "metadata": {"artist": "The Beatles"},
            },
            headers=_auth(token),
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()["job"]
    assert body["disc_number"] == 1
    assert body["disc_total"] == 2
    assert body["title"] == "Abbey Road"

    # Also confirm the DB row was mutated.
    job_row = next(j for j in db.rows["jobs"] if j.id == _JOB_ID)
    assert job_row.disc_number == 1
    assert job_row.disc_total == 2
