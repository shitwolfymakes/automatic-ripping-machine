"""Tests for the in-process passthrough executor.

`execute_passthrough_task` runs one QUEUED passthrough (TranscodeTool.NONE)
task to completion in the backend process instead of spawning a transcoder
container. The lifecycle must mirror `routers/transcoder.py`'s complete/fail
endpoints exactly (claim fields, application QUEUED -> RUNNING,
session.started/task.started/task.completed/task.failed WS events,
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
    track_kind: TrackKind = TrackKind.VIDEO_TITLE,
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
            kind=track_kind,
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
    assert task.started_at is not None
    assert (media_root / "Title (2020)" / "t0.mkv").read_bytes() == b"data"
    assert not raw.exists()

    application = db.rows["session_applications"][0]
    assert application.status == SessionApplicationStatus.DONE

    assert [e["event_type"] for e in sent] == [
        "session.started",
        "task.started",
        "task.completed",
        "session.completed",
    ]
    assert sent[2]["payload"]["task_id"] == "txt_1"
    assert sent[2]["payload"]["output_path"] == "Title (2020)/t0.mkv"
    assert sent[2]["payload"]["size_bytes"] == 4
    # Pin the exact event_type aggregate_session_application returns for the
    # all-done case (see arm_backend.transcode_apply.aggregate_session_application).
    assert sent[3]["payload"]["session_application_id"] == "sap_x"
    assert sent[3]["payload"]["status"] == "done"


async def test_claim_mirrors_claim_router_side_effects(tmp_path: Path, monkeypatch: Any) -> None:
    """The in-process claim performs the same side effects as the container
    path's POST /tasks/{id}/claim: the application flips QUEUED -> RUNNING
    (with session.started) and task.started carries claimed_by + attempts,
    all before the move runs, with progress reset to 0."""
    raw = tmp_path / "raw" / "job1" / "t0.mkv"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"data")
    media_root = tmp_path / "media"

    db = _db(track_output_path=str(raw), task_output_path="Title (2020)/t0.mkv", task_attempts=1)
    task = db.rows["transcode_tasks"][0]
    task.progress_pct = 37
    hub, sent = _hub_with_recorder()
    application = db.rows["session_applications"][0]

    import arm_backend.passthrough_executor as mod

    seen_during_move: dict[str, Any] = {}
    real_transcode_none = mod.transcode_none

    def _spy(input_path: Path, output_path: Path, **kwargs: Any) -> int:
        seen_during_move["app_status"] = application.status
        seen_during_move["progress_pct"] = task.progress_pct
        seen_during_move["events"] = [e["event_type"] for e in sent]
        return real_transcode_none(input_path, output_path, **kwargs)

    monkeypatch.setattr(mod, "transcode_none", _spy)

    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is True
    assert seen_during_move == {
        "app_status": SessionApplicationStatus.RUNNING,
        "progress_pct": 0,
        "events": ["session.started", "task.started"],
    }
    assert sent[0]["topic"] == "transcode.events"
    assert sent[0]["payload"] == {
        "session_application_id": "sap_x",
        "session_id": "ses_x",
        "job_id": "job_01JZXR7K3M5Q8N4VWA00000001",
    }
    assert sent[0]["job_id"] == "job_01JZXR7K3M5Q8N4VWA00000001"
    assert sent[1]["payload"] == {
        "task_id": "txt_1",
        "session_application_id": "sap_x",
        "claimed_by": IN_PROCESS_CLAIMANT,
        "attempts": 2,
    }
    assert sent[1]["job_id"] == "job_01JZXR7K3M5Q8N4VWA00000001"
    assert sent[1]["track_id"] == "trk_1"


async def test_claim_on_already_running_application_skips_session_started(tmp_path: Path) -> None:
    """A sibling task already moved the application to RUNNING: only
    task.started is emitted at claim time (router parity)."""
    raw = tmp_path / "raw" / "job1" / "t0.mkv"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"data")
    media_root = tmp_path / "media"

    db = _db(track_output_path=str(raw), task_output_path="Title (2020)/t0.mkv")
    db.rows["session_applications"][0].status = SessionApplicationStatus.RUNNING
    hub, sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]

    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is True
    assert [e["event_type"] for e in sent] == ["task.started", "task.completed", "session.completed"]


async def test_row_already_deleted_before_claim_skips_cleanly(tmp_path: Path) -> None:
    """The tick's initial FOR UPDATE SKIP LOCKED select can grab
    this row minutes before this task's turn in the loop (an earlier task's
    move can run long); by the time we get here a concurrent
    DELETE /api/transcodes/{id} may already have removed it. Attempting the
    claim UPDATE against a gone row raises StaleDataError, so the pre-claim
    re-select must catch this and skip instead."""
    raw = tmp_path / "raw" / "job1" / "t0.mkv"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"data")
    media_root = tmp_path / "media"

    db = _db(track_output_path=str(raw), task_output_path="Title (2020)/t0.mkv")
    hub, sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]
    db.rows["transcode_tasks"] = []  # simulate the concurrent delete

    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is None
    assert sent == []  # never claimed, so no task.completed/failed event
    assert not (media_root / "Title (2020)" / "t0.mkv").exists()  # move never ran
    assert raw.exists()  # source untouched


async def test_row_no_longer_queued_before_claim_skips_cleanly(tmp_path: Path) -> None:
    """Same as above but the row still exists and was merely repurposed
    (status changed by a concurrent writer) rather than deleted outright."""
    raw = tmp_path / "raw" / "job1" / "t0.mkv"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"data")
    media_root = tmp_path / "media"

    db = _db(track_output_path=str(raw), task_output_path="Title (2020)/t0.mkv")
    hub, sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]
    db.rows["transcode_tasks"][0].status = TranscodeTaskStatus.FAILED  # no longer QUEUED

    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is None
    assert sent == []
    assert raw.exists()


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

    assert sent[2]["event_type"] == "task.failed"
    assert sent[2]["payload"]["last_error"] == task.last_error
    assert sent[3]["event_type"] == "session.failed"


async def test_empty_track_output_path_fails_cleanly(tmp_path: Path) -> None:
    media_root = tmp_path / "media"
    db = _db(track_output_path="", task_output_path="Title (2020)/t0.mkv")
    hub, sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]

    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is False
    assert task.status == TranscodeTaskStatus.FAILED
    assert task.last_error == "source track has no output_path on disk; rip not complete or raw deleted"
    assert sent[2]["event_type"] == "task.failed"


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
    assert sent[2]["event_type"] == "task.failed"
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

    def _boom(_input: Path, _output: Path, **_kwargs: Any) -> int:
        raise OSError("disk full")

    monkeypatch.setattr(mod, "transcode_none", _boom)

    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is False
    assert task.status == TranscodeTaskStatus.FAILED
    assert task.last_error == "OSError: disk full"
    assert sent[2]["event_type"] == "task.failed"


async def test_claim_is_committed_before_the_move_runs(tmp_path: Path, monkeypatch: Any) -> None:
    """The IN_PROGRESS claim must be durably committed before the
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

    def _spy_transcode_none(input_path: Path, output_path: Path, **kwargs: Any) -> int:
        commits_before_move.append(db.committed)
        return real_transcode_none(input_path, output_path, **kwargs)

    monkeypatch.setattr(mod, "transcode_none", _spy_transcode_none)

    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is True
    assert commits_before_move == [1]  # claim already committed by the time the move ran
    assert db.committed == 2  # claim commit + terminal-state commit


async def test_row_deleted_mid_move_skips_terminal_update_cleanly(tmp_path: Path, monkeypatch: Any) -> None:
    """cancel_running runs in a different session and can delete the
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

    def _delete_row_then_move(input_path: Path, output_path: Path, **kwargs: Any) -> int:
        # Simulate a concurrent cancel_running deleting the row (from a
        # different session) while this move is in flight.
        db.rows["transcode_tasks"] = [t for t in db.rows["transcode_tasks"] if t.id != task.id]
        return real_transcode_none(input_path, output_path, **kwargs)

    monkeypatch.setattr(mod, "transcode_none", _delete_row_then_move)

    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is True  # the move itself succeeded (error is None)
    assert db.rows["transcode_tasks"] == []  # row stays deleted, not resurrected
    # Only the claim-time events; no task.completed/failed for a cancelled task.
    assert [e["event_type"] for e in sent] == ["session.started", "task.started"]
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
    assert sent[2]["event_type"] == "task.completed"


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
    assert application.status == SessionApplicationStatus.RUNNING  # claim flipped it; a sibling is still live
    assert [e["event_type"] for e in sent] == ["session.started", "task.started", "task.completed"]


async def test_no_application_row_skips_aggregate(tmp_path: Path) -> None:
    """Defensive: session_application_id points nowhere (shouldn't happen in
    practice, but the row lookup can legitimately miss under a hard
    FakeSession/test setup). The task itself still completes and only the
    task-level events are emitted."""
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
    assert [e["event_type"] for e in sent] == ["task.started", "task.completed"]


def _backup_dir(root: Path) -> Path:
    (root / "BDMV").mkdir(parents=True)
    (root / "BDMV" / "index.bdmv").write_bytes(b"idx")
    return root


async def test_disc_backup_is_moved_as_a_folder(tmp_path: Path) -> None:
    raw = _backup_dir(tmp_path / "raw" / "job1" / "backup")
    media_root = tmp_path / "media"
    db = _db(track_output_path=str(raw), task_output_path="Iron Man (2008)", track_kind=TrackKind.DISC_BACKUP)
    hub, sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]

    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is True
    assert (media_root / "Iron Man (2008)" / "BDMV" / "index.bdmv").read_bytes() == b"idx"
    assert not raw.exists()
    assert sent[2]["payload"]["size_bytes"] == 3


async def test_a_same_filesystem_folder_move_does_not_size_the_tree_first(tmp_path: Path, monkeypatch: Any) -> None:
    """D-127 follow-up: a same-filesystem move is a rename. Sizing the tree
    for progress is needed only once a copy starts copying bytes."""
    import arm_backend.passthrough_executor as mod

    raw = _backup_dir(tmp_path / "raw" / "job1" / "backup")
    db = _db(track_output_path=str(raw), task_output_path="Iron Man (2008)", track_kind=TrackKind.DISC_BACKUP)
    hub, _sent = _hub_with_recorder()
    sized: list[Path] = []
    monkeypatch.setattr(mod, "tree_size", lambda root: sized.append(root) or 0)

    ok = await execute_passthrough_task(
        db, db.rows["transcode_tasks"][0], hub, _settings(MEDIA_ROOT=str(tmp_path / "m"))
    )

    assert ok is True and sized == []


def test_copy_progress_sizes_the_tree_on_the_first_copied_bytes() -> None:
    from arm_backend.passthrough_executor import _CopyProgress

    progress = _CopyProgress(sizer=lambda: 300)
    assert progress.total == 0
    progress.add(100)
    progress.add(50)
    assert (progress.total, progress.done) == (300, 150)


async def test_disc_backup_onto_an_existing_folder_fails_and_keeps_it(tmp_path: Path) -> None:
    raw = _backup_dir(tmp_path / "raw" / "job1" / "backup")
    media_root = tmp_path / "media"
    existing = media_root / "Iron Man (2008)"
    existing.mkdir(parents=True)
    (existing / "old.txt").write_text("keep")
    db = _db(track_output_path=str(raw), task_output_path="Iron Man (2008)", track_kind=TrackKind.DISC_BACKUP)
    hub, _sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]

    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is False
    assert "FileExistsError" in (task.last_error or "")
    assert sorted(p.name for p in existing.iterdir()) == ["old.txt"]
    assert raw.exists()


async def test_disc_backup_chowns_the_whole_tree(tmp_path: Path, monkeypatch: Any) -> None:
    raw = _backup_dir(tmp_path / "raw" / "job1" / "backup")
    media_root = tmp_path / "media"
    db = _db(track_output_path=str(raw), task_output_path="Iron Man (2008)", track_kind=TrackKind.DISC_BACKUP)
    hub, _sent = _hub_with_recorder()
    chowned: list[Path] = []
    monkeypatch.setattr("arm_backend.passthrough_executor.os.chown", lambda p, _u, _g: chowned.append(Path(p)))

    await execute_passthrough_task(
        db,
        db.rows["transcode_tasks"][0],
        hub,
        _settings(MEDIA_ROOT=str(media_root), ARM_TRANSCODE_PUID="1000", ARM_TRANSCODE_PGID="1000"),
    )

    final = media_root / "Iron Man (2008)"
    assert set(chowned) == {final, final / "BDMV", final / "BDMV" / "index.bdmv"}


async def test_disc_backup_tree_chown_runs_off_the_event_loop(tmp_path: Path, monkeypatch: Any) -> None:
    """Chowning a whole backup tree walks thousands of files: it runs in the
    worker thread with the move, never on the event loop."""
    import threading

    raw = _backup_dir(tmp_path / "raw" / "job1" / "backup")
    media_root = tmp_path / "media"
    db = _db(track_output_path=str(raw), task_output_path="Iron Man (2008)", track_kind=TrackKind.DISC_BACKUP)
    hub, _sent = _hub_with_recorder()
    threads: set[int] = set()
    monkeypatch.setattr(
        "arm_backend.passthrough_executor.os.chown", lambda _p, _u, _g: threads.add(threading.get_ident())
    )

    ok = await execute_passthrough_task(
        db,
        db.rows["transcode_tasks"][0],
        hub,
        _settings(MEDIA_ROOT=str(media_root), ARM_TRANSCODE_PUID="1000", ARM_TRANSCODE_PGID="1000"),
    )

    assert ok is True
    assert threads
    assert threading.get_ident() not in threads


async def test_cancel_stops_an_in_flight_copy_and_keeps_the_raw_source(tmp_path: Path, monkeypatch: Any) -> None:
    """D-066: there is no container to stop, so cancel_running's
    request_cancel must stop the copy itself: nothing lands in /media, the
    raw source stays, and the task fails as cancelled."""
    raw = tmp_path / "raw" / "job1" / "t0.mkv"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"data")
    media_root = tmp_path / "media"
    db = _db(track_output_path=str(raw), task_output_path="Title (2020)/t0.mkv")
    hub, sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]

    import arm_backend.passthrough_executor as mod
    from arm_common import fileops

    def _exdev(a: object, b: object) -> None:
        raise OSError(18, "Invalid cross-device link")

    monkeypatch.setattr(fileops.os, "rename", _exdev)
    real_transcode_none = mod.transcode_none

    def _cancel_then_move(input_path: Path, output_path: Path, **kwargs: Any) -> int:
        assert mod.request_cancel("txt_1") is True  # what cancel_running does mid-copy
        return real_transcode_none(input_path, output_path, **kwargs)

    monkeypatch.setattr(mod, "transcode_none", _cancel_then_move)
    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is False and task.status == TranscodeTaskStatus.FAILED and task.last_error == "cancelled"
    assert raw.read_bytes() == b"data"
    assert list((media_root / "Title (2020)").iterdir()) == []
    assert "task.failed" in [e["event_type"] for e in sent]
    assert mod.request_cancel("txt_1") is False  # unregistered once the move ends


async def test_copy_publishes_progress_while_it_runs(tmp_path: Path, monkeypatch: Any) -> None:
    """D-127: a long cross-mount copy heartbeats progress_pct onto the row and
    publishes transcode.progress, instead of sitting at 0 % until it ends."""
    import threading

    raw = tmp_path / "raw" / "job1" / "t0.mkv"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"x" * 100)
    media_root = tmp_path / "media"
    db = _db(track_output_path=str(raw), task_output_path="Title (2020)/t0.mkv")
    hub, sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]

    import arm_backend.passthrough_executor as mod

    monkeypatch.setattr(mod, "PROGRESS_INTERVAL_SECONDS", 0.01)
    seen_pct: list[int] = []

    def _slow_copy(input_path: Path, output_path: Path, *, on_bytes: Any, **_kw: Any) -> int:
        on_bytes(50)
        # Hold the copy at 50 % until the row shows it.
        for _ in range(500):
            if db.rows["transcode_tasks"][0].progress_pct == 50:
                break
            threading.Event().wait(0.01)
        seen_pct.append(db.rows["transcode_tasks"][0].progress_pct)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        input_path.rename(output_path)
        return 100

    monkeypatch.setattr(mod, "transcode_none", _slow_copy)
    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(media_root)))

    assert ok is True and seen_pct == [50] and task.progress_pct == 100
    progress = [e for e in sent if e["event_type"] == "transcode.progress"]
    assert progress and progress[0]["topic"] == "transcode.progress.txt_1"
    assert progress[0]["payload"]["progress_pct"] == 50 and progress[0]["persist"] is False


async def test_a_failing_progress_publish_does_not_strand_the_task(tmp_path: Path, monkeypatch: Any) -> None:
    """D-127 follow-up: a hub error while publishing progress is telemetry
    only. The move's result still lands as the task's terminal status."""
    import threading

    raw = tmp_path / "raw" / "job1" / "t0.mkv"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"x" * 100)
    db = _db(track_output_path=str(raw), task_output_path="Title (2020)/t0.mkv")
    hub, sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]
    progress_tried = threading.Event()

    async def _emit(**kwargs: Any) -> None:
        if kwargs["event_type"] == "transcode.progress":
            progress_tried.set()
            raise RuntimeError("hub down")
        sent.append(kwargs)

    hub.emit = _emit  # type: ignore[method-assign]

    import arm_backend.passthrough_executor as mod

    monkeypatch.setattr(mod, "PROGRESS_INTERVAL_SECONDS", 0.01)

    def _slow_copy(input_path: Path, output_path: Path, *, on_bytes: Any, **_kw: Any) -> int:
        on_bytes(50)
        progress_tried.wait(5)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        input_path.rename(output_path)
        return 100

    monkeypatch.setattr(mod, "transcode_none", _slow_copy)
    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(tmp_path / "media")))

    assert progress_tried.is_set()
    assert ok is True and task.status == TranscodeTaskStatus.DONE


async def test_a_crashing_progress_publisher_does_not_change_the_result(
    tmp_path: Path, monkeypatch: Any, caplog: Any
) -> None:
    """The publisher is awaited after the move; whatever it raises is logged
    and the move's own result still decides the task's terminal state."""
    raw = tmp_path / "raw" / "job1" / "t0.mkv"
    raw.parent.mkdir(parents=True)
    raw.write_bytes(b"x" * 100)
    db = _db(track_output_path=str(raw), task_output_path="Title (2020)/t0.mkv")
    hub, _sent = _hub_with_recorder()
    task = db.rows["transcode_tasks"][0]

    import arm_backend.passthrough_executor as mod

    async def _crashing_publisher(*_args: Any) -> None:
        raise RuntimeError("publisher bug")

    monkeypatch.setattr(mod, "_publish_progress", _crashing_publisher)
    ok = await execute_passthrough_task(db, task, hub, _settings(MEDIA_ROOT=str(tmp_path / "media")))

    assert ok is True and task.status == TranscodeTaskStatus.DONE
    assert "passthrough progress publisher failed task_id=txt_1" in caplog.text


async def test_progress_publisher_skips_unknown_totals_and_repeat_percentages(monkeypatch: Any) -> None:
    """No total yet (the sizer has not run) publishes nothing, and an unchanged
    percentage is not re-published."""
    import asyncio

    import arm_backend.passthrough_executor as mod

    monkeypatch.setattr(mod, "PROGRESS_INTERVAL_SECONDS", 0.001)
    stop = asyncio.Event()
    hub, sent = _hub_with_recorder()

    class _Progress:
        done = 50
        reads = 0

        @property
        def total(self) -> int:
            self.reads += 1
            if self.reads == 1:
                return 0  # first tick: total unknown
            if sent:
                stop.set()  # a tick after the publish: same 50 %, then stop
            return 100

    db = FakeSession()
    await mod._publish_progress(db, hub, "txt_1", None, None, _Progress(), stop)  # type: ignore[arg-type]

    assert [e["payload"]["progress_pct"] for e in sent] == [50]
    assert db.committed == 1


async def test_progress_publisher_stops_after_a_failed_write(monkeypatch: Any, caplog: Any) -> None:
    """A failed heartbeat write rolls back and ends progress reporting; the
    copy itself is unaffected."""
    import asyncio

    import arm_backend.passthrough_executor as mod
    from arm_backend.passthrough_executor import _CopyProgress

    monkeypatch.setattr(mod, "PROGRESS_INTERVAL_SECONDS", 0.001)
    hub, sent = _hub_with_recorder()
    db = FakeSession()

    async def _raising_execute(_stmt: Any) -> None:
        raise RuntimeError("db gone")

    monkeypatch.setattr(db, "execute", _raising_execute)
    progress = _CopyProgress()
    progress.add(50)
    progress.total = 100

    await mod._publish_progress(db, hub, "txt_1", None, None, progress, asyncio.Event())

    assert db.call_log[-1] == "rollback" and sent == []
    assert "progress write failed task_id=txt_1" in caplog.text
