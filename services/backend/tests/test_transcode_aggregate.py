from typing import Any

import pytest

from arm_backend import transcode_apply
from arm_backend.transcode_apply import aggregate_session_application, settle_session_application
from arm_common import (
    DiscType,
    Job,
    JobStatus,
    SessionApplication,
    SessionApplicationStatus,
    TranscodeTask,
    TranscodeTaskStatus,
)
from tests._fakes import FakeSession
from tests._logs import LineCapture


def _app(status: SessionApplicationStatus = SessionApplicationStatus.RUNNING) -> SessionApplication:
    return SessionApplication(
        id="sap_x",
        session_id="ses_x",
        job_id="job_01JZXR7K3M5Q8N4VWA00000001",
        status=status,
        overwrite=False,
    )


def _task(idx: int, status: TranscodeTaskStatus) -> TranscodeTask:
    return TranscodeTask(
        id=f"txt_{idx}",
        session_application_id="sap_x",
        source_track_id=f"trk_{idx}",
        status=status,
        attempts=0,
        progress_pct=0,
    )


async def test_all_done_transitions_to_done() -> None:
    db = FakeSession()
    app = _app()
    db.rows["transcode_tasks"] = [_task(1, TranscodeTaskStatus.DONE), _task(2, TranscodeTaskStatus.DONE)]
    outcome = await aggregate_session_application(db, app)
    assert outcome.event_type == "session.completed"
    assert app.status == SessionApplicationStatus.DONE
    assert app.completed_at is not None


async def test_all_failed_transitions_to_failed() -> None:
    db = FakeSession()
    app = _app()
    db.rows["transcode_tasks"] = [_task(1, TranscodeTaskStatus.FAILED), _task(2, TranscodeTaskStatus.FAILED)]
    outcome = await aggregate_session_application(db, app)
    assert outcome.event_type == "session.failed"
    assert app.status == SessionApplicationStatus.FAILED


async def test_mixed_done_failed_is_partial() -> None:
    db = FakeSession()
    app = _app()
    db.rows["transcode_tasks"] = [_task(1, TranscodeTaskStatus.DONE), _task(2, TranscodeTaskStatus.FAILED)]
    outcome = await aggregate_session_application(db, app)
    assert outcome.event_type == "session.partial"
    assert app.status == SessionApplicationStatus.DONE_PARTIAL


async def test_pending_task_means_running_no_transition() -> None:
    db = FakeSession()
    app = _app()
    db.rows["transcode_tasks"] = [_task(1, TranscodeTaskStatus.DONE), _task(2, TranscodeTaskStatus.IN_PROGRESS)]
    outcome = await aggregate_session_application(db, app)
    assert outcome.event_type is None
    assert app.status == SessionApplicationStatus.RUNNING
    assert app.completed_at is None


async def test_idempotent_when_already_terminal() -> None:
    db = FakeSession()
    app = _app(status=SessionApplicationStatus.DONE)
    db.rows["transcode_tasks"] = [_task(1, TranscodeTaskStatus.DONE)]
    outcome = await aggregate_session_application(db, app)
    assert outcome.event_type is None  # don't re-emit
    assert app.status == SessionApplicationStatus.DONE


async def test_no_tasks_does_nothing() -> None:
    db = FakeSession()
    app = _app(status=SessionApplicationStatus.WAITING_IDENTIFY)
    db.rows["transcode_tasks"] = []
    outcome = await aggregate_session_application(db, app)
    assert outcome.event_type is None
    assert app.status == SessionApplicationStatus.WAITING_IDENTIFY


class _Hub:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def emit(self, **kwargs: Any) -> None:
        self.events.append(kwargs["event_type"])


def _db_with_job(*statuses: TranscodeTaskStatus) -> FakeSession:
    db = FakeSession()
    db.rows["jobs"] = [
        Job(
            id="job_01JZXR7K3M5Q8N4VWA00000001",
            drive_id="d",
            disc_type=DiscType.CD,
            status=JobStatus.RIPPED,
            metadata_json={},
        )
    ]
    db.rows["transcode_tasks"] = [_task(i, s) for i, s in enumerate(statuses, start=1)]
    return db


async def test_aggregate_counts_the_settled_tasks() -> None:
    db = _db_with_job(TranscodeTaskStatus.DONE, TranscodeTaskStatus.FAILED, TranscodeTaskStatus.DONE)
    outcome = await aggregate_session_application(db, _app())
    assert (outcome.done, outcome.failed, outcome.total) == (2, 1, 3)


async def test_settle_logs_session_completed_once(job_log: LineCapture) -> None:
    db = _db_with_job(TranscodeTaskStatus.DONE, TranscodeTaskStatus.FAILED)
    app = _app()
    hub = _Hub()
    await settle_session_application(db, hub, app)  # type: ignore[arg-type]
    await settle_session_application(db, hub, app)  # type: ignore[arg-type]
    (line,) = job_log.lines(event="session.completed")
    assert line["msg"] == "transcode complete: 1/2 (1 failed)"
    assert line["job_id"] == "job_01JZXR7K3M5Q8N4VWA00000001" and line["session_application_id"] == "sap_x"
    assert hub.events == ["session.partial"]


async def test_settle_with_work_left_logs_nothing(job_log: LineCapture) -> None:
    db = _db_with_job(TranscodeTaskStatus.DONE, TranscodeTaskStatus.QUEUED)
    await settle_session_application(db, _Hub(), _app())  # type: ignore[arg-type]
    assert job_log.lines(event="session.completed") == []


async def test_settle_survives_a_failed_session_log(job_log: LineCapture, monkeypatch: pytest.MonkeyPatch) -> None:
    def _broken(*_args: Any, **_kw: Any) -> None:
        raise RuntimeError("log bug")

    monkeypatch.setattr(transcode_apply.job_events, "log_session_completed", _broken)
    app = _app()
    await settle_session_application(_db_with_job(TranscodeTaskStatus.DONE), _Hub(), app)  # type: ignore[arg-type]
    assert app.status == SessionApplicationStatus.DONE
    assert job_log.lines(level="error")[0]["msg"] == "could not log the session.completed milestone"


async def test_settle_without_the_job_row_logs_nothing(job_log: LineCapture) -> None:
    db = FakeSession()
    db.rows["transcode_tasks"] = [_task(1, TranscodeTaskStatus.DONE)]
    await settle_session_application(db, _Hub(), _app())  # type: ignore[arg-type]
    assert job_log.lines(event="session.completed") == [] and job_log.lines(level="error") == []
