"""Transcode-task list + delete: filters, 404, the IN_PROGRESS cancel paths
(dispatcher missing → 503, dispatcher present → async cancel + 204), and the
synchronous delete path with/without a job-bearing application and WS hub."""

from __future__ import annotations

import os
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import pytest  # noqa: E402

from arm_backend.config import settings  # noqa: E402
from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import transcodes as tx_router  # noqa: E402
from arm_common import (  # noqa: E402
    Gpu,
    GpuStatus,
    GpuVendor,
    SessionApplication,
    SessionApplicationStatus,
    TranscodeTaskStatus,
    User,
)
from arm_common.models import TranscodeTask  # noqa: E402

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
        self.events.append({"event_type": event_type, "payload": payload, "job_id": job_id, "track_id": track_id})


class _Dispatcher:
    def __init__(self) -> None:
        self.cancelled: list[str] = []

    async def cancel_running(self, task_id: str) -> None:
        self.cancelled.append(task_id)


def _make_app(
    signing_key: bytes,
    db: FakeSession,
    *,
    hub: _CapturingHub | None = None,
    dispatcher: _Dispatcher | None = None,
) -> tuple[FastAPI, str]:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.ws_hub = hub
    app.state.transcode_dispatcher = dispatcher
    app.include_router(tx_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    db.rows.setdefault("users", []).append(
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)
    )
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _task(
    task_id: str = "txt_1",
    *,
    status: TranscodeTaskStatus = TranscodeTaskStatus.QUEUED,
    session_application_id: str = "sap_1",
    source_track_id: str = "trk_1",
) -> TranscodeTask:
    return TranscodeTask(
        id=task_id,
        session_application_id=session_application_id,
        source_track_id=source_track_id,
        status=status,
        progress_pct=0,
        attempts=0,
    )


def _gpu(
    gpu_id: str = "gpu_1", *, status: GpuStatus = GpuStatus.AVAILABLE, claimed_by_task_id: str | None = None
) -> Gpu:
    return Gpu(
        id=gpu_id,
        vendor=GpuVendor.VAAPI,
        device_path="/dev/dri/renderD128",
        encoder_kinds=["h264"],
        status=status,
        claimed_by_task_id=claimed_by_task_id,
    )


def test_list_all_and_filters(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["transcode_tasks"] = [
        _task("txt_q", status=TranscodeTaskStatus.QUEUED, session_application_id="sap_a"),
        _task("txt_d", status=TranscodeTaskStatus.DONE, session_application_id="sap_b"),
    ]
    with TestClient(app) as client:
        all_rows = client.get("/api/transcodes", headers=_auth(token))
        by_status = client.get("/api/transcodes?status=done", headers=_auth(token))
        by_app = client.get("/api/transcodes?session_application_id=sap_a", headers=_auth(token))
    assert all_rows.status_code == 200
    assert len(all_rows.json()) == 2
    assert [r["id"] for r in by_status.json()] == ["txt_d"]
    assert [r["id"] for r in by_app.json()] == ["txt_q"]


def test_delete_404(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    with TestClient(app) as client:
        r = client.delete("/api/transcodes/txt_missing", headers=_auth(token))
    assert r.status_code == 404
    assert "unknown transcode_task_id" in r.json()["detail"]


def test_delete_in_progress_without_dispatcher_503(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db, dispatcher=None)
    db.rows["transcode_tasks"] = [_task("txt_run", status=TranscodeTaskStatus.IN_PROGRESS)]
    with TestClient(app) as client:
        r = client.delete("/api/transcodes/txt_run", headers=_auth(token))
    assert r.status_code == 503
    assert "dispatcher unavailable" in r.json()["detail"]


def test_delete_in_progress_triggers_cancel_and_204(signing_key: bytes) -> None:
    db = FakeSession()
    dispatcher = _Dispatcher()
    app, token = _make_app(signing_key, db, dispatcher=dispatcher)
    db.rows["transcode_tasks"] = [_task("txt_run", status=TranscodeTaskStatus.IN_PROGRESS)]
    with TestClient(app) as client:
        r = client.delete("/api/transcodes/txt_run", headers=_auth(token))
    assert r.status_code == 204
    assert dispatcher.cancelled == ["txt_run"]


def test_delete_terminal_emits_with_job_id(signing_key: bytes) -> None:
    db = FakeSession()
    hub = _CapturingHub()
    app, token = _make_app(signing_key, db, hub=hub)
    db.rows["transcode_tasks"] = [
        _task("txt_done", status=TranscodeTaskStatus.DONE, session_application_id="sap_1", source_track_id="trk_9")
    ]
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_1",
            session_id="ses_1",
            job_id="job_01JZXR7K3M5Q8N4VWA0000000C",
            status=SessionApplicationStatus.QUEUED,
        )
    ]
    with TestClient(app) as client:
        r = client.delete("/api/transcodes/txt_done", headers=_auth(token))
    assert r.status_code == 204
    assert len(hub.events) == 1
    evt = hub.events[0]
    assert evt["event_type"] == "task.deleted"
    assert evt["payload"] == {"task_id": "txt_done", "session_application_id": "sap_1"}
    assert evt["job_id"] == "job_01JZXR7K3M5Q8N4VWA0000000C"
    assert evt["track_id"] == "trk_9"


def test_delete_terminal_no_application_no_hub(signing_key: bytes) -> None:
    """application lookup misses (job_id None) and no ws_hub on app.state —
    both `is not None` guards take their false branch; still 204."""
    db = FakeSession()
    app, token = _make_app(signing_key, db, hub=None)
    db.rows["transcode_tasks"] = [_task("txt_orphan", status=TranscodeTaskStatus.FAILED)]
    db.rows["session_applications"] = []
    with TestClient(app) as client:
        r = client.delete("/api/transcodes/txt_orphan", headers=_auth(token))
    assert r.status_code == 204


def test_stats_counts_tasks_and_gpus(signing_key: bytes) -> None:
    db = FakeSession()
    db.rows["transcode_tasks"] = [
        _task("txt_1", status=TranscodeTaskStatus.QUEUED),
        _task("txt_2", status=TranscodeTaskStatus.QUEUED),
        _task("txt_3", status=TranscodeTaskStatus.IN_PROGRESS),
        _task("txt_4", status=TranscodeTaskStatus.DONE),
        _task("txt_5", status=TranscodeTaskStatus.FAILED),
    ]
    db.rows["gpus"] = [
        _gpu("gpu_1", status=GpuStatus.AVAILABLE),
        _gpu("gpu_2", status=GpuStatus.BUSY, claimed_by_task_id="txt_3"),
    ]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/transcodes/stats", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tasks_by_status"] == {"queued": 2, "in_progress": 1, "done": 1, "failed": 1}
    assert body["total_tasks"] == 5
    assert body["gpus_total"] == 2
    assert body["gpus_available"] == 1
    assert body["max_parallel"] == settings.MAX_PARALLEL_TRANSCODES


def test_stats_empty_db_all_zero(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/transcodes/stats", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tasks_by_status"] == {}
    assert body["total_tasks"] == 0
    assert body["gpus_total"] == 0
    assert body["gpus_available"] == 0


def test_stats_requires_jwt(signing_key: bytes) -> None:
    app, _ = _make_app(signing_key, FakeSession())
    with TestClient(app) as c:
        r = c.get("/api/transcodes/stats")
    assert r.status_code == 401


def test_workers_lists_only_in_progress_with_gpu(signing_key: bytes) -> None:
    db = FakeSession()
    db.rows["transcode_tasks"] = [
        _task("txt_run_gpu", status=TranscodeTaskStatus.IN_PROGRESS, source_track_id="trk_a"),
        _task("txt_run_cpu", status=TranscodeTaskStatus.IN_PROGRESS, source_track_id="trk_b"),
        _task("txt_queued", status=TranscodeTaskStatus.QUEUED),
        _task("txt_done", status=TranscodeTaskStatus.DONE),
    ]
    db.rows["gpus"] = [_gpu("gpu_1", status=GpuStatus.BUSY, claimed_by_task_id="txt_run_gpu")]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/transcodes/workers", headers=_auth(token))
    assert r.status_code == 200, r.text
    workers = {w["task_id"]: w for w in r.json()}
    assert set(workers) == {"txt_run_gpu", "txt_run_cpu"}  # only in-progress
    assert workers["txt_run_gpu"]["gpu_id"] == "gpu_1"
    assert workers["txt_run_cpu"]["gpu_id"] is None
    assert workers["txt_run_gpu"]["source_track_id"] == "trk_a"


def test_workers_empty_when_nothing_running(signing_key: bytes) -> None:
    db = FakeSession()
    db.rows["transcode_tasks"] = [_task("txt_q", status=TranscodeTaskStatus.QUEUED)]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/transcodes/workers", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_workers_requires_jwt(signing_key: bytes) -> None:
    app, _ = _make_app(signing_key, FakeSession())
    with TestClient(app) as c:
        r = c.get("/api/transcodes/workers")
    assert r.status_code == 401


def test_retry_failed_requeues_and_resets(signing_key: bytes) -> None:
    db = FakeSession()
    failed = _task("txt_f", status=TranscodeTaskStatus.FAILED)
    failed.progress_pct = 47
    failed.last_error = "boom"
    failed.claimed_by = "transcoder-xyz"
    failed.claim_heartbeat_at = datetime.now(UTC)
    failed.attempts = 2
    db.rows["transcode_tasks"] = [failed]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.post("/api/transcodes/txt_f/retry", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "queued"
    assert body["progress_pct"] == 0
    assert body["last_error"] is None
    assert body["claimed_by"] is None
    assert body["claim_heartbeat_at"] is None
    assert body["attempts"] == 2  # preserved for audit
    assert db.rows["transcode_tasks"][0].status == TranscodeTaskStatus.QUEUED


def test_retry_non_failed_409(signing_key: bytes) -> None:
    db = FakeSession()
    db.rows["transcode_tasks"] = [_task("txt_run", status=TranscodeTaskStatus.IN_PROGRESS)]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.post("/api/transcodes/txt_run/retry", headers=_auth(token))
    assert r.status_code == 409, r.text
    assert "in_progress" in r.json()["detail"]


def test_retry_unknown_404(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.post("/api/transcodes/txt_nope/retry", headers=_auth(token))
    assert r.status_code == 404


def test_retry_requires_jwt(signing_key: bytes) -> None:
    app, _ = _make_app(signing_key, FakeSession())
    with TestClient(app) as c:
        r = c.post("/api/transcodes/txt_x/retry")
    assert r.status_code == 401


def _write_task_log(log_dir: Path, task_id: str, lines: list[str]) -> None:
    p = log_dir / f"arm-transcode-{task_id[-12:]}.log"
    p.write_text("".join(line if line.endswith("\n") else line + "\n" for line in lines), encoding="utf-8")


def test_log_streams_task_file(signing_key: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tx_router, "LOG_DIR", tmp_path)
    db = FakeSession()
    db.rows["transcode_tasks"] = [_task("txt_log000000001", status=TranscodeTaskStatus.DONE)]
    _write_task_log(tmp_path, "txt_log000000001", ["line one", "line two"])
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/transcodes/txt_log000000001/log", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert "line one" in r.text and "line two" in r.text


def test_log_unknown_task_404(signing_key: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tx_router, "LOG_DIR", tmp_path)
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/transcodes/txt_missing0001/log", headers=_auth(token))
    assert r.status_code == 404


def test_log_task_exists_no_file_404(signing_key: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tx_router, "LOG_DIR", tmp_path)
    db = FakeSession()
    db.rows["transcode_tasks"] = [_task("txt_nofile00001", status=TranscodeTaskStatus.DONE)]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/transcodes/txt_nofile00001/log", headers=_auth(token))
    assert r.status_code == 404
    assert "no transcoder log" in r.json()["detail"]


def test_log_respects_limit_cap(signing_key: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tx_router, "LOG_DIR", tmp_path)
    db = FakeSession()
    db.rows["transcode_tasks"] = [_task("txt_cap000000001", status=TranscodeTaskStatus.DONE)]
    _write_task_log(tmp_path, "txt_cap000000001", ["a", "b", "c"])
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/transcodes/txt_cap000000001/log?limit=2", headers=_auth(token))
    assert r.status_code == 200, r.text
    # only the first 2 lines are streamed
    assert r.text.count("\n") == 2


def test_log_zip_returns_zip(signing_key: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import zipfile

    monkeypatch.setattr(tx_router, "LOG_DIR", tmp_path)
    db = FakeSession()
    db.rows["transcode_tasks"] = [_task("txt_zip000000001", status=TranscodeTaskStatus.DONE)]
    _write_task_log(tmp_path, "txt_zip000000001", ["zipline"])
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/transcodes/txt_zip000000001/log.zip", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    assert zf.namelist() == ["arm-transcode-zip000000001.log"]
    assert b"zipline" in zf.read("arm-transcode-zip000000001.log")


def test_log_zip_no_file_404(signing_key: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tx_router, "LOG_DIR", tmp_path)
    db = FakeSession()
    db.rows["transcode_tasks"] = [_task("txt_zipno000001", status=TranscodeTaskStatus.DONE)]
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/transcodes/txt_zipno000001/log.zip", headers=_auth(token))
    assert r.status_code == 404


def test_log_requires_jwt(signing_key: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tx_router, "LOG_DIR", tmp_path)
    app, _ = _make_app(signing_key, FakeSession())
    with TestClient(app) as c:
        r = c.get("/api/transcodes/txt_x/log")
    assert r.status_code == 401


def test_log_zip_respects_hard_cap(signing_key: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import zipfile

    monkeypatch.setattr(tx_router, "LOG_DIR", tmp_path)
    monkeypatch.setattr(settings, "ARM_LOG_PER_FILE_HARD_CAP", 2)  # cheap cap for the test
    db = FakeSession()
    db.rows["transcode_tasks"] = [_task("txt_zipcap000001", status=TranscodeTaskStatus.DONE)]
    _write_task_log(tmp_path, "txt_zipcap000001", ["x1", "x2", "x3", "x4"])
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/transcodes/txt_zipcap000001/log.zip", headers=_auth(token))
    assert r.status_code == 200, r.text
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    content = zf.read("arm-transcode-zipcap000001.log").decode()
    assert content.count("\n") == 2  # capped at ARM_LOG_PER_FILE_HARD_CAP lines


def test_log_zip_unknown_task_404(signing_key: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tx_router, "LOG_DIR", tmp_path)
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    with TestClient(app) as c:
        r = c.get("/api/transcodes/txt_zipmissing/log.zip", headers=_auth(token))
    assert r.status_code == 404


def test_log_zip_requires_jwt(signing_key: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tx_router, "LOG_DIR", tmp_path)
    app, _ = _make_app(signing_key, FakeSession())
    with TestClient(app) as c:
        r = c.get("/api/transcodes/txt_x/log.zip")
    assert r.status_code == 401


def test_list_transcodes_populates_job_id(signing_key: bytes) -> None:
    """GET /api/transcodes resolves job_id via the task's SessionApplication."""
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["transcode_tasks"] = [
        _task("txt_j1", status=TranscodeTaskStatus.QUEUED, session_application_id="sap_j1"),
    ]
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_j1",
            session_id="ses_1",
            job_id="job_01JZXR7K3M5Q8N4VWA0000000J",
            status=SessionApplicationStatus.QUEUED,
        )
    ]
    with TestClient(app) as client:
        r = client.get("/api/transcodes", headers=_auth(token))
    assert r.status_code == 200
    tasks = r.json()
    assert tasks, "expected at least one task"
    assert tasks[0]["job_id"] == "job_01JZXR7K3M5Q8N4VWA0000000J"


def test_list_transcodes_job_id_none_when_no_application(signing_key: bytes) -> None:
    """job_id is None when the task's SessionApplication is not found."""
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["transcode_tasks"] = [
        _task("txt_orphan2", status=TranscodeTaskStatus.QUEUED, session_application_id="sap_missing"),
    ]
    db.rows["session_applications"] = []
    with TestClient(app) as client:
        r = client.get("/api/transcodes", headers=_auth(token))
    assert r.status_code == 200
    tasks = r.json()
    assert tasks[0]["job_id"] is None
