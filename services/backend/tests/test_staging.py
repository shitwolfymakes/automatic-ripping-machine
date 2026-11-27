"""Stage rows: destination paths, `ensure_stage_rows`, and the event payload."""

from __future__ import annotations

import logging

import pytest
from sqlmodel import select

from arm_backend.staging import dest_path_for, ensure_stage_rows, stage_for_track, stage_payload
from arm_common import StageStatus, TrackKind, TrackStage
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
