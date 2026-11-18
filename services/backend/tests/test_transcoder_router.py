"""End-to-end tests for the `/api/transcoder/*` endpoints.

Uses the same FakeSession + TestClient pattern as the Phase 6 router tests.
Service-token auth (no JWT plumbing required).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, AsyncIterator


from fastapi import FastAPI
from fastapi.testclient import TestClient

from arm_backend.db import get_session
from arm_backend.handbrake_schema_store import SchemaStore
from arm_backend.routers import transcoder as transcoder_router
from arm_backend.ws import WSHub
from arm_common import (
    ContainerFormat,
    DiscType,
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
from tests._fakes import FakeSession
from tests._hb_schema import fixture_schema

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
            encoder="preset",
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


class _FakeRunner:
    def __init__(self) -> None:
        self.requested: list[str] = []

    def request_refresh_if_hash_differs(self, schema_hash: str) -> None:
        self.requested.append(schema_hash)


def _make_app(db: FakeSession, *, store: SchemaStore | None = None, runner: _FakeRunner | None = None) -> FastAPI:
    app = FastAPI()
    app.state.ws_hub = WSHub()
    app.state.handbrake_schema_store = store if store is not None else SchemaStore()
    if runner is not None:
        app.state.handbrake_schema_runner = runner
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
    # started_at marks the claim so the UI measures encode time, not queue wait (D-130/D-202).
    assert db.rows["transcode_tasks"][0].started_at is not None
    assert body["task"]["started_at"] is not None
    assert db.rows["session_applications"][0].status == SessionApplicationStatus.RUNNING


def test_claim_resets_the_previous_attempts_telemetry() -> None:
    # A retry must not show the failed attempt's ETA or frame rate until its
    # own first heartbeat (D-242, D-248).
    db = FakeSession()
    _seed(db)
    row = db.rows["transcode_tasks"][0]
    row.current_pass, row.eta_seconds, row.fps, row.avg_fps = "1/1", 600, 45.7, 23.5
    with TestClient(_make_app(db)) as client:
        r = client.post("/api/transcoder/tasks/txt_1/claim", headers=_SERVICE_AUTH)
    assert r.status_code == 200, r.text
    task = r.json()["task"]
    assert (task["current_pass"], task["eta_seconds"], task["fps"], task["avg_fps"]) == (None, None, None, None)


class _RecordingHub(WSHub):
    """A hub that records (event_type, payload) instead of publishing."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def emit(  # type: ignore[override]
        self, *, topic: str, event_type: str, payload: dict[str, Any], **_kw: Any
    ) -> None:
        self.events.append((event_type, payload))


def _app_with_hub(db: FakeSession) -> tuple[FastAPI, _RecordingHub]:
    app = _make_app(db)
    hub = _RecordingHub()
    app.state.ws_hub = hub
    return app, hub


def _add_second_task(db: FakeSession, status: TranscodeTaskStatus) -> None:
    """A sibling task of the same application, still unfinished."""
    db.rows["transcode_tasks"].append(
        TranscodeTask(
            id="txt_2",
            session_application_id="sap_x",
            source_track_id="trk_1",
            status=status,
            output_path="Iron Man (2008)/Iron Man - other.mkv",
            attempts=0,
            progress_pct=0,
        )
    )


def test_claim_on_a_running_application_emits_only_the_task_event() -> None:
    """The application is already RUNNING: no session.started, the claim still succeeds."""
    db = FakeSession()
    _seed(db)
    db.rows["session_applications"][0].status = SessionApplicationStatus.RUNNING
    app, hub = _app_with_hub(db)
    with TestClient(app) as client:
        r = client.post("/api/transcoder/tasks/txt_1/claim", headers=_SERVICE_AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["task"]["status"] == "in_progress"
    assert [e for e, _ in hub.events] == ["task.started"]
    assert db.rows["session_applications"][0].status == SessionApplicationStatus.RUNNING


def test_complete_with_another_task_still_queued_emits_no_application_event() -> None:
    """A sibling task is unfinished: only task.completed is emitted, the task update commits."""
    db = FakeSession()
    _seed(db, task_status=TranscodeTaskStatus.IN_PROGRESS)
    _add_second_task(db, TranscodeTaskStatus.QUEUED)
    db.rows["session_applications"][0].status = SessionApplicationStatus.RUNNING
    app, hub = _app_with_hub(db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/transcoder/tasks/txt_1/complete",
            json={
                "output_path": "Iron Man (2008)/Iron Man - plex-1080p-h-265.mkv",
                "size_bytes": 1,
                "duration_seconds": 1,
            },
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"
    assert db.rows["transcode_tasks"][0].status == TranscodeTaskStatus.DONE
    assert [e for e, _ in hub.events] == ["task.completed"]
    assert db.rows["session_applications"][0].status == SessionApplicationStatus.RUNNING
    assert db.rows["session_applications"][0].completed_at is None


def test_fail_with_another_task_still_running_emits_no_application_event() -> None:
    """A sibling task is unfinished: only task.failed is emitted, the task update commits."""
    db = FakeSession()
    _seed(db, task_status=TranscodeTaskStatus.IN_PROGRESS)
    _add_second_task(db, TranscodeTaskStatus.IN_PROGRESS)
    db.rows["session_applications"][0].status = SessionApplicationStatus.RUNNING
    app, hub = _app_with_hub(db)
    with TestClient(app) as client:
        r = client.patch(
            "/api/transcoder/tasks/txt_1/fail",
            json={"last_error": "HandBrakeCLI exited rc=1"},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "failed"
    assert db.rows["transcode_tasks"][0].status == TranscodeTaskStatus.FAILED
    assert [e for e, _ in hub.events] == ["task.failed"]
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
            json={"progress_pct": 42, "current_pass": "main", "eta_seconds": 600, "fps": 45.7, "avg_fps": 23.5},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["progress_pct"] == 42
    row = db.rows["transcode_tasks"][0]
    assert row.progress_pct == 42
    # The reported telemetry lands on the row and the view, so a polling
    # client sees the same ETA and frame rate as the live event (D-242, D-248).
    assert (row.current_pass, row.eta_seconds, row.fps, row.avg_fps) == ("main", 600, 45.7, 23.5)
    assert (body["current_pass"], body["eta_seconds"], body["fps"], body["avg_fps"]) == ("main", 600, 45.7, 23.5)


def test_heartbeat_without_telemetry_clears_the_previous_values() -> None:
    # HandBrake's early ticks carry no ETA or fps; the row follows the latest
    # report rather than keeping a stale one.
    db = FakeSession()
    _seed(db, task_status=TranscodeTaskStatus.IN_PROGRESS)
    row = db.rows["transcode_tasks"][0]
    row.eta_seconds, row.fps = 600, 45.7
    with TestClient(_make_app(db)) as client:
        r = client.patch("/api/transcoder/tasks/txt_1/heartbeat", json={"progress_pct": 1}, headers=_SERVICE_AUTH)
    assert r.status_code == 200, r.text
    assert (row.current_pass, row.eta_seconds, row.fps, row.avg_fps) == (None, None, None, None)


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


def test_register_returns_no_preset_when_session_has_none() -> None:
    db = FakeSession()
    _seed(db)
    db.rows["sessions"][0].transcode_preset_id = None
    with TestClient(_make_app(db)) as client:
        r = client.post(
            "/api/transcoder/register",
            json={"task_id": "txt_1", "hostname": _HOSTNAME, "hw_caps": {"cpu_count": 4}},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 200, r.text
    assert r.json()["transcode_preset"] is None


# --- schema_hash guard and refresh -------------------------------------------

_SETTINGS = {"common": {"PictureWidth": 1280}}
_PREDATES = "transcode image predates HandBrake settings; rebuild or pull it"


def _register(app: FastAPI, **extra: Any) -> Any:
    body = {"task_id": "txt_1", "hostname": _HOSTNAME, "hw_caps": {"cpu_count": 4}, **extra}
    with TestClient(app) as client:
        return client.post("/api/transcoder/register", json=body, headers=_SERVICE_AUTH)


def _loaded_store() -> SchemaStore:
    store = SchemaStore()
    store.replace(fixture_schema())
    return store


def test_register_refuses_an_image_without_schema_hash_when_the_preset_has_settings() -> None:
    db = FakeSession()
    _seed(db)
    db.rows["transcode_presets"][0].handbrake_settings = _SETTINGS
    r = _register(_make_app(db))
    assert r.status_code == 409
    assert r.json()["detail"] == _PREDATES


def test_register_accepts_an_image_without_schema_hash_when_the_preset_has_no_settings() -> None:
    db = FakeSession()
    _seed(db)
    r = _register(_make_app(db))
    assert r.status_code == 200, r.text


def test_register_returns_the_full_preset_view_with_settings() -> None:
    db = FakeSession()
    _seed(db)
    db.rows["transcode_presets"][0].handbrake_settings = _SETTINGS
    r = _register(_make_app(db), schema_hash="abc")
    assert r.status_code == 200, r.text
    preset = r.json()["transcode_preset"]
    assert preset["handbrake_settings"]["common"] == _SETTINGS["common"]
    assert "issues" in preset and "host_notes" in preset


def test_register_requests_a_refresh_when_the_hash_differs() -> None:
    db = FakeSession()
    _seed(db)
    runner = _FakeRunner()
    r = _register(_make_app(db, store=_loaded_store(), runner=runner), schema_hash="other")
    assert r.status_code == 200, r.text
    assert runner.requested == ["other"]


def test_register_requests_a_refresh_when_no_schema_is_loaded() -> None:
    db = FakeSession()
    _seed(db)
    runner = _FakeRunner()
    r = _register(_make_app(db, runner=runner), schema_hash="other")
    assert r.status_code == 200, r.text
    assert runner.requested == ["other"]


def test_register_skips_the_refresh_when_the_hash_matches() -> None:
    db = FakeSession()
    _seed(db)
    store = _loaded_store()
    schema = store.current()
    assert schema is not None
    runner = _FakeRunner()
    r = _register(_make_app(db, store=store, runner=runner), schema_hash=schema.content_hash)
    assert r.status_code == 200, r.text
    assert runner.requested == []


def test_register_skips_the_refresh_when_the_image_reports_no_hash() -> None:
    db = FakeSession()
    _seed(db)
    runner = _FakeRunner()
    r = _register(_make_app(db, runner=runner))
    assert r.status_code == 200, r.text
    assert runner.requested == []


def test_register_without_a_runner_is_a_no_op_refresh() -> None:
    db = FakeSession()
    _seed(db)
    r = _register(_make_app(db), schema_hash="other")
    assert r.status_code == 200, r.text
