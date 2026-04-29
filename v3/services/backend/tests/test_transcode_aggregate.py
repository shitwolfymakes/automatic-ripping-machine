import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.transcode_apply import aggregate_session_application  # noqa: E402
from arm_common import (  # noqa: E402
    SessionApplication,
    SessionApplicationStatus,
    TranscodeTask,
    TranscodeTaskStatus,
)
from tests._fakes import FakeSession  # noqa: E402


def _app(status: SessionApplicationStatus = SessionApplicationStatus.RUNNING) -> SessionApplication:
    return SessionApplication(
        id="sap_x",
        session_id="ses_x",
        job_id="job_x",
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
