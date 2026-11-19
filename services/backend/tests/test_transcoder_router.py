"""End-to-end tests for the `/api/transcoder/*` endpoints.

Uses the same FakeSession + TestClient pattern as the Phase 6 router tests.
Service-token auth (no JWT plumbing required).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, AsyncIterator


import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from arm_backend.db import get_session
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
from tests._logs import LineCapture, log_commits

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


# --- job-log milestones ----------------------------------------------------


def test_container_task_logs_its_milestones(job_log: LineCapture) -> None:
    """Claim, a heartbeat run and complete log started once, each quarter crossed once, and completed."""
    db = FakeSession()
    _seed(db)
    with TestClient(_make_app(db)) as client:
        assert client.post("/api/transcoder/tasks/txt_1/claim", headers=_SERVICE_AUTH).status_code == 200
        for pct in (10, 30, 30, 80, 100):
            r = client.patch("/api/transcoder/tasks/txt_1/heartbeat", json={"progress_pct": pct}, headers=_SERVICE_AUTH)
            assert r.status_code == 200, r.text
        r = client.patch(
            "/api/transcoder/tasks/txt_1/complete",
            json={"output_path": "Iron Man (2008)/Iron Man.mkv", "size_bytes": 1024000},
            headers=_SERVICE_AUTH,
        )
        assert r.status_code == 200, r.text

    (started,) = job_log.lines(event="transcode.started")
    assert started["msg"] == "transcoding track 1/1 to Plex 1080p H.265"
    assert started["job_id"] == "job_01JZXR7K3M5Q8N4VWA00000001" and started["track_id"] == "trk_1"
    progress = job_log.lines(event="transcode.progress")
    assert [line["fields"]["percent"] for line in progress] == [25, 75, 100]
    (completed,) = job_log.lines(event="transcode.completed")
    assert completed["fields"]["size_bytes"] == 1024000
    assert completed["fields"]["output"] == "Iron Man (2008)/Iron Man.mkv"
    (session_done,) = job_log.lines(event="session.completed")
    assert session_done["msg"] == "transcode complete: 1/1" and session_done["session_application_id"] == "sap_x"
    assert job_log.lines(logger_prefix="arm_backend.routers.transcoder") == []


def test_container_task_failure_logs_an_error(job_log: LineCapture) -> None:
    db = FakeSession()
    _seed(db, task_status=TranscodeTaskStatus.IN_PROGRESS)
    db.rows["session_applications"][0].status = SessionApplicationStatus.RUNNING
    with TestClient(_make_app(db)) as client:
        r = client.patch(
            "/api/transcoder/tasks/txt_1/fail", json={"last_error": "HandBrakeCLI exited rc=1"}, headers=_SERVICE_AUTH
        )
    assert r.status_code == 200, r.text
    (line,) = job_log.lines(event="transcode.failed")
    assert line["level"] == "error" and line["msg"] == "track 1/1 transcode failed: HandBrakeCLI exited rc=1"
    (session_done,) = job_log.lines(event="session.completed")
    assert session_done["msg"] == "transcode failed: 0/1" and session_done["level"] == "warning"


@pytest.mark.parametrize(
    ("method", "path", "body", "status", "announcer"),
    [
        ("post", "claim", None, TranscodeTaskStatus.QUEUED, "announce_started"),
        ("patch", "heartbeat", {"progress_pct": 50}, TranscodeTaskStatus.IN_PROGRESS, "announce_progress"),
        ("patch", "complete", {"output_path": "a.mkv"}, TranscodeTaskStatus.IN_PROGRESS, "announce_completed"),
        ("patch", "fail", {"last_error": "x"}, TranscodeTaskStatus.IN_PROGRESS, "announce_failed"),
    ],
)
def test_a_failed_milestone_log_does_not_fail_the_request(
    job_log: LineCapture,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    status: TranscodeTaskStatus,
    announcer: str,
) -> None:
    async def _broken(*_args: Any) -> None:
        raise RuntimeError("log bug")

    monkeypatch.setattr(transcoder_router.transcode_task_events, announcer, _broken)
    db = FakeSession()
    _seed(db, task_status=status)
    with TestClient(_make_app(db)) as client:
        r = getattr(client, method)(f"/api/transcoder/tasks/txt_1/{path}", json=body, headers=_SERVICE_AUTH)
    assert r.status_code == 200, r.text
    assert job_log.lines(level="error")[-1]["msg"].startswith("could not log the transcode.")


_SETTLE_ORDER = ("commit", "transcode.completed", "transcode.failed", "session.completed")


@pytest.mark.parametrize(
    ("path", "body", "task_event"),
    [
        ("complete", {"output_path": "a.mkv"}, "transcode.completed"),
        ("fail", {"last_error": "HandBrakeCLI exited rc=1"}, "transcode.failed"),
    ],
)
def test_session_completed_follows_the_commit_and_the_task_line(
    job_log: LineCapture, path: str, body: dict[str, Any], task_event: str
) -> None:
    """The last task's line comes before the session's, and both only once the transition is committed."""
    db = FakeSession()
    _seed(db, task_status=TranscodeTaskStatus.IN_PROGRESS)
    log_commits(db)
    with TestClient(_make_app(db)) as client:
        r = client.patch(f"/api/transcoder/tasks/txt_1/{path}", json=body, headers=_SERVICE_AUTH)
    assert r.status_code == 200, r.text
    assert job_log.events(*_SETTLE_ORDER) == ["commit", task_event, "session.completed"]


@pytest.mark.parametrize(
    ("path", "body"), [("complete", {"output_path": "a.mkv"}), ("fail", {"last_error": "HandBrakeCLI exited rc=1"})]
)
def test_a_failed_commit_logs_no_session_completed(job_log: LineCapture, path: str, body: dict[str, Any]) -> None:
    db = FakeSession()
    _seed(db, task_status=TranscodeTaskStatus.IN_PROGRESS)
    db.commit_raises = RuntimeError("db gone")
    with TestClient(_make_app(db)) as client, pytest.raises(RuntimeError, match="db gone"):
        client.patch(f"/api/transcoder/tasks/txt_1/{path}", json=body, headers=_SERVICE_AUTH)
    assert job_log.lines(event="session.completed") == []
