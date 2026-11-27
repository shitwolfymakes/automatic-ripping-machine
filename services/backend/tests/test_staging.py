"""Stage rows: destination paths, `ensure_stage_rows`, and the event payload."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from sqlmodel import select

from arm_backend.staging import (
    dest_path_for,
    ensure_stage_rows,
    release_if_settled,
    stage_for_track,
    stage_payload,
    unlink_staged_copy,
)
from arm_common import StageStatus, TrackKind, TrackStage, TranscodeTask, TranscodeTaskStatus
from tests._stage_env import JOB, Env, add_job, add_stage, add_track


async def test_dest_path_mirrors_the_path_under_the_raw_job_dir(env: Env) -> None:
    async with env.factory() as db:
        await add_job(db)
        track = await add_track(env, db)
        track.output_path = str(env.raw / JOB / "sub" / "t.mkv")
    assert dest_path_for(env.settings, track) == env.raw / ".staging" / JOB / "sub" / "t.mkv"


async def test_dest_path_needs_an_output_path(env: Env) -> None:
    async with env.factory() as db:
        await add_job(db)
        track = await add_track(env, db, content=None)
    with pytest.raises(ValueError, match="no output_path"):
        dest_path_for(env.settings, track)


async def test_dest_path_refuses_a_path_outside_the_raw_job_dir(env: Env) -> None:
    async with env.factory() as db:
        await add_job(db)
        track = await add_track(env, db)
        track.output_path = "/elsewhere/t.mkv"
    with pytest.raises(ValueError):
        dest_path_for(env.settings, track)


async def test_ensure_inserts_a_pending_row_once_and_announces_it(env: Env) -> None:
    async with env.factory() as db:
        await add_job(db)
        track = await add_track(env, db)
        created = await ensure_stage_rows(db, env.settings, [track], env.hub)
        again = await ensure_stage_rows(db, env.settings, [track], env.hub)
        await db.commit()
    assert [c.track_id for c in created] == [track.id]
    assert again == []
    row = created[0]
    assert row.status == StageStatus.PENDING
    assert row.source_path == track.output_path
    assert row.dest_path == str(env.raw / ".staging" / JOB / "trk_a.mkv")
    assert env.hub.types() == ["stage.queued"]
    call = env.hub.calls[0]
    assert call["topic"] == "staging.events"
    assert call["payload"]["stage_id"] == row.id
    assert call["job_id"] == JOB and call["track_id"] == track.id


async def test_ensure_leaves_an_existing_row_of_any_status_alone(env: Env) -> None:
    async with env.factory() as db:
        await add_job(db)
        track = await add_track(env, db)
        await add_stage(env, db, track, status=StageStatus.FAILED, last_error="boom")
        created = await ensure_stage_rows(db, env.settings, [track], env.hub)
        rows = (await db.execute(select(TrackStage))).scalars().all()
    assert created == []
    assert [(r.status, r.last_error) for r in rows] == [(StageStatus.FAILED, "boom")]
    assert env.hub.calls == []


async def test_ensure_skips_tracks_without_a_file(env: Env) -> None:
    async with env.factory() as db:
        await add_job(db)
        track = await add_track(env, db, content=None)
        assert await ensure_stage_rows(db, env.settings, [track], env.hub) == []


async def test_ensure_skips_a_disc_backup_folder(env: Env) -> None:
    async with env.factory() as db:
        await add_job(db)
        track = await add_track(env, db, kind=TrackKind.DISC_BACKUP)
        assert await ensure_stage_rows(db, env.settings, [track], env.hub) == []


async def test_ensure_skips_and_logs_a_path_outside_raw(env: Env, caplog: pytest.LogCaptureFixture) -> None:
    async with env.factory() as db:
        await add_job(db)
        track = await add_track(env, db)
        track.output_path = "/elsewhere/t.mkv"
        with caplog.at_level(logging.WARNING, logger="arm_backend.staging"):
            assert await ensure_stage_rows(db, env.settings, [track], env.hub) == []
    assert "outside its raw dir" in caplog.text


async def test_ensure_without_a_hub_inserts_silently(env: Env) -> None:
    async with env.factory() as db:
        await add_job(db)
        track = await add_track(env, db)
        created = await ensure_stage_rows(db, env.settings, [track])
    assert len(created) == 1
    assert env.hub.calls == []


async def test_stage_for_track_finds_the_row_or_none(env: Env) -> None:
    async with env.factory() as db:
        await add_job(db)
        track = await add_track(env, db)
        stage = await add_stage(env, db, track)
        found = await stage_for_track(db, track.id)
        missing = await stage_for_track(db, "trk_none")
    assert found is stage
    assert missing is None


async def test_payload_shape_and_a_raw_status_string(env: Env) -> None:
    async with env.factory() as db:
        await add_job(db)
        track = await add_track(env, db)
        stage = await add_stage(env, db, track, bytes_durable=7, attempts=2, last_error="e", linked=True)
    assert stage_payload(stage) == {
        "track_id": track.id,
        "job_id": JOB,
        "stage_id": stage.id,
        "status": "pending",
        "attempts": 2,
        "last_error": "e",
        "bytes_durable": 7,
        "linked": True,
    }
    stage.status = "from_a_newer_build"  # type: ignore[assignment]
    assert stage_payload(stage)["status"] == "from_a_newer_build"


async def _seed_staged_with_tasks(env: Env, statuses: list[TranscodeTaskStatus]) -> Path:
    """A STAGED row with a real staged file and one task per status; returns the staged file."""
    async with env.factory() as db:
        await add_job(db)
        track = await add_track(env, db)
        stage = await add_stage(env, db, track, status=StageStatus.STAGED)
        staged = Path(stage.dest_path)
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(b"staged")
        for n, status in enumerate(statuses):
            db.add(
                TranscodeTask(
                    id=f"txt_{n}",
                    session_application_id="sap_x",
                    source_track_id=track.id,
                    status=status,
                    output_path=f"out_{n}.mkv",
                )
            )
        await db.commit()
    return staged


async def _release(env: Env) -> Path | None:
    async with env.factory() as db:
        released = await release_if_settled(db, "trk_a")
        await db.commit()
    return released


async def _stage_rows(env: Env) -> list[TrackStage]:
    async with env.factory() as db:
        return list((await db.execute(select(TrackStage))).scalars().all())


async def test_release_drops_the_row_and_returns_the_copy_to_unlink_once_every_task_is_done(env: Env) -> None:
    staged = await _seed_staged_with_tasks(env, [TranscodeTaskStatus.DONE, TranscodeTaskStatus.DONE])
    assert await _release(env) == staged
    assert staged.exists()  # unlinking is the caller's job, after its commit
    assert await _stage_rows(env) == []


@pytest.mark.parametrize(
    "other", [TranscodeTaskStatus.QUEUED, TranscodeTaskStatus.IN_PROGRESS, TranscodeTaskStatus.FAILED]
)
async def test_release_keeps_the_row_while_any_task_is_not_done(env: Env, other: TranscodeTaskStatus) -> None:
    staged = await _seed_staged_with_tasks(env, [TranscodeTaskStatus.DONE, other])
    assert await _release(env) is None
    assert staged.exists()
    assert len(await _stage_rows(env)) == 1


async def test_release_keeps_the_row_of_a_track_with_no_tasks(env: Env) -> None:
    await _seed_staged_with_tasks(env, [])
    assert await _release(env) is None
    assert len(await _stage_rows(env)) == 1


async def test_release_without_a_stage_row_does_nothing(env: Env) -> None:
    async with env.factory() as db:
        assert await release_if_settled(db, "trk_none") is None


async def test_a_rolled_back_release_keeps_the_row(env: Env) -> None:
    await _seed_staged_with_tasks(env, [TranscodeTaskStatus.DONE])
    async with env.factory() as db:
        assert await release_if_settled(db, "trk_a") is not None
        await db.rollback()
    assert len(await _stage_rows(env)) == 1


def test_unlink_removes_the_file(tmp_path: Path) -> None:
    staged = tmp_path / "t.mkv"
    staged.write_bytes(b"x")
    unlink_staged_copy(staged)
    assert not staged.exists()


def test_unlink_of_nothing_or_a_missing_file_is_a_no_op(tmp_path: Path) -> None:
    unlink_staged_copy(None)
    unlink_staged_copy(tmp_path / "gone.mkv")


def test_unlink_logs_a_file_that_will_not_go(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def _boom(self: Path, missing_ok: bool = False) -> None:
        raise PermissionError("read-only")

    monkeypatch.setattr(Path, "unlink", _boom)
    with caplog.at_level(logging.WARNING, logger="arm_backend.staging"):
        unlink_staged_copy(tmp_path / "t.mkv")
    assert "staged copy not removed" in caplog.text
