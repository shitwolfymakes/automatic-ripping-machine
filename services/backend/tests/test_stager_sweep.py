"""The startup sweep: one test per row of the reconciliation table."""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

import pytest

from arm_backend import stager
from arm_backend.stager import DiskFacts, SweepAction, classify_stage, observe_stage, sweep_track_stages
from arm_common import StageStatus
from arm_common.fileops import SourceStamp, inprogress_path
from tests._stage_env import Env, add_job, add_stage, add_track, load_stage

BYTES = b"ripped bytes"


async def _seed(
    env: Env,
    *,
    status: StageStatus,
    stamped: bool = True,
    **fields: object,
) -> tuple[str, Path, Path]:
    """A stage row (stamped with the source's real stamp unless `stamped` is False); returns id, source, dest."""
    async with env.factory() as db:
        await add_job(db)
        track = await add_track(env, db)
        src = Path(str(track.output_path))
        if stamped:
            stamp = SourceStamp.of(src)
            fields.setdefault("source_size", stamp.size)
            fields.setdefault("source_mtime_ns", stamp.mtime_ns)
        stage = await add_stage(env, db, track, status=status, attempts=2, **fields)
        await db.commit()
        return stage.id, src, Path(stage.dest_path)


async def _sweep(env: Env) -> int:
    async with env.factory() as db:
        count = await sweep_track_stages(db, env.settings)
        await db.commit()
    return count


def _put_dest(src: Path, dest: Path, *, link: bool = False) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    os.link(src, dest) if link else shutil.copy2(src, dest)


@pytest.mark.parametrize("status", [StageStatus.COPYING, StageStatus.STALLED])
async def test_an_interrupted_stage_whose_source_is_gone_fails(env: Env, status: StageStatus) -> None:
    stage_id, src, _ = await _seed(env, status=status)
    src.unlink()
    assert await _sweep(env) == 1
    stage = await load_stage(env, stage_id)
    assert (stage.status, stage.last_error, stage.attempts) == (StageStatus.FAILED, "raw source missing", 2)


async def test_an_interrupted_stage_whose_source_changed_is_reset(env: Env) -> None:
    stage_id, src, dest = await _seed(env, status=StageStatus.COPYING, bytes_durable=5, linked=False)
    _put_dest(src, dest)
    inprogress_path(dest).write_bytes(b"tmp")
    src.write_bytes(b"re-ripped with other bytes")
    assert await _sweep(env) == 1
    stage = await load_stage(env, stage_id)
    assert stage.status == StageStatus.PENDING
    assert (stage.bytes_durable, stage.source_size, stage.source_mtime_ns, stage.linked) == (0, None, None, None)
    assert not dest.exists() and not inprogress_path(dest).exists()
    assert stage.attempts == 2


async def test_a_placement_whose_commit_was_lost_is_requeued_for_the_worker_to_adopt(env: Env) -> None:
    stage_id, src, dest = await _seed(env, status=StageStatus.COPYING, bytes_durable=5)
    _put_dest(src, dest, link=True)
    assert await _sweep(env) == 1
    stage = await load_stage(env, stage_id)
    assert (stage.status, stage.bytes_durable) == (StageStatus.PENDING, 0)
    assert dest.exists()  # kept: the worker hashes raw once and commits STAGED


async def test_a_partial_copy_is_requeued_keeping_its_checkpoint(env: Env) -> None:
    stage_id, _, dest = await _seed(env, status=StageStatus.STALLED, bytes_durable=4)
    dest.parent.mkdir(parents=True)
    inprogress_path(dest).write_bytes(b"ripp")
    assert await _sweep(env) == 1
    stage = await load_stage(env, stage_id)
    assert (stage.status, stage.bytes_durable) == (StageStatus.PENDING, 4)
    assert inprogress_path(dest).exists()  # the PENDING row owns it


async def test_an_interrupted_stage_with_nothing_on_disk_starts_over(env: Env) -> None:
    stage_id, _, _ = await _seed(env, status=StageStatus.COPYING, bytes_durable=4)
    assert await _sweep(env) == 1
    stage = await load_stage(env, stage_id)
    assert (stage.status, stage.bytes_durable) == (StageStatus.PENDING, 0)


async def test_an_unstamped_interrupted_stage_is_never_called_changed_or_placed(env: Env) -> None:
    stage_id, _, _ = await _seed(env, status=StageStatus.COPYING, stamped=False)
    assert await _sweep(env) == 1
    assert (await load_stage(env, stage_id)).status == StageStatus.PENDING


async def test_a_staged_row_whose_file_vanished_is_restaged(env: Env) -> None:
    stage_id, _, dest = await _seed(env, status=StageStatus.STAGED, bytes_durable=12, linked=True)
    dest.parent.mkdir(parents=True)
    inprogress_path(dest).write_bytes(b"leftover")
    assert await _sweep(env) == 1  # the row; its temp went with it, so no orphan is left
    stage = await load_stage(env, stage_id)
    assert (stage.status, stage.bytes_durable, stage.linked, stage.staged_at) == (StageStatus.PENDING, 0, None, None)
    assert not inprogress_path(dest).exists()


async def test_a_staged_row_with_the_wrong_size_is_restaged(env: Env) -> None:
    stage_id, _, dest = await _seed(env, status=StageStatus.STAGED)
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"short")
    assert await _sweep(env) == 1
    assert (await load_stage(env, stage_id)).status == StageStatus.PENDING


async def test_a_staged_row_with_an_intact_file_is_left_alone(env: Env) -> None:
    stage_id, src, dest = await _seed(env, status=StageStatus.STAGED)
    _put_dest(src, dest, link=True)
    assert await _sweep(env) == 0
    assert (await load_stage(env, stage_id)).status == StageStatus.STAGED


@pytest.mark.parametrize("status", [StageStatus.PENDING, StageStatus.FAILED])
async def test_pending_and_failed_rows_are_left_alone(env: Env, status: StageStatus) -> None:
    stage_id, _, _ = await _seed(env, status=status)
    assert await _sweep(env) == 0
    assert (await load_stage(env, stage_id)).status == status


async def test_orphan_temp_files_go_but_a_live_rows_temp_stays(env: Env, caplog: pytest.LogCaptureFixture) -> None:
    _, _, dest = await _seed(env, status=StageStatus.PENDING)
    dest.parent.mkdir(parents=True)
    inprogress_path(dest).write_bytes(b"mine")
    orphan = env.raw / ".staging" / "job_gone" / "x.mkv.arm-inprogress"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"orphan")
    with caplog.at_level(logging.INFO, logger="arm_backend.stager"):
        assert await _sweep(env) == 1
    assert not orphan.exists() and inprogress_path(dest).exists()
    assert "swept staging orphan" in caplog.text


async def test_an_orphan_that_cannot_be_deleted_is_logged_and_skipped(
    env: Env,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    orphan = env.raw / ".staging" / "job_gone" / "x.mkv.arm-inprogress"
    orphan.parent.mkdir(parents=True)
    orphan.write_bytes(b"orphan")

    def deny(self: Path, *a: object, **k: object) -> None:
        raise PermissionError("read-only")

    monkeypatch.setattr(Path, "unlink", deny)
    with caplog.at_level(logging.WARNING, logger="arm_backend.stager"):
        assert await _sweep(env) == 0
    assert "failed to delete staging orphan" in caplog.text


async def test_a_missing_staging_root_has_nothing_to_sweep(env: Env) -> None:
    assert await _sweep(env) == 0


# --- the classifiers, pure --------------------------------------------------------------------


def _facts(**kw: bool) -> DiskFacts:
    base = {"source_exists": True, "source_changed": False, "placed": False, "temp_exists": False, "dest_intact": True}
    return DiskFacts(**{**base, **kw})


@pytest.mark.parametrize(
    ("status", "facts", "expected"),
    [
        (StageStatus.COPYING, _facts(source_exists=False), SweepAction.FAIL_SOURCE_MISSING),
        (StageStatus.COPYING, _facts(source_changed=True, placed=True), SweepAction.RESET_CHANGED_SOURCE),
        (StageStatus.STALLED, _facts(placed=True, temp_exists=True), SweepAction.REQUEUE_PLACED),
        (StageStatus.COPYING, _facts(temp_exists=True), SweepAction.REQUEUE_RESUME),
        (StageStatus.COPYING, _facts(), SweepAction.REQUEUE_FRESH),
        (StageStatus.STAGED, _facts(dest_intact=False), SweepAction.RESTAGE),
        (StageStatus.STAGED, _facts(), SweepAction.KEEP),
        (StageStatus.PENDING, _facts(dest_intact=False), SweepAction.KEEP),
        (StageStatus.FAILED, _facts(source_exists=False), SweepAction.KEEP),
    ],
)
def test_classify_stage(status: StageStatus, facts: DiskFacts, expected: SweepAction) -> None:
    assert classify_stage(status, facts) == expected


async def test_observe_reads_the_disk(env: Env) -> None:
    stage_id, src, dest = await _seed(env, status=StageStatus.COPYING)
    _put_dest(src, dest)
    facts = observe_stage(await load_stage(env, stage_id))
    assert facts == DiskFacts(
        source_exists=True, source_changed=False, placed=True, temp_exists=False, dest_intact=True
    )


def test_every_action_but_keep_has_a_handler() -> None:
    assert set(stager._SWEEP_HANDLERS) == set(SweepAction) - {SweepAction.KEEP}
