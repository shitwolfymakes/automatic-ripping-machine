"""Tests for the `transcode_progress` summary attached to `JobView`."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_common.schemas.jobs import JobView, TranscodeProgressSummary  # noqa: E402


def test_transcode_progress_summary_shape() -> None:
    s = TranscodeProgressSummary(state="done", tasks_total=2, tasks_done=2, percent=100.0)
    assert s.model_dump() == {
        "state": "done",
        "tasks_total": 2,
        "tasks_done": 2,
        "percent": 100.0,
    }


def test_jobview_transcode_progress_defaults_none() -> None:
    view = JobView(
        id="job_x",
        drive_id="drv_x",
        disc_type="bluray",
        status="ripped",
        title="X",
        year=2000,
        metadata_json={},
        resumed_from_crash=False,
    )
    assert view.transcode_progress is None


from arm_common import (  # noqa: E402
    SessionApplication,
    SessionApplicationStatus,
    TranscodeTask,
    TranscodeTaskStatus,
)
from arm_backend.routers.jobs import _summarize_transcode_progress  # noqa: E402


def _sa(sa_id: str, status: SessionApplicationStatus) -> SessionApplication:
    return SessionApplication(id=sa_id, session_id="ses_x", job_id="job_x", status=status)


def _task(task_id: str, sa_id: str, status: TranscodeTaskStatus, pct: int) -> TranscodeTask:
    return TranscodeTask(
        id=task_id,
        session_application_id=sa_id,
        source_track_id="trk_x",
        status=status,
        output_path="/media/x.mkv",
        attempts=0,
        progress_pct=pct,
    )


def test_no_session_apps_returns_none() -> None:
    assert _summarize_transcode_progress([], []) is None


def test_running_session_is_transcoding() -> None:
    sa = _sa("sap_1", SessionApplicationStatus.RUNNING)
    tasks = [
        _task("txt_1", "sap_1", TranscodeTaskStatus.DONE, 100),
        _task("txt_2", "sap_1", TranscodeTaskStatus.IN_PROGRESS, 40),
    ]
    s = _summarize_transcode_progress([sa], tasks)
    assert s is not None
    assert s.state == "transcoding"
    assert s.tasks_total == 2
    assert s.tasks_done == 1
    assert s.percent == 70.0


def test_all_done_is_done() -> None:
    sa = _sa("sap_1", SessionApplicationStatus.DONE)
    tasks = [
        _task("txt_1", "sap_1", TranscodeTaskStatus.DONE, 100),
        _task("txt_2", "sap_1", TranscodeTaskStatus.DONE, 100),
    ]
    s = _summarize_transcode_progress([sa], tasks)
    assert s is not None
    assert s.state == "done"
    assert s.tasks_done == 2 and s.tasks_total == 2 and s.percent == 100.0


def test_done_partial_is_done_partial() -> None:
    sa = _sa("sap_1", SessionApplicationStatus.DONE_PARTIAL)
    tasks = [
        _task("txt_1", "sap_1", TranscodeTaskStatus.DONE, 100),
        _task("txt_2", "sap_1", TranscodeTaskStatus.FAILED, 0),
    ]
    s = _summarize_transcode_progress([sa], tasks)
    assert s is not None
    assert s.state == "done_partial"
    assert s.tasks_done == 1 and s.tasks_total == 2


def test_all_failed_is_failed() -> None:
    sa = _sa("sap_1", SessionApplicationStatus.FAILED)
    tasks = [_task("txt_1", "sap_1", TranscodeTaskStatus.FAILED, 0)]
    s = _summarize_transcode_progress([sa], tasks)
    assert s is not None
    assert s.state == "failed"


def test_multi_session_conflict_done_plus_queued_is_transcoding() -> None:
    # Proves we aggregate ALL session_apps, not the latest. A prior DONE app
    # plus a newer QUEUED app (non-colliding outputs) => still transcoding.
    done_sa = _sa("sap_done", SessionApplicationStatus.DONE)
    queued_sa = _sa("sap_q", SessionApplicationStatus.QUEUED)
    tasks = [
        _task("txt_d", "sap_done", TranscodeTaskStatus.DONE, 100),
        _task("txt_q", "sap_q", TranscodeTaskStatus.QUEUED, 0),
    ]
    s = _summarize_transcode_progress([done_sa, queued_sa], tasks)
    assert s is not None
    assert s.state == "transcoding"


def test_zero_task_queued_session_absorbed_as_done() -> None:
    # Rip-only / all-excluded: QUEUED with 0 tasks is a deadlock in the
    # session subsystem; the read projection absorbs it as terminal/done.
    sa = _sa("sap_1", SessionApplicationStatus.QUEUED)
    s = _summarize_transcode_progress([sa], [])
    assert s is not None
    assert s.state == "done"
    assert s.tasks_total == 0 and s.tasks_done == 0 and s.percent == 100.0


def test_waiting_identify_zero_task_is_not_terminal() -> None:
    # 0 tasks but genuinely waiting — must NOT be treated as done.
    sa = _sa("sap_1", SessionApplicationStatus.WAITING_IDENTIFY)
    s = _summarize_transcode_progress([sa], [])
    assert s is not None
    assert s.state == "transcoding"


import secrets  # noqa: E402
from typing import Any  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import jobs as jobs_router  # noqa: E402
from arm_common import DiscType, Job, JobStatus, User  # noqa: E402
from tests._fakes import FakeSession  # noqa: E402


class _NoopHub:
    async def emit(self, **_: Any) -> None:
        return None


def _make_app(db: FakeSession) -> tuple[FastAPI, str]:
    key = secrets.token_bytes(32)
    app = FastAPI()
    app.state.signing_key = key
    app.state.ws_hub = _NoopHub()
    app.include_router(jobs_router.router)

    async def _override() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override
    token, _ = issue_access_token("usr_admin", "admin", key)
    return app, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _seed_admin(db: FakeSession) -> None:
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]


def _ripped_job(job_id: str) -> Job:
    return Job(
        id=job_id,
        drive_id="drv_x",
        disc_type=DiscType.BLURAY,
        title="X",
        year=2000,
        status=JobStatus.RIPPED,
        metadata_json={},
        resumed_from_crash=False,
    )


def test_list_surfaces_transcode_progress_done() -> None:
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = [_ripped_job("job_01JZXR7K3M5Q8N4VWA00000010")]
    db.rows["session_applications"] = [_sa("sap_1", SessionApplicationStatus.DONE)]
    db.rows["session_applications"][0].job_id = "job_01JZXR7K3M5Q8N4VWA00000010"
    db.rows["transcode_tasks"] = [_task("txt_1", "sap_1", TranscodeTaskStatus.DONE, 100)]
    app, token = _make_app(db)
    with TestClient(app) as client:
        r = client.get("/api/jobs", headers=_auth(token))
    assert r.status_code == 200
    tp = r.json()[0]["transcode_progress"]
    assert tp["state"] == "done" and tp["tasks_done"] == 1


def test_list_job_without_session_has_null_transcode_progress() -> None:
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = [_ripped_job("job_01JZXR7K3M5Q8N4VWA00000011")]
    app, token = _make_app(db)
    with TestClient(app) as client:
        r = client.get("/api/jobs", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()[0]["transcode_progress"] is None


def test_list_empty_page_skips_session_lookup() -> None:
    # No jobs in the page → the `if job_ids:` block is skipped entirely
    # (the batched session_application lookup never runs).
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = []
    app, token = _make_app(db)
    with TestClient(app) as client:
        r = client.get("/api/jobs", headers=_auth(token))
    assert r.status_code == 200
    assert r.json() == []


def test_detail_job_without_session_has_null_transcode_progress() -> None:
    db = FakeSession()
    _seed_admin(db)
    db.rows["jobs"] = [_ripped_job("job_01JZXR7K3M5Q8N4VWA00000021")]
    app, token = _make_app(db)
    with TestClient(app) as client:
        r = client.get("/api/jobs/job_01JZXR7K3M5Q8N4VWA00000021", headers=_auth(token))
    assert r.status_code == 200
    assert r.json()["job"]["transcode_progress"] is None


def test_detail_surfaces_transcode_progress() -> None:
    db = FakeSession()
    _seed_admin(db)
    job = _ripped_job("job_01JZXR7K3M5Q8N4VWA00000020")
    db.rows["jobs"] = [job]
    sa = _sa("sap_1", SessionApplicationStatus.RUNNING)
    sa.job_id = "job_01JZXR7K3M5Q8N4VWA00000020"
    db.rows["session_applications"] = [sa]
    db.rows["transcode_tasks"] = [
        _task("txt_1", "sap_1", TranscodeTaskStatus.DONE, 100),
        _task("txt_2", "sap_1", TranscodeTaskStatus.IN_PROGRESS, 50),
    ]
    app, token = _make_app(db)
    with TestClient(app) as client:
        r = client.get("/api/jobs/job_01JZXR7K3M5Q8N4VWA00000020", headers=_auth(token))
    assert r.status_code == 200
    tp = r.json()["job"]["transcode_progress"]
    assert tp["state"] == "transcoding" and tp["tasks_total"] == 2
