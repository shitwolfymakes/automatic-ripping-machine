"""Tests for the in-process passthrough executor.

`execute_passthrough_task` runs one QUEUED passthrough (TranscodeTool.NONE)
task to completion in the backend process instead of spawning a transcoder
container. The lifecycle must mirror `routers/transcoder.py`'s complete/fail
endpoints exactly (claim fields, task.completed/task.failed WS events,
aggregate_session_application + its event emit) so the UI and session
rollups cannot tell the difference.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.config import Settings  # noqa: E402
from arm_backend.passthrough_executor import IN_PROCESS_CLAIMANT, execute_passthrough_task  # noqa: E402
from arm_backend.ws import WSHub  # noqa: E402
from arm_common import (  # noqa: E402
    SessionApplication,
    SessionApplicationStatus,
    Track,
    TranscodeTask,
    TranscodeTaskStatus,
)
from arm_common.enums import TrackKind  # noqa: E402
from tests._fakes import FakeSession  # noqa: E402


def _settings(**overrides: Any) -> Settings:
    base = {
        "DATABASE_URL": "postgresql://x:x@localhost/x",
        "ARM_SERVICE_TOKEN": "tok-service",
    }
    base.update(overrides)
    return Settings.model_construct(**base)


def _hub_with_recorder() -> tuple[WSHub, list[dict[str, Any]]]:
    hub = WSHub()
    sent: list[dict[str, Any]] = []

    async def _capture(**kwargs: Any) -> None:
        sent.append(kwargs)

    hub.emit = _capture  # type: ignore[method-assign]
    return hub, sent


def _db(
    *,
    track_output_path: str | None,
    task_output_path: str | None,
    task_attempts: int = 0,
) -> FakeSession:
    db = FakeSession()
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_x",
            session_id="ses_x",
            job_id="job_01JZXR7K3M5Q8N4VWA00000001",
            status=SessionApplicationStatus.QUEUED,
            overwrite=False,
        )
    ]
    db.rows["tracks"] = [
        Track(
            id="trk_1",
            job_id="job_01JZXR7K3M5Q8N4VWA00000001",
            kind=TrackKind.VIDEO_TITLE,
            index=1,
            source_ref="t0",
            output_path=track_output_path,
        )
    ]
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_1",
            session_application_id="sap_x",
            source_track_id="trk_1",
            status=TranscodeTaskStatus.QUEUED,
            attempts=task_attempts,
            progress_pct=0,
            output_path=task_output_path,
        )
    ]
    return db


async def test_success_moves_file_and_completes(tmp_path: Path) -> None:
    raw = tmp_path / "raw" / "job1" / "t0.mkv"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"data")
    media_root = tmp_path / "media"

    db = _db(track_output_path=str(raw), task_output_path="Title (2020)/t0.mkv")
    hub, sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]

    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is True
    assert task.status == TranscodeTaskStatus.DONE
    assert task.progress_pct == 100
    assert task.last_error is None
    assert task.claimed_by == IN_PROCESS_CLAIMANT
    assert task.attempts == 1
    assert (media_root / "Title (2020)" / "t0.mkv").read_bytes() == b"data"
    assert not raw.exists()

    application = db.rows["session_applications"][0]
    assert application.status == SessionApplicationStatus.DONE

    assert len(sent) == 2
    assert sent[0]["event_type"] == "task.completed"
    assert sent[0]["payload"]["task_id"] == "txt_1"
    assert sent[0]["payload"]["output_path"] == "Title (2020)/t0.mkv"
    assert sent[0]["payload"]["size_bytes"] == 4
    # Pin the exact event_type aggregate_session_application returns for the
    # all-done case (see arm_backend.transcode_apply.aggregate_session_application).
    assert sent[1]["event_type"] == "session.completed"
    assert sent[1]["payload"]["session_application_id"] == "sap_x"
    assert sent[1]["payload"]["status"] == "done"


async def test_missing_source_fails_task_not_loop(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    missing = tmp_path / "raw" / "job1" / "gone.mkv"

    db = _db(track_output_path=str(missing), task_output_path="Title (2020)/t0.mkv")
    hub, sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]

    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is False
    assert task.status == TranscodeTaskStatus.FAILED
    assert task.last_error
    assert "FileNotFoundError" in task.last_error

    application = db.rows["session_applications"][0]
    assert application.status == SessionApplicationStatus.FAILED

    assert sent[0]["event_type"] == "task.failed"
    assert sent[0]["payload"]["last_error"] == task.last_error
    assert sent[1]["event_type"] == "session.failed"


async def test_empty_track_output_path_fails_cleanly(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    db = _db(track_output_path="", task_output_path="Title (2020)/t0.mkv")
    hub, sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]

    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is False
    assert task.status == TranscodeTaskStatus.FAILED
    assert task.last_error == "source track has no output_path on disk; rip not complete or raw deleted"
    assert sent[0]["event_type"] == "task.failed"


async def test_none_task_output_path_fails_cleanly(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    raw = tmp_path / "raw" / "job1" / "t0.mkv"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"data")

    db = _db(track_output_path=str(raw), task_output_path=None)
    hub, sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]

    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is False
    assert task.status == TranscodeTaskStatus.FAILED
    assert task.last_error == "task has no output_path"
    assert sent[0]["event_type"] == "task.failed"
    # Source file must be left untouched — nothing to move it to.
    assert raw.exists()


async def test_oserror_from_move_is_captured_as_last_error(tmp_path: Path, monkeypatch: Any) -> None:
    raw = tmp_path / "raw" / "job1" / "t0.mkv"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"data")
    media_root = tmp_path / "media"

    db = _db(track_output_path=str(raw), task_output_path="Title (2020)/t0.mkv")
    hub, sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]

    import arm_backend.passthrough_executor as mod

    def _boom(_input: Path, _output: Path) -> int:
        raise OSError("disk full")

    monkeypatch.setattr(mod, "transcode_none", _boom)

    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is False
    assert task.status == TranscodeTaskStatus.FAILED
    assert task.last_error == "OSError: disk full"
    assert sent[0]["event_type"] == "task.failed"


async def test_claim_is_committed_before_the_move_runs(tmp_path: Path, monkeypatch: Any) -> None:
    """I1: the IN_PROGRESS claim must be durably committed before the
    (possibly slow, cross-mount) move starts, so the tick's FOR UPDATE row
    locks are released before any blocking I/O, not held across it."""
    raw = tmp_path / "raw" / "job1" / "t0.mkv"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"data")
    media_root = tmp_path / "media"

    db = _db(track_output_path=str(raw), task_output_path="Title (2020)/t0.mkv")
    hub, _sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]

    import arm_backend.passthrough_executor as mod

    commits_before_move: list[int] = []
    real_transcode_none = mod.transcode_none

    def _spy_transcode_none(input_path: Path, output_path: Path) -> int:
        commits_before_move.append(db.committed)
        return real_transcode_none(input_path, output_path)

    monkeypatch.setattr(mod, "transcode_none", _spy_transcode_none)

    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is True
    assert commits_before_move == [1]  # claim already committed by the time the move ran
    assert db.committed == 2  # claim commit + terminal-state commit


async def test_row_deleted_mid_move_skips_terminal_update_cleanly(tmp_path: Path, monkeypatch: Any) -> None:
    """I1/O3: cancel_running runs in a different session and can delete the
    task row while the move is in flight (after the claim commit). The
    terminal-state write must be skipped cleanly rather than resurrecting a
    row a concurrent cancel already removed."""
    raw = tmp_path / "raw" / "job1" / "t0.mkv"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"data")
    media_root = tmp_path / "media"

    db = _db(track_output_path=str(raw), task_output_path="Title (2020)/t0.mkv")
    hub, sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]

    import arm_backend.passthrough_executor as mod

    real_transcode_none = mod.transcode_none

    def _delete_row_then_move(input_path: Path, output_path: Path) -> int:
        # Simulate a concurrent cancel_running deleting the row (from a
        # different session) while this move is in flight.
        db.rows["transcode_tasks"] = [t for t in db.rows["transcode_tasks"] if t.id != task.id]
        return real_transcode_none(input_path, output_path)

    monkeypatch.setattr(mod, "transcode_none", _delete_row_then_move)

    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is True  # the move itself succeeded (error is None)
    assert db.rows["transcode_tasks"] == []  # row stays deleted, not resurrected
    assert sent == []  # no task.completed/failed event for a cancelled task
    assert (media_root / "Title (2020)" / "t0.mkv").exists()  # the move still happened


async def test_chown_applied_when_transcode_puid_configured(tmp_path: Path, monkeypatch: Any) -> None:
    raw = tmp_path / "raw" / "job1" / "t0.mkv"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"data")
    media_root = tmp_path / "media"

    db = _db(track_output_path=str(raw), task_output_path="Title (2020)/t0.mkv")
    hub, _sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]

    import arm_backend.passthrough_executor as mod

    calls: list[tuple[Path, int, int]] = []

    def _fake_chown(path: Path, uid: int, gid: int) -> None:
        calls.append((path, uid, gid))

    monkeypatch.setattr(mod.os, "chown", _fake_chown)

    settings = _settings(MEDIA_ROOT=str(media_root), ARM_TRANSCODE_PUID="1001", ARM_TRANSCODE_PGID="1000")
    ok = await execute_passthrough_task(db, task, hub, settings)

    assert ok is True
    assert len(calls) == 1
    assert calls[0][1] == 1001
    assert calls[0][2] == 1000


async def test_chown_skipped_without_transcode_puid(tmp_path: Path, monkeypatch: Any) -> None:
    raw = tmp_path / "raw" / "job1" / "t0.mkv"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"data")
    media_root = tmp_path / "media"

    db = _db(track_output_path=str(raw), task_output_path="Title (2020)/t0.mkv")
    hub, _sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]

    import arm_backend.passthrough_executor as mod

    calls: list[Any] = []
    monkeypatch.setattr(mod.os, "chown", lambda *a, **kw: calls.append((a, kw)))

    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is True
    assert calls == []


async def test_chown_failure_is_best_effort_and_does_not_fail_task(tmp_path: Path, monkeypatch: Any) -> None:
    raw = tmp_path / "raw" / "job1" / "t0.mkv"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"data")
    media_root = tmp_path / "media"

    db = _db(track_output_path=str(raw), task_output_path="Title (2020)/t0.mkv")
    hub, sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]

    import arm_backend.passthrough_executor as mod

    def _boom(*_a: Any, **_kw: Any) -> None:
        raise OSError("not permitted")

    monkeypatch.setattr(mod.os, "chown", _boom)

    settings = _settings(MEDIA_ROOT=str(media_root), ARM_TRANSCODE_PUID="1001")
    ok = await execute_passthrough_task(db, task, hub, settings)

    assert ok is True
    assert task.status == TranscodeTaskStatus.DONE
    assert sent[0]["event_type"] == "task.completed"


async def test_attempts_incremented_on_each_run(tmp_path: Path) -> None:
    raw = tmp_path / "raw" / "job1" / "t0.mkv"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"data")
    media_root = tmp_path / "media"

    db = _db(track_output_path=str(raw), task_output_path="Title (2020)/t0.mkv", task_attempts=2)
    hub, _sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]

    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is True
    assert task.attempts == 3


async def test_aggregate_still_running_emits_no_second_event(tmp_path: Path) -> None:
    """A sibling task under the same application is still QUEUED, so
    aggregate_session_application leaves the application RUNNING
    (event_type=None) — only the task.completed event is emitted."""
    raw = tmp_path / "raw" / "job1" / "t0.mkv"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"data")
    media_root = tmp_path / "media"

    db = _db(track_output_path=str(raw), task_output_path="Title (2020)/t0.mkv")
    db.rows["transcode_tasks"].append(
        TranscodeTask(
            id="txt_2",
            session_application_id="sap_x",
            source_track_id="trk_2",
            status=TranscodeTaskStatus.QUEUED,
            attempts=0,
            progress_pct=0,
            output_path="Title (2020)/t1.mkv",
        )
    )
    hub, sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]

    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is True
    application = db.rows["session_applications"][0]
    assert application.status == SessionApplicationStatus.QUEUED  # unchanged, still has a live task
    assert len(sent) == 1
    assert sent[0]["event_type"] == "task.completed"


async def test_no_application_row_skips_aggregate(tmp_path: Path) -> None:
    """Defensive: session_application_id points nowhere (shouldn't happen in
    practice, but the row lookup can legitimately miss under a hard
    FakeSession/test setup). The task itself still completes and only the
    task.completed event is emitted."""
    raw = tmp_path / "raw" / "job1" / "t0.mkv"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"data")
    media_root = tmp_path / "media"

    db = _db(track_output_path=str(raw), task_output_path="Title (2020)/t0.mkv")
    db.rows["session_applications"] = []
    hub, sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]

    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is True
    assert len(sent) == 1
    assert sent[0]["event_type"] == "task.completed"
