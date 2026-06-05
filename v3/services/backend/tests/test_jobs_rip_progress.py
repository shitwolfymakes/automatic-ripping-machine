"""Tests for the `rip_progress` summary attached to `JobView` by GET /api/jobs.

Covers the dashboard "Track N of M" line: only ripping jobs get a summary,
the current-track ordinal is 1-based among tracks sorted by `Track.index`,
and DONE/FAILED counts come straight off the rows.
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
from arm_common import DiscType, Job, JobStatus, Track, TrackKind, TrackStatus, User  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


class _NoopHub:
    async def emit(self, **_: Any) -> None:
        return None


def _make_app(signing_key: bytes, db: FakeSession) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.ws_hub = _NoopHub()
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


def _make_job(job_id: str, *, status: JobStatus, drive_id: str = "drv_x") -> Job:
    # `resumed_from_crash` has a server default in the schema but no
    # Python-side default — the in-memory FakeSession never hits the DB
    # so we set it explicitly here for `JobView.model_validate`.
    return Job(
        id=job_id,
        drive_id=drive_id,
        disc_type=DiscType.BLURAY,
        title="X",
        year=2000,
        status=status,
        metadata_json={},
        resumed_from_crash=False,
    )


def _make_track(track_id: str, *, job_id: str, index: int, status: TrackStatus) -> Track:
    return Track(
        id=track_id,
        job_id=job_id,
        kind=TrackKind.VIDEO_TITLE,
        index=index,
        source_ref=str(index),
        status=status,
    )


def test_ripping_job_with_in_progress_track_returns_summary(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = [_make_job("job_01JZXR7K3M5Q8N4VWA00000002", status=JobStatus.RIPPING)]
    # 8 tracks: 0..1 done, 2 in-progress, 3..7 queued. Indexes intentionally
    # out of insertion order to prove `_summarize_rip_progress` sorts by
    # `Track.index` before computing the ordinal.
    db.rows["tracks"] = [
        _make_track("trk_3", job_id="job_01JZXR7K3M5Q8N4VWA00000002", index=3, status=TrackStatus.QUEUED),
        _make_track("trk_2", job_id="job_01JZXR7K3M5Q8N4VWA00000002", index=2, status=TrackStatus.IN_PROGRESS),
        _make_track("trk_0", job_id="job_01JZXR7K3M5Q8N4VWA00000002", index=0, status=TrackStatus.DONE),
        _make_track("trk_1", job_id="job_01JZXR7K3M5Q8N4VWA00000002", index=1, status=TrackStatus.DONE),
        _make_track("trk_4", job_id="job_01JZXR7K3M5Q8N4VWA00000002", index=4, status=TrackStatus.QUEUED),
        _make_track("trk_5", job_id="job_01JZXR7K3M5Q8N4VWA00000002", index=5, status=TrackStatus.QUEUED),
        _make_track("trk_6", job_id="job_01JZXR7K3M5Q8N4VWA00000002", index=6, status=TrackStatus.QUEUED),
        _make_track("trk_7", job_id="job_01JZXR7K3M5Q8N4VWA00000002", index=7, status=TrackStatus.QUEUED),
    ]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/jobs", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    rp = body[0]["rip_progress"]
    assert rp == {
        "tracks_total": 8,
        "tracks_done": 2,
        "tracks_failed": 0,
        "current_track_id": "trk_2",
        # Index 2 is the 3rd track when sorted (indexes 0,1,2,...) → 1-based ordinal 3.
        "current_track_index": 3,
    }


def test_ripping_job_without_in_progress_track_returns_null_current(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = [_make_job("job_01JZXR7K3M5Q8N4VWA00000002", status=JobStatus.RIPPING)]
    db.rows["tracks"] = [
        _make_track("trk_0", job_id="job_01JZXR7K3M5Q8N4VWA00000002", index=0, status=TrackStatus.QUEUED),
        _make_track("trk_1", job_id="job_01JZXR7K3M5Q8N4VWA00000002", index=1, status=TrackStatus.QUEUED),
        _make_track("trk_2", job_id="job_01JZXR7K3M5Q8N4VWA00000002", index=2, status=TrackStatus.QUEUED),
    ]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/jobs", headers=_auth(token))
    assert r.status_code == 200
    rp = r.json()[0]["rip_progress"]
    assert rp == {
        "tracks_total": 3,
        "tracks_done": 0,
        "tracks_failed": 0,
        "current_track_id": None,
        "current_track_index": None,
    }


def test_ripping_job_counts_failed_tracks(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = [_make_job("job_01JZXR7K3M5Q8N4VWA00000002", status=JobStatus.RIPPING)]
    db.rows["tracks"] = [
        _make_track("trk_0", job_id="job_01JZXR7K3M5Q8N4VWA00000002", index=0, status=TrackStatus.DONE),
        _make_track("trk_1", job_id="job_01JZXR7K3M5Q8N4VWA00000002", index=1, status=TrackStatus.FAILED),
        _make_track("trk_2", job_id="job_01JZXR7K3M5Q8N4VWA00000002", index=2, status=TrackStatus.IN_PROGRESS),
        _make_track("trk_3", job_id="job_01JZXR7K3M5Q8N4VWA00000002", index=3, status=TrackStatus.QUEUED),
    ]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/jobs", headers=_auth(token))
    assert r.status_code == 200
    rp = r.json()[0]["rip_progress"]
    assert rp["tracks_done"] == 1
    assert rp["tracks_failed"] == 1
    assert rp["current_track_index"] == 3


@pytest.mark.parametrize(
    "status",
    [
        JobStatus.CREATED,
        JobStatus.AWAITING_USER_ID,
        JobStatus.IDENTIFIED,
        JobStatus.RIPPED,
        JobStatus.RIPPED_PARTIAL,
        JobStatus.ABANDONED,
        JobStatus.FAILED,
    ],
)
def test_non_ripping_jobs_return_null_rip_progress(signing_key: bytes, status: JobStatus) -> None:
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = [_make_job("job_01JZXR7K3M5Q8N4VWA00000002", status=status)]
    # Even with tracks, non-ripping jobs should not get a summary —
    # the field is dashboard-only.
    db.rows["tracks"] = [
        _make_track("trk_0", job_id="job_01JZXR7K3M5Q8N4VWA00000002", index=0, status=TrackStatus.DONE),
    ]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/jobs", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()[0]["rip_progress"] is None


def test_ripping_job_with_no_tracks_returns_zeroed_summary(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = [_make_job("job_01JZXR7K3M5Q8N4VWA00000002", status=JobStatus.RIPPING)]
    db.rows["tracks"] = []
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/jobs", headers=_auth(token))
    assert r.status_code == 200
    rp = r.json()[0]["rip_progress"]
    assert rp == {
        "tracks_total": 0,
        "tracks_done": 0,
        "tracks_failed": 0,
        "current_track_id": None,
        "current_track_index": None,
    }


def test_mixed_jobs_only_ripping_get_summary(signing_key: bytes) -> None:
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = [
        _make_job("job_01JZXR7K3M5Q8N4VWA0000000A", status=JobStatus.RIPPING, drive_id="drv_1"),
        _make_job("job_01JZXR7K3M5Q8N4VWA00000007", status=JobStatus.RIPPED, drive_id="drv_2"),
    ]
    db.rows["tracks"] = [
        _make_track("trk_a0", job_id="job_01JZXR7K3M5Q8N4VWA0000000A", index=0, status=TrackStatus.IN_PROGRESS),
        _make_track("trk_a1", job_id="job_01JZXR7K3M5Q8N4VWA0000000A", index=1, status=TrackStatus.QUEUED),
        # Tracks for the terminal job — must not bleed into its summary.
        _make_track("trk_b0", job_id="job_01JZXR7K3M5Q8N4VWA00000007", index=0, status=TrackStatus.DONE),
    ]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.get("/api/jobs", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    by_id = {j["id"]: j for j in body}
    assert by_id["job_01JZXR7K3M5Q8N4VWA0000000A"]["rip_progress"]["current_track_index"] == 1
    assert by_id["job_01JZXR7K3M5Q8N4VWA0000000A"]["rip_progress"]["tracks_total"] == 2
    assert by_id["job_01JZXR7K3M5Q8N4VWA00000007"]["rip_progress"] is None
