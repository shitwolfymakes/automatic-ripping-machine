"""The stager: decisions, claim, placement, the run's transitions, the publisher and the worker loop.

Real aiosqlite and `tmp_path` files; the only fakes are the hub and (where a test needs a copy to
fail, block or finish late) `place_staged`, the one I/O boundary the run calls."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from arm_backend import stager
from arm_backend.stager import (
    TrackStager,
    _Plan,
    _StageProgress,
    cancel_job_staging,
    claim_next_stage,
    eta_seconds,
    error_text,
    is_stalled,
    place_staged,
    refund_attempt,
    set_active_stager,
    status_after_failure,
    transfer_rate,
    wake_active_stager,
)
from arm_common import StageStatus, Track, TrackStage, TrackStatus
from arm_common import fileops
from arm_common.fileops import CopyCancelled, LinkUnavailable, PlaceResult, SourceChanged, SourceStamp
from tests._stage_env import JOB, Env, add_job, add_stage, add_track, load_stage, seed_stage

BYTES = b"ripped bytes"


def _dest(env: Env, track_id: str = "trk_a") -> Path:
    return env.raw / ".staging" / JOB / f"{track_id}.mkv"


def _stager(env: Env, **kw: Any) -> TrackStager:
    return TrackStager(env.settings, env.hub, env.factory, **kw)  # type: ignore[arg-type]


async def _run_one(env: Env, stage_id: str) -> None:
    """Claim the stage and run it once, as the worker does."""
    worker = _stager(env)
    assert await worker._work_once() is True
    assert (await load_stage(env, stage_id)).attempts >= 0


@pytest.fixture
def fast_ticks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stager, "PROGRESS_INTERVAL_SECONDS", 0.01)


# --- pure decisions -------------------------------------------------------------------------


def test_is_stalled_only_past_the_threshold() -> None:
    assert not is_stalled(100.0, 400.0, 300.0)
    assert is_stalled(100.0, 400.1, 300.0)


def test_status_after_failure_retries_until_attempts_are_spent() -> None:
    assert status_after_failure(2, 3) == StageStatus.PENDING
    assert status_after_failure(3, 3) == StageStatus.FAILED


def test_transfer_rate_and_eta() -> None:
    assert transfer_rate(100, 2.0) == 50.0
    assert transfer_rate(100, 0.0) == 0.0
    assert eta_seconds(50, 150, 50.0) == 2
    assert eta_seconds(50, 150, 0.0) is None


def test_refund_attempt_never_goes_negative() -> None:
    assert refund_attempt(2) == 1
    assert refund_attempt(0) == 0


def test_error_text_names_the_exception_and_is_capped() -> None:
    assert error_text(OSError("disk")) == "OSError: disk"
    assert len(error_text(OSError("x" * 1000))) == 300


# --- claim ------------------------------------------------------------------------------------


async def test_claim_takes_the_oldest_pending_stage_of_a_done_track(env: Env) -> None:
    async with env.factory() as db:
        await add_job(db)
        for tid in ("trk_young", "trk_old"):
            track = await add_track(env, db, tid)
            await add_stage(env, db, track, created_at=datetime(2026, 1, 2 if tid == "trk_young" else 1, tzinfo=UTC))
        await db.commit()
    async with env.factory() as db:
        stage_id = await claim_next_stage(db, env.hub)  # type: ignore[arg-type]
    assert stage_id is not None
    claimed = await load_stage(env, stage_id)
    assert claimed.track_id == "trk_old"
    assert claimed.status == StageStatus.COPYING
    assert claimed.attempts == 1
    assert claimed.heartbeat_at is not None
    assert claimed.last_error is None
    assert env.hub.types() == ["stage.started"]


async def test_claim_skips_tracks_still_ripping_and_other_statuses(env: Env) -> None:
    async with env.factory() as db:
        await add_job(db)
        ripping = await add_track(env, db, "trk_ripping", status=TrackStatus.IN_PROGRESS)
        await add_stage(env, db, ripping)
        for tid, status in (
            ("trk_c", StageStatus.COPYING),
            ("trk_s", StageStatus.STAGED),
            ("trk_f", StageStatus.FAILED),
        ):
            await add_stage(env, db, await add_track(env, db, tid), status=status)
        await db.commit()
    async with env.factory() as db:
        assert await claim_next_stage(db, env.hub) is None  # type: ignore[arg-type]
    assert env.hub.calls == []


async def test_claim_locks_only_the_stage_row_and_skips_rows_another_worker_holds(env: Env) -> None:
    from types import SimpleNamespace

    from sqlalchemy.dialects import postgresql

    captured: list[Any] = []

    class _Db:
        async def execute(self, stmt: Any) -> Any:
            captured.append(stmt)
            return SimpleNamespace(scalar_one_or_none=lambda: None)

    assert await claim_next_stage(_Db(), env.hub) is None  # type: ignore[arg-type]
    sql = str(captured[0].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE OF track_stages SKIP LOCKED" in sql
    assert "ORDER BY track_stages.created_at" in sql


# --- placement (worker thread) ------------------------------------------------------------


def _plan(src: Path, dst: Path, *, resume_from: int = 0) -> _Plan:
    return _Plan("stg_x", "trk_a", JOB, src, dst, SourceStamp.of(src), resume_from)


def _progress() -> _StageProgress:
    return _StageProgress(100, lambda: 0.0)


def test_place_staged_links_on_the_same_filesystem(tmp_path: Path) -> None:
    src, dst = tmp_path / "raw.mkv", tmp_path / "stage" / "t.mkv"
    src.write_bytes(BYTES)
    progress = _progress()
    result = place_staged(_plan(src, dst), threading.Event(), progress, lambda n: None)
    assert result == PlaceResult(size=len(BYTES), linked=True)
    assert src.samefile(dst) and src.exists()
    assert progress.done == 0
    assert progress.linked is None


def test_place_staged_copies_when_a_link_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src, dst = tmp_path / "raw.mkv", tmp_path / "stage" / "t.mkv"
    src.write_bytes(BYTES * 5)

    def refuse(*_a: Any, **_k: Any) -> PlaceResult:
        raise LinkUnavailable(18, "cross-device")

    monkeypatch.setattr(stager, "place_by_link", refuse)
    monkeypatch.setattr(fileops, "CHECKPOINT_BYTES", 1)
    monkeypatch.setattr(fileops, "COPY_CHUNK_BYTES", 8)
    checkpoints: list[int] = []
    progress = _progress()
    result = place_staged(_plan(src, dst), threading.Event(), progress, checkpoints.append)
    assert result == PlaceResult(size=len(BYTES * 5), linked=False)
    assert dst.read_bytes() == BYTES * 5 and not src.samefile(dst)
    assert progress.linked is False
    assert checkpoints and checkpoints == sorted(checkpoints)


def test_place_staged_resumes_a_copy_from_its_durable_offset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src, dst = tmp_path / "raw.mkv", tmp_path / "stage" / "t.mkv"
    src.write_bytes(BYTES * 4)
    dst.parent.mkdir()
    fileops.inprogress_path(dst).write_bytes((BYTES * 4)[:20] + b"junk past the checkpoint")
    monkeypatch.setattr(stager, "place_by_link", lambda *_a, **_k: (_ for _ in ()).throw(LinkUnavailable(18, "x")))
    result = place_staged(_plan(src, dst, resume_from=20), threading.Event(), _progress(), lambda n: None)
    assert dst.read_bytes() == BYTES * 4
    assert result == PlaceResult(size=len(BYTES * 4), linked=False)


def test_place_staged_adopts_a_finished_placement_without_reading_raw(tmp_path: Path) -> None:
    src, dst = tmp_path / "raw.mkv", tmp_path / "stage" / "t.mkv"
    src.write_bytes(BYTES)
    dst.parent.mkdir()
    os.link(src, dst)
    progress = _progress()
    result = place_staged(_plan(src, dst), threading.Event(), progress, lambda n: None)
    assert result == PlaceResult(size=len(BYTES), linked=True)
    assert progress.done == 0


def test_place_staged_adopts_a_finished_copy_and_reports_it_unlinked(tmp_path: Path) -> None:
    src, dst = tmp_path / "raw.mkv", tmp_path / "stage" / "t.mkv"
    src.write_bytes(BYTES)
    dst.parent.mkdir()
    shutil.copy2(src, dst)
    assert place_staged(_plan(src, dst), threading.Event(), _progress(), lambda n: None).linked is False


def test_place_staged_does_not_adopt_a_placement_whose_source_changed(tmp_path: Path) -> None:
    src, dst = tmp_path / "raw.mkv", tmp_path / "stage" / "t.mkv"
    src.write_bytes(BYTES)
    dst.parent.mkdir()
    shutil.copy2(src, dst)
    plan = _plan(src, dst)
    os.utime(src, ns=(1, 1))
    with pytest.raises(SourceChanged):
        place_staged(plan, threading.Event(), _progress(), lambda n: None)


def test_place_staged_does_not_adopt_when_a_checkpoint_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src, dst = tmp_path / "raw.mkv", tmp_path / "stage" / "t.mkv"
    src.write_bytes(BYTES)
    dst.parent.mkdir()
    os.link(src, dst)
    seen: list[str] = []
    monkeypatch.setattr(stager, "_adopt_placed", lambda *_a: seen.append("adopted"))
    result = place_staged(_plan(src, dst, resume_from=5), threading.Event(), _progress(), lambda n: None)
    assert seen == [] and result.linked is True


def test_a_cancelled_copy_pass_keeps_the_source_and_places_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src, dst = tmp_path / "raw.mkv", tmp_path / "stage" / "t.mkv"
    src.write_bytes(BYTES)
    monkeypatch.setattr(stager, "place_by_link", lambda *_a, **_k: (_ for _ in ()).throw(LinkUnavailable(18, "x")))
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(CopyCancelled):
        place_staged(_plan(src, dst), cancel, _progress(), lambda n: None)
    assert src.exists() and not dst.exists()


def test_remove_staged_files_deletes_the_destination_and_its_temp(tmp_path: Path) -> None:
    dst = tmp_path / "t.mkv"
    dst.write_bytes(b"x")
    fileops.inprogress_path(dst).write_bytes(b"y")
    stager._remove_staged_files(dst)
    stager._remove_staged_files(dst)  # idempotent
    assert not dst.exists() and not fileops.inprogress_path(dst).exists()


# --- a whole run ------------------------------------------------------------------------------


async def test_pending_becomes_staged(env: Env) -> None:
    stage_id = await seed_stage(env)
    await _run_one(env, stage_id)
    stage = await load_stage(env, stage_id)
    assert stage.status == StageStatus.STAGED
    assert stage.linked is True and stage.bytes_durable == len(BYTES)
    assert stage.staged_at is not None and stage.last_error is None
    assert (stage.source_size, stage.attempts) == (len(BYTES), 1)
    assert _dest(env).read_bytes() == BYTES
    assert env.hub.types() == ["stage.started", "stage.completed"]
    assert env.hub.calls[-1]["payload"]["status"] == "staged"


async def test_a_track_deleted_before_the_commit_still_stages(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    stage_id = await seed_stage(env)

    def place_and_drop_the_track(plan: _Plan, *a: Any) -> PlaceResult:
        async def drop() -> None:
            async with env.factory() as db:
                await db.delete(await db.get(Track, "trk_a"))
                await db.commit()

        asyncio.run(drop())
        return PlaceResult(size=1, linked=True)

    monkeypatch.setattr(stager, "place_staged", place_and_drop_the_track)
    worker = _stager(env)
    await worker._work_once()
    assert (await load_stage(env, stage_id)).status == StageStatus.STAGED


async def test_the_source_is_stamped_on_first_run_and_kept_on_later_ones(env: Env) -> None:
    stage_id = await seed_stage(env)
    src = Path((await load_stage(env, stage_id)).source_path)
    await _run_one(env, stage_id)
    first = await load_stage(env, stage_id)
    assert first.source_size == len(BYTES)
    assert first.source_mtime_ns == src.stat().st_mtime_ns


async def test_a_missing_source_fails_the_stage_at_once(env: Env) -> None:
    stage_id = await seed_stage(env)
    Path((await load_stage(env, stage_id)).source_path).unlink()
    await _run_one(env, stage_id)
    stage = await load_stage(env, stage_id)
    assert stage.status == StageStatus.FAILED and stage.last_error == "raw source missing"
    assert env.hub.types() == ["stage.started", "stage.failed"]


async def test_an_oserror_retries_until_attempts_are_spent_then_fails(
    env: Env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage_id = await seed_stage(env)

    def boom(*_a: Any) -> PlaceResult:
        raise OSError("read error on /raw")

    monkeypatch.setattr(stager, "place_staged", boom)
    seen = []
    for _ in range(3):
        await _stager(env)._work_once()
        stage = await load_stage(env, stage_id)
        seen.append((stage.status, stage.attempts))
    assert seen == [(StageStatus.PENDING, 1), (StageStatus.PENDING, 2), (StageStatus.FAILED, 3)]
    assert stage.last_error == "OSError: read error on /raw"
    assert env.hub.types().count("stage.failed") == 1
    assert env.hub.types()[-1] == "stage.failed"


async def test_a_changed_source_resets_without_spending_an_attempt(
    env: Env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage_id = await seed_stage(env, bytes_durable=5, attempts=1)
    _dest(env).parent.mkdir(parents=True)
    _dest(env).write_bytes(b"old inode")
    fileops.inprogress_path(_dest(env)).write_bytes(b"old tmp")

    def changed(*_a: Any) -> PlaceResult:
        raise SourceChanged("re-ripped")

    monkeypatch.setattr(stager, "place_staged", changed)
    await _stager(env)._work_once()
    stage = await load_stage(env, stage_id)
    assert stage.status == StageStatus.PENDING
    assert (stage.attempts, stage.bytes_durable) == (1, 0)  # claim made it 2, the reset refunds it
    assert stage.source_size is None and stage.source_mtime_ns is None and stage.linked is None
    assert not _dest(env).exists() and not fileops.inprogress_path(_dest(env)).exists()
    assert env.hub.types() == ["stage.started", "stage.restarted"]


async def test_a_shutdown_cancel_returns_the_stage_to_pending_with_its_checkpoint(
    env: Env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage_id = await seed_stage(env, bytes_durable=9)

    def cancelled(*_a: Any) -> PlaceResult:
        raise CopyCancelled("stopping")

    monkeypatch.setattr(stager, "place_staged", cancelled)
    await _stager(env)._work_once()
    stage = await load_stage(env, stage_id)
    assert (stage.status, stage.bytes_durable, stage.attempts) == (StageStatus.PENDING, 9, 0)
    assert env.hub.types() == ["stage.started"]


async def test_a_vanished_row_ends_the_run_quietly(
    env: Env,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    stage_id = await seed_stage(env)

    def delete_the_row(*_a: Any) -> PlaceResult:
        async def go() -> None:
            async with env.factory() as db:
                await db.delete(await db.get(TrackStage, stage_id))
                await db.commit()

        asyncio.run(go())
        return PlaceResult(size=1, linked=True)

    monkeypatch.setattr(stager, "place_staged", delete_the_row)
    with caplog.at_level(logging.INFO, logger="arm_backend.stager"):
        assert await _stager(env)._work_once() is True
    assert "deleted mid-run" in caplog.text


# --- stall ----------------------------------------------------------------------------------


def _blocking_place(outcome: str) -> Any:
    """A `place_staged` that blocks until the run asks it to stop, then ends as `outcome` says."""

    def place(plan: _Plan, cancel: threading.Event, progress: _StageProgress, on_checkpoint: Any) -> PlaceResult:
        assert cancel.wait(5), "the stall watch never cancelled the copy"
        if outcome == "cancelled":
            raise CopyCancelled("stalled")
        return PlaceResult(size=1, linked=True)

    return place


async def test_a_stalled_copy_is_announced_then_requeued(
    env: Env,
    monkeypatch: pytest.MonkeyPatch,
    fast_ticks: None,
) -> None:
    env.settings.ARM_STAGE_STALL_SECONDS = 0
    stage_id = await seed_stage(env)
    monkeypatch.setattr(stager, "place_staged", _blocking_place("cancelled"))
    await _stager(env)._work_once()
    stage = await load_stage(env, stage_id)
    assert stage.status == StageStatus.PENDING
    assert stage.last_error is not None and stage.last_error.startswith("no progress for ")
    assert env.hub.types()[:2] == ["stage.started", "stage.stalled"]
    assert "stage.failed" not in env.hub.types()
    assert env.hub.calls[1]["payload"]["status"] == "stalled"


async def test_a_stalled_copy_with_no_attempts_left_fails(
    env: Env,
    monkeypatch: pytest.MonkeyPatch,
    fast_ticks: None,
) -> None:
    env.settings.ARM_STAGE_STALL_SECONDS = 0
    env.settings.ARM_STAGE_MAX_ATTEMPTS = 1
    stage_id = await seed_stage(env)
    monkeypatch.setattr(stager, "place_staged", _blocking_place("cancelled"))
    await _stager(env)._work_once()
    assert (await load_stage(env, stage_id)).status == StageStatus.FAILED
    assert env.hub.types().count("stage.failed") == 1


async def test_a_stalled_copy_that_finishes_anyway_never_commits_staged(
    env: Env,
    monkeypatch: pytest.MonkeyPatch,
    fast_ticks: None,
) -> None:
    env.settings.ARM_STAGE_STALL_SECONDS = 0
    stage_id = await seed_stage(env)
    monkeypatch.setattr(stager, "place_staged", _blocking_place("late success"))
    await _stager(env)._work_once()
    stage = await load_stage(env, stage_id)
    assert stage.status == StageStatus.PENDING and stage.staged_at is None
    assert "stage.completed" not in env.hub.types()


# --- checkpoints and the publisher --------------------------------------------------------------


async def test_a_checkpoint_commits_after_the_fsync_and_blocks_the_copy_until_it_lands(
    env: Env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage_id = await seed_stage(env)
    order: list[str] = []
    real_fsync = os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: (order.append("fsync"), real_fsync(fd))[1])
    monkeypatch.setattr(stager, "place_by_link", lambda *_a, **_k: (_ for _ in ()).throw(LinkUnavailable(18, "x")))
    monkeypatch.setattr(fileops, "CHECKPOINT_BYTES", 1)
    monkeypatch.setattr(fileops, "COPY_CHUNK_BYTES", 4)
    run_commit = stager._StageRun._commit_checkpoint

    async def spy(self: stager._StageRun, offset: int) -> None:
        order.append(f"commit {offset}")
        await run_commit(self, offset)
        order.append(f"landed {offset}")

    monkeypatch.setattr(stager._StageRun, "_commit_checkpoint", spy)
    await _stager(env)._work_once()
    commits = [i for i, o in enumerate(order) if o.startswith("commit ")]
    assert commits, "no checkpoint was reported"
    for i in commits:
        assert order[i - 1] == "fsync"  # the data was durable before the database heard of it
        assert order[i + 1] == order[i].replace("commit", "landed")  # the copy waited for the commit
    assert (await load_stage(env, stage_id)).status == StageStatus.STAGED


async def test_a_checkpoint_is_ignored_unless_the_row_is_copying(env: Env) -> None:
    stage_id = await seed_stage(env, status=StageStatus.STALLED, bytes_durable=3)
    run = stager._StageRun(stage_id, env.settings, env.hub, env.factory, threading.Event(), lambda: 0.0)  # type: ignore[arg-type]
    await run._commit_checkpoint(99)
    assert (await load_stage(env, stage_id)).bytes_durable == 3


async def test_heartbeat_moves_only_when_bytes_advance_and_progress_is_published(
    env: Env,
    monkeypatch: pytest.MonkeyPatch,
    fast_ticks: None,
) -> None:
    stage_id = await seed_stage(env)
    old = datetime(2026, 1, 1, tzinfo=UTC)
    beats: list[datetime | None] = []

    def place(plan: _Plan, cancel: threading.Event, progress: _StageProgress, on_checkpoint: Any) -> PlaceResult:
        async def reset_heartbeat() -> None:
            async with env.factory() as db:
                (await db.get(TrackStage, stage_id)).heartbeat_at = old  # type: ignore[union-attr]
                await db.commit()

        async def read() -> None:
            beats.append((await load_stage(env, stage_id)).heartbeat_at)

        asyncio.run(reset_heartbeat())
        threading.Event().wait(0.1)  # idle ticks: no bytes yet
        asyncio.run(read())
        progress.linked = False
        progress.add(len(BYTES))
        threading.Event().wait(0.1)  # a tick sees the bytes
        asyncio.run(read())
        return PlaceResult(size=len(BYTES), linked=False)

    monkeypatch.setattr(stager, "place_staged", place)
    await _stager(env)._work_once()
    idle_beat, advanced_beat = beats
    assert idle_beat is not None and idle_beat.replace(tzinfo=UTC) == old
    assert advanced_beat is not None and advanced_beat.replace(tzinfo=UTC) > old
    progress_calls = [c for c in env.hub.calls if c["event_type"] == "stage.progress"]
    assert progress_calls and all(c["persist"] is False for c in progress_calls)
    last = progress_calls[-1]
    assert last["topic"] == "staging.progress.trk_a"
    assert (last["job_id"], last["track_id"]) == (JOB, "trk_a")
    assert set(last["payload"]) == {
        "track_id", "job_id", "bytes_done", "bytes_total", "rate_bps", "eta_seconds", "linked",
    }  # fmt: skip
    assert last["payload"]["bytes_done"] == len(BYTES) and last["payload"]["bytes_total"] == len(BYTES)
    assert last["payload"]["linked"] is False


async def test_a_failing_progress_publish_does_not_stop_the_copy(
    env: Env,
    monkeypatch: pytest.MonkeyPatch,
    fast_ticks: None,
    caplog: pytest.LogCaptureFixture,
) -> None:
    env.hub.fail_progress = True
    stage_id = await seed_stage(env)

    def slow_place(plan: _Plan, cancel: threading.Event, progress: _StageProgress, on_checkpoint: Any) -> PlaceResult:
        threading.Event().wait(0.1)
        return PlaceResult(size=1, linked=True)

    monkeypatch.setattr(stager, "place_staged", slow_place)
    with caplog.at_level(logging.WARNING, logger="arm_backend.stager"):
        await _stager(env)._work_once()
    assert "progress tick failed" in caplog.text
    assert (await load_stage(env, stage_id)).status == StageStatus.STAGED


async def test_a_publisher_that_dies_is_logged_not_raised(env: Env, caplog: pytest.LogCaptureFixture) -> None:
    run = stager._StageRun("stg_x", env.settings, env.hub, env.factory, threading.Event(), lambda: 0.0)  # type: ignore[arg-type]

    async def dies() -> None:
        raise RuntimeError("publisher bug")

    with caplog.at_level(logging.ERROR, logger="arm_backend.stager"):
        await run._stop_publisher(asyncio.ensure_future(dies()), asyncio.Event())
    assert "progress publisher failed" in caplog.text


# --- the worker loop ------------------------------------------------------------------------------


async def test_the_worker_stages_what_is_waiting_idles_and_stops_on_request(
    env: Env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(stager, "IDLE_POLL_SECONDS", 0.01)
    stage_id = await seed_stage(env)
    worker = _stager(env)
    task = asyncio.ensure_future(worker.run())
    for _ in range(200):
        if (await load_stage(env, stage_id)).status == StageStatus.STAGED:
            break
        await asyncio.sleep(0.02)
    worker.wake()
    await asyncio.wait_for(worker.stop(), 5)
    await asyncio.wait_for(task, 5)
    assert (await load_stage(env, stage_id)).status == StageStatus.STAGED


async def test_stop_before_run_returns_at_once(env: Env) -> None:
    await asyncio.wait_for(_stager(env).stop(), 1)


async def test_stop_cancels_the_copy_in_flight(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    stage_id = await seed_stage(env)
    started = threading.Event()

    def place(plan: _Plan, cancel: threading.Event, progress: _StageProgress, on_checkpoint: Any) -> PlaceResult:
        started.set()
        assert cancel.wait(5)
        raise CopyCancelled("stop")

    monkeypatch.setattr(stager, "place_staged", place)
    worker = _stager(env)
    task = asyncio.ensure_future(worker.run())
    await asyncio.to_thread(started.wait, 5)
    await asyncio.wait_for(worker.stop(), 5)
    await asyncio.wait_for(task, 5)
    stage = await load_stage(env, stage_id)
    assert (stage.status, stage.attempts) == (StageStatus.PENDING, 0)


async def test_a_failed_pass_is_logged_and_the_worker_goes_idle(
    env: Env,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def broken(*_a: Any) -> str | None:
        raise RuntimeError("db down")

    monkeypatch.setattr(stager, "claim_next_stage", broken)
    with caplog.at_level(logging.ERROR, logger="arm_backend.stager"):
        assert await _stager(env)._work_once() is False
    assert "stager pass failed" in caplog.text


async def test_nothing_to_claim_is_an_idle_pass(env: Env) -> None:
    assert await _stager(env)._work_once() is False


async def test_the_idle_wait_ends_on_a_wake(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stager, "IDLE_POLL_SECONDS", 5.0)
    worker = _stager(env)
    worker.wake()
    await asyncio.wait_for(worker._idle(), 1)


async def test_the_idle_wait_times_out_without_a_wake(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stager, "IDLE_POLL_SECONDS", 0.01)
    await asyncio.wait_for(_stager(env)._idle(), 1)


async def test_the_active_stager_hook_wakes_it_and_tolerates_none(env: Env) -> None:
    worker = _stager(env)
    wake_active_stager()  # none published: a no-op
    set_active_stager(worker)
    try:
        wake_active_stager()
        assert worker._wake.is_set()
    finally:
        set_active_stager(None)


def test_a_stamp_helper_reads_unreadable_paths_as_none(tmp_path: Path) -> None:
    assert stager._current_stamp(tmp_path / "gone") is None
    assert stager._file_size(tmp_path / "gone") is None
    assert stager._file_size(tmp_path) is not None


# --- a job going away (delete or abandon) ---------------------------------------------------


def _copying_place(outcome: str, started: threading.Event) -> Any:
    """A `place_staged` that leaves a temp file, then waits for the cancel and ends as `outcome` says."""

    def place(plan: _Plan, cancel: threading.Event, progress: _StageProgress, on_checkpoint: Any) -> PlaceResult:
        plan.dest.parent.mkdir(parents=True, exist_ok=True)
        fileops.inprogress_path(plan.dest).write_bytes(b"partial")
        started.set()
        assert cancel.wait(5), "the cancel never reached the copy"
        if outcome == "cancelled":
            raise CopyCancelled("job gone")
        plan.dest.write_bytes(b"whole")
        return PlaceResult(size=5, linked=False)

    return place


@pytest.mark.parametrize("outcome", ["cancelled", "finished"])
async def test_cancelling_a_job_stops_its_copy_and_leaves_no_file_or_row(
    env: Env, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    stage_id = await seed_stage(env)
    started = threading.Event()
    monkeypatch.setattr(stager, "place_staged", _copying_place(outcome, started))
    worker = _stager(env)
    task = asyncio.ensure_future(worker._work_once())
    await asyncio.to_thread(started.wait, 5)
    dest = _dest(env)
    assert fileops.inprogress_path(dest).exists()

    await asyncio.wait_for(worker.cancel_job(JOB), 5)

    assert await asyncio.wait_for(task, 5) is True
    assert not fileops.inprogress_path(dest).exists()
    assert not dest.exists()
    async with env.factory() as db:
        assert await db.get(TrackStage, stage_id) is None
    assert "stage.failed" not in env.hub.types()


async def test_cancelling_a_job_does_not_touch_another_jobs_copy(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    stage_id = await seed_stage(env)
    started = threading.Event()
    monkeypatch.setattr(stager, "place_staged", _copying_place("cancelled", started))
    worker = _stager(env)
    task = asyncio.ensure_future(worker._work_once())
    await asyncio.to_thread(started.wait, 5)

    await worker.cancel_job("job_other")

    assert not worker._cancel.is_set()
    assert fileops.inprogress_path(_dest(env)).exists()
    await asyncio.wait_for(worker.stop(), 5)
    await asyncio.wait_for(task, 5)
    assert (await load_stage(env, stage_id)).status == StageStatus.PENDING


async def test_cancelling_a_job_with_no_copy_running_drops_its_claimable_rows(env: Env) -> None:
    stage_id = await seed_stage(env)
    worker = _stager(env)
    await worker.cancel_job(JOB)
    async with env.factory() as db:
        assert await db.get(TrackStage, stage_id) is None
        assert await claim_next_stage(db, env.hub) is None  # type: ignore[arg-type]


async def test_a_claim_whose_row_was_dropped_before_it_started_places_nothing(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    stage_id = await seed_stage(env)
    placed: list[str] = []
    monkeypatch.setattr(stager, "place_staged", lambda *a: placed.append("x"))
    worker = _stager(env)
    async with env.factory() as db:
        assert await claim_next_stage(db, env.hub) == stage_id  # type: ignore[arg-type]
    await worker.cancel_job(JOB)  # between the claim and the run's first read
    await stager._StageRun(stage_id, env.settings, env.hub, env.factory, threading.Event(), lambda: 0.0).run()  # type: ignore[arg-type]
    assert placed == []


async def test_a_copy_that_will_not_stop_is_logged_after_the_bounded_wait(
    env: Env, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    await seed_stage(env)
    started, release = threading.Event(), threading.Event()

    def place(plan: _Plan, cancel: threading.Event, progress: _StageProgress, on_checkpoint: Any) -> PlaceResult:
        started.set()
        assert release.wait(5)
        raise CopyCancelled("late")

    monkeypatch.setattr(stager, "place_staged", place)
    worker = _stager(env)
    task = asyncio.ensure_future(worker._work_once())
    await asyncio.to_thread(started.wait, 5)
    with caplog.at_level(logging.WARNING, logger="arm_backend.stager"):
        await worker.cancel_job(JOB, wait=0.05)
    assert "did not stop" in caplog.text
    release.set()
    assert await asyncio.wait_for(task, 5) is True


async def test_the_active_stager_hook_cancels_a_job_and_tolerates_none(env: Env) -> None:
    stage_id = await seed_stage(env)
    await cancel_job_staging(JOB)  # none published: a no-op
    assert (await load_stage(env, stage_id)).status == StageStatus.PENDING
    set_active_stager(_stager(env))
    try:
        await cancel_job_staging(JOB)
    finally:
        set_active_stager(None)
    async with env.factory() as db:
        assert await db.get(TrackStage, stage_id) is None
