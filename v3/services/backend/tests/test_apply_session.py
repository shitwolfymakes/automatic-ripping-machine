"""End-to-end tests for `POST /api/jobs/{id}/transcode` (apply-session)."""

from __future__ import annotations

import os
import secrets
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import jobs as jobs_router  # noqa: E402
from arm_common import (  # noqa: E402
    ContainerFormat,
    DiscType,
    HwPreference,
    IdentificationMode,
    Job,
    JobStatus,
    MediaType,
    OutputMode,
    RipPreset,
    Session,
    SessionApplication,
    SessionApplicationStatus,
    Track,
    TrackKind,
    TrackSelection,
    TrackStatus,
    TranscodePreset,
    TranscodeTask,
    TranscodeTaskStatus,
    TranscodeTool,
    User,
)

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _seed(db: FakeSession, *, job_status: JobStatus = JobStatus.RIPPED) -> None:
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows["jobs"] = [
        Job(
            id="job_x",
            drive_id="drv_x",
            disc_type=DiscType.DVD,
            title="Iron Man",
            year=2008,
            status=job_status,
            metadata_json={},
        )
    ]
    db.rows["rip_presets"] = [
        RipPreset(
            id="rpr_x",
            name="Movie main",
            media_type=MediaType.MOVIE,
            is_builtin=True,
            track_selection=TrackSelection.MAIN_FEATURE,
            identification_mode=IdentificationMode.REQUIRED,
            output_mode=OutputMode.TRACKS,
        )
    ]
    db.rows["transcode_presets"] = [
        TranscodePreset(
            id="tpr_x",
            name="Plex 1080p H.265",
            media_type=MediaType.MOVIE,
            is_builtin=True,
            tool=TranscodeTool.HANDBRAKE,
            container=ContainerFormat.MKV,
            hw_preference=HwPreference.CPU_ONLY,
        )
    ]
    db.rows["sessions"] = [
        Session(
            id="ses_x",
            name="My Plex",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_x",
            transcode_preset_id="tpr_x",
            output_path_template="{title} ({year})/{title} - {transcode_slug}.{ext}",
        )
    ]
    db.rows["tracks"] = [
        Track(
            id="trk_1",
            job_id="job_x",
            kind=TrackKind.VIDEO_TITLE,
            index=1,
            source_ref="1",
            expected_duration_seconds=8000,
            status=TrackStatus.DONE,
        )
    ]
    db.rows["transcode_tasks"] = []
    db.rows["session_applications"] = []
    db.rows["drives"] = []


def _make_app(signing_key: bytes, db: FakeSession, tmp_media_root: Path) -> tuple[FastAPI, str]:
    from arm_backend import config as bcfg

    bcfg.settings.MEDIA_ROOT = str(tmp_media_root)

    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.ws_hub = None
    app.include_router(jobs_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_apply_happy_path_creates_application_and_tasks(signing_key: bytes, tmp_path: Path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_x/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["idempotent"] is False
    assert body["session_application"]["status"] == "queued"
    assert len(body["tasks"]) == 1
    assert body["tasks"][0]["output_path"] == "Iron Man (2008)/Iron Man - plex-1080p-h-265.mkv"
    assert body["tasks"][0]["status"] == "queued"
    assert body["collisions"] == []


def test_apply_idempotent_returns_existing_application(signing_key: bytes, tmp_path: Path) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_existing",
            session_id="ses_x",
            job_id="job_x",
            status=SessionApplicationStatus.QUEUED,
            overwrite=False,
        )
    ]
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_existing",
            session_application_id="sap_existing",
            source_track_id="trk_1",
            status=TranscodeTaskStatus.QUEUED,
            output_path="Iron Man (2008)/Iron Man - plex-1080p-h-265.mkv",
            attempts=0,
            progress_pct=0,
        )
    ]
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_x/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["idempotent"] is True
    assert body["session_application"]["id"] == "sap_existing"
    assert len(body["tasks"]) == 1


def test_apply_collision_409_lists_paths(signing_key: bytes, tmp_path: Path) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_other",
            session_application_id="sap_other",
            source_track_id="trk_other",
            status=TranscodeTaskStatus.QUEUED,
            output_path="Iron Man (2008)/Iron Man - plex-1080p-h-265.mkv",
        )
    ]
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_x/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["message"] == "output_path collisions detected"
    assert detail["collisions"][0]["existing_task_id"] == "txt_other"


def test_apply_overwrite_true_clears_collision(signing_key: bytes, tmp_path: Path) -> None:
    db = FakeSession()
    _seed(db)
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_other",
            session_application_id="sap_other",
            source_track_id="trk_other",
            status=TranscodeTaskStatus.QUEUED,
            output_path="Iron Man (2008)/Iron Man - plex-1080p-h-265.mkv",
        )
    ]
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_x/transcode",
            json={"session_id": "ses_x", "overwrite": True},
            headers=_auth(token),
        )
    assert r.status_code == 200
    assert r.json()["session_application"]["overwrite"] is True


def test_apply_filesystem_collision_detected(signing_key: bytes, tmp_path: Path) -> None:
    db = FakeSession()
    _seed(db)
    target = tmp_path / "Iron Man (2008)"
    target.mkdir(parents=True)
    (target / "Iron Man - plex-1080p-h-265.mkv").write_text("pre-existing")
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_x/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["collisions"][0]["on_filesystem"] is True


def test_apply_to_unidentified_job_creates_waiting_identify(signing_key: bytes, tmp_path: Path) -> None:
    db = FakeSession()
    _seed(db, job_status=JobStatus.AWAITING_USER_ID)
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_x/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 200
    body = r.json()
    assert body["session_application"]["status"] == "waiting_identify"
    assert body["tasks"] == []


def test_apply_rejects_job_in_bad_status(signing_key: bytes, tmp_path: Path) -> None:
    db = FakeSession()
    _seed(db, job_status=JobStatus.RIPPING)
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_x/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 409


def test_apply_unknown_session_400(signing_key: bytes, tmp_path: Path) -> None:
    db = FakeSession()
    _seed(db)
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_x/transcode",
            json={"session_id": "ses_does_not_exist"},
            headers=_auth(token),
        )
    assert r.status_code == 400


def test_apply_integrity_race_returns_409(signing_key: bytes, tmp_path: Path) -> None:
    db = FakeSession()
    _seed(db)
    db.commit_raises = IntegrityError("stmt", {}, Exception("partial unique"))
    app, token = _make_app(signing_key, db, tmp_path)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/job_x/transcode",
            json={"session_id": "ses_x"},
            headers=_auth(token),
        )
    assert r.status_code == 409
    assert "concurrent" in r.json()["detail"].lower()
