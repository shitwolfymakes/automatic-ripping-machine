"""Transcode-task list + delete: filters, 404, the IN_PROGRESS cancel paths
(dispatcher missing → 503, dispatcher present → async cancel + 204), and the
synchronous delete path with/without a job-bearing application and WS hub."""

from __future__ import annotations

import os
import secrets
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import pytest  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import transcodes as tx_router  # noqa: E402
from arm_common import (  # noqa: E402
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
