"""End-to-end tests for the `/api/transcoder/*` endpoints.

Uses the same FakeSession + TestClient pattern as the Phase 6 router tests.
Service-token auth (no JWT plumbing required).
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import AsyncIterator

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.routers import transcoder as transcoder_router  # noqa: E402
from arm_backend.ws import WSHub  # noqa: E402
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
)
from tests._fakes import FakeSession  # noqa: E402

_HOSTNAME = "arm-transcode-abc123"
_SERVICE_AUTH = {"Authorization": "Bearer tok-service", "X-ARM-Hostname": _HOSTNAME}


def _seed(db: FakeSession, *, task_status: TranscodeTaskStatus = TranscodeTaskStatus.QUEUED) -> None:
    db.rows["jobs"] = [
        Job(
            id="job_01JZXR7K3M5Q8N4VWA00000001",
            drive_id="drv_x",
            disc_type=DiscType.DVD,
            title="Iron Man",
            year=2008,
            status=JobStatus.RIPPED,
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
            preset_ref="H.265 MKV 1080p30",
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
            job_id="job_01JZXR7K3M5Q8N4VWA00000001",
            kind=TrackKind.VIDEO_TITLE,
            index=1,
            source_ref="1",
            expected_duration_seconds=8000,
            status=TrackStatus.DONE,
            output_path="/raw/job_01JZXR7K3M5Q8N4VWA00000001/title_t01.mkv",
            attempts=0,
        )
    ]
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_x",
            session_id="ses_x",
            job_id="job_01JZXR7K3M5Q8N4VWA00000001",
            status=SessionApplicationStatus.QUEUED,
            overwrite=False,
        )
    ]
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_1",
            session_application_id="sap_x",
            source_track_id="trk_1",
            status=task_status,
            output_path="Iron Man (2008)/Iron Man - plex-1080p-h-265.mkv",
            attempts=0,
            progress_pct=0,
            claimed_by=_HOSTNAME if task_status == TranscodeTaskStatus.IN_PROGRESS else None,
            claim_heartbeat_at=datetime.now(UTC) if task_status == TranscodeTaskStatus.IN_PROGRESS else None,
        )
    ]


def _make_app(db: FakeSession) -> FastAPI:
    app = FastAPI()
    app.state.ws_hub = WSHub()
    app.include_router(transcoder_router.router)

    async def _override() -> AsyncIterator[FakeSession]:
        yield db

    app.dependency_overrides[get_session] = _override
    return app


def test_register_returns_bundle() -> None:
    db = FakeSession()
    _seed(db)
    app = _make_app(db)
    with TestClient(app) as client:
        r = client.post(
            "/api/transcoder/register",
            json={
                "task_id": "txt_1",
                "hostname": _HOSTNAME,
                "hw_caps": {"cpu_count": 8},
            },
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["task"]["id"] == "txt_1"
    assert body["raw_input_path"] == "/raw/job_01JZXR7K3M5Q8N4VWA00000001/title_t01.mkv"
    assert body["transcode_preset"]["preset_ref"] == "H.265 MKV 1080p30"
    assert body["session"]["id"] == "ses_x"


def test_register_refuses_when_track_has_no_output_path() -> None:
    db = FakeSession()
    _seed(db)
    db.rows["tracks"][0].output_path = None
    app = _make_app(db)
    with TestClient(app) as client:
        r = client.post(
            "/api/transcoder/register",
            json={"task_id": "txt_1", "hostname": _HOSTNAME, "hw_caps": {"cpu_count": 4}},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 409
    assert "no output_path" in r.json()["detail"]


def test_register_404_unknown_task() -> None:
    db = FakeSession()
    _seed(db)
    app = _make_app(db)
    with TestClient(app) as client:
        r = client.post(
            "/api/transcoder/register",
            json={"task_id": "txt_unknown", "hostname": _HOSTNAME, "hw_caps": {"cpu_count": 4}},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 404


def test_claim_transitions_task_and_application() -> None:
    db = FakeSession()
    _seed(db)
    app = _make_app(db)
    with TestClient(app) as client:
        r = client.post("/api/transcoder/tasks/txt_1/claim", headers=_SERVICE_AUTH)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["task"]["status"] == "in_progress"
    assert body["task"]["claimed_by"] == _HOSTNAME
    assert body["task"]["attempts"] == 1
    assert db.rows["session_applications"][0].status == SessionApplicationStatus.RUNNING


def test_claim_idempotent_for_same_host() -> None:
    db = FakeSession()
    _seed(db, task_status=TranscodeTaskStatus.IN_PROGRESS)
    app = _make_app(db)
    with TestClient(app) as client:
        r = client.post("/api/transcoder/tasks/txt_1/claim", headers=_SERVICE_AUTH)
    assert r.status_code == 200
    # Idempotent — no attempts increment, status unchanged.
    assert db.rows["transcode_tasks"][0].attempts == 0


def test_claim_409_when_not_queued_and_other_host() -> None:
    db = FakeSession()
    _seed(db, task_status=TranscodeTaskStatus.IN_PROGRESS)
    db.rows["transcode_tasks"][0].claimed_by = "arm-transcode-other"
    app = _make_app(db)
    with TestClient(app) as client:
        r = client.post("/api/transcoder/tasks/txt_1/claim", headers=_SERVICE_AUTH)
    assert r.status_code == 409


def test_heartbeat_updates_progress_and_timestamp() -> None:
    db = FakeSession()
    _seed(db, task_status=TranscodeTaskStatus.IN_PROGRESS)
    app = _make_app(db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/transcoder/tasks/txt_1/heartbeat",
            json={"progress_pct": 42, "current_pass": "main", "eta_seconds": 600},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 200, r.text
    assert r.json()["progress_pct"] == 42
    assert db.rows["transcode_tasks"][0].progress_pct == 42


def test_heartbeat_403_when_not_owner() -> None:
    db = FakeSession()
    _seed(db, task_status=TranscodeTaskStatus.IN_PROGRESS)
    db.rows["transcode_tasks"][0].claimed_by = "someone-else"
    app = _make_app(db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/transcoder/tasks/txt_1/heartbeat",
            json={"progress_pct": 50},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 403


def test_complete_marks_done_and_aggregates_application() -> None:
    db = FakeSession()
    _seed(db, task_status=TranscodeTaskStatus.IN_PROGRESS)
    db.rows["session_applications"][0].status = SessionApplicationStatus.RUNNING
    app = _make_app(db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/transcoder/tasks/txt_1/complete",
            json={
                "output_path": "Iron Man (2008)/Iron Man - plex-1080p-h-265.mkv",
                "size_bytes": 1024000,
                "duration_seconds": 8000,
            },
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"
    assert db.rows["transcode_tasks"][0].status == TranscodeTaskStatus.DONE
    assert db.rows["session_applications"][0].status == SessionApplicationStatus.DONE
    assert db.rows["session_applications"][0].completed_at is not None


def test_fail_marks_failed_and_aggregates() -> None:
    db = FakeSession()
    _seed(db, task_status=TranscodeTaskStatus.IN_PROGRESS)
    db.rows["session_applications"][0].status = SessionApplicationStatus.RUNNING
    app = _make_app(db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/transcoder/tasks/txt_1/fail",
            json={"last_error": "HandBrakeCLI exited rc=1"},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "failed"
    assert db.rows["session_applications"][0].status == SessionApplicationStatus.FAILED


def test_complete_409_on_wrong_status() -> None:
    db = FakeSession()
    _seed(db, task_status=TranscodeTaskStatus.QUEUED)  # never claimed
    db.rows["transcode_tasks"][0].claimed_by = _HOSTNAME
    app = _make_app(db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/transcoder/tasks/txt_1/complete",
            json={"output_path": "x.mkv"},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 409


def test_jwt_rejected_on_transcoder_endpoint() -> None:
    db = FakeSession()
    _seed(db)
    app = _make_app(db)
    with TestClient(app) as client:
        r = client.post(
            "/api/transcoder/tasks/txt_1/claim",
            headers={"Authorization": "Bearer aa.bb.cc", "X-ARM-Hostname": _HOSTNAME},
        )
    assert r.status_code == 401
    assert "service endpoint requires service token" in r.json()["detail"]


# --- residual guard coverage -------------------------------------------------

_NO_HOST_AUTH = {"Authorization": "Bearer tok-service"}


def test_register_409_when_task_terminal() -> None:
    db = FakeSession()
    _seed(db, task_status=TranscodeTaskStatus.DONE)
    with TestClient(_make_app(db)) as client:
        r = client.post(
            "/api/transcoder/register",
            json={"task_id": "txt_1", "hostname": _HOSTNAME, "hw_caps": {"cpu_count": 4}},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 409
    assert "terminal status" in r.json()["detail"]


def test_register_409_when_claimed_by_other_host_in_progress() -> None:
    db = FakeSession()
    _seed(db, task_status=TranscodeTaskStatus.IN_PROGRESS)
    db.rows["transcode_tasks"][0].claimed_by = "some-other-host"
    with TestClient(_make_app(db)) as client:
        r = client.post(
            "/api/transcoder/register",
            json={"task_id": "txt_1", "hostname": _HOSTNAME, "hw_caps": {"cpu_count": 4}},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 409
    assert "claimed by a different host" in r.json()["detail"]


def test_claim_400_missing_hostname() -> None:
    db = FakeSession()
    _seed(db)
    with TestClient(_make_app(db)) as client:
        r = client.post("/api/transcoder/tasks/txt_1/claim", headers=_NO_HOST_AUTH)
    assert r.status_code == 400
    assert "missing X-ARM-Hostname" in r.json()["detail"]


def test_heartbeat_400_missing_hostname() -> None:
    db = FakeSession()
    _seed(db, task_status=TranscodeTaskStatus.IN_PROGRESS)
    with TestClient(_make_app(db)) as client:
        r = client.patch(
            "/api/transcoder/tasks/txt_1/heartbeat",
            json={"progress_pct": 10},
            headers=_NO_HOST_AUTH,
        )
    assert r.status_code == 400
    assert "missing X-ARM-Hostname" in r.json()["detail"]


def test_heartbeat_409_when_not_in_progress() -> None:
    db = FakeSession()
    _seed(db, task_status=TranscodeTaskStatus.QUEUED)
    db.rows["transcode_tasks"][0].claimed_by = _HOSTNAME
    with TestClient(_make_app(db)) as client:
        r = client.patch(
            "/api/transcoder/tasks/txt_1/heartbeat",
            json={"progress_pct": 10},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 409
    assert "not in_progress" in r.json()["detail"]


def test_fail_409_when_not_in_progress() -> None:
    db = FakeSession()
    _seed(db, task_status=TranscodeTaskStatus.QUEUED)
    db.rows["transcode_tasks"][0].claimed_by = _HOSTNAME
    with TestClient(_make_app(db)) as client:
        r = client.patch(
            "/api/transcoder/tasks/txt_1/fail",
            json={"last_error": "boom"},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 409
    assert "not in_progress" in r.json()["detail"]
