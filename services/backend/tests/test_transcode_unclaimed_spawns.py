"""Spawned transcoders that have not claimed their task yet (#251, #642).

A task stays QUEUED from its spawn until its container calls /claim. The
dispatcher remembers those spawns (`_awaiting_checkin`): a later pass neither
spawns the task again nor gives its encode slot away. A spawn still unchecked
after ARM_TRANSCODE_CHECKIN_TIMEOUT_SECONDS is removed, its GPU released and the
attempt counted (test_transcode_spawn_retry); a claim that lands while it is
removed keeps the task and its GPU.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from arm_backend import transcode_dispatcher as tdmod
from arm_backend.transcode_dispatcher import TranscodeDispatcher
from arm_backend.ws import WSHub
from arm_common import GpuStatus, GpuVendor, TranscodeTask, TranscodeTaskStatus
from tests._staged_sources import staged_by_default
from tests.test_transcode_dispatcher import _app_with_one_task, _db_factory, _settings
from tests.test_transcode_dispatcher_gpu import _build_db


@pytest.fixture(autouse=True)
def _staged_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    staged_by_default(monkeypatch)


def _dispatcher(db: Any, docker: MagicMock, **settings: Any) -> TranscodeDispatcher:
    return TranscodeDispatcher(_settings(**settings), _db_factory(db), docker, WSHub())


def _cpu_db(*task_ids: str) -> Any:
    db = _app_with_one_task(TranscodeTaskStatus.QUEUED)
    db.rows["transcode_tasks"][0].created_at = datetime.now(UTC)
    for n, task_id in enumerate(task_ids):
        db.rows["transcode_tasks"].append(
            TranscodeTask(
                id=task_id,
                session_application_id="sap_x",
                source_track_id=f"trk_{n + 2}",
                status=TranscodeTaskStatus.QUEUED,
                attempts=0,
                progress_pct=0,
                output_path=f"Iron Man (2008)/extra {n}.mkv",
                created_at=datetime.now(UTC),
            )
        )
    return db


def _nvenc_db() -> Any:
    return _build_db(encoder="any_h265", gpus=[(GpuVendor.NVENC, GpuStatus.AVAILABLE, ["h265"], None)])


def _spawned_ids(docker: MagicMock) -> list[str]:
    return [c.kwargs["labels"]["arm.task_id"] for c in docker.containers.run.call_args_list]


# --- #642: a spawned, unclaimed task is not spawned again ----------------------------


async def test_unclaimed_cpu_task_is_not_spawned_again_on_the_next_pass() -> None:
    db = _cpu_db()
    docker = MagicMock()
    disp = _dispatcher(db, docker)

    assert await disp.spawn_pending(db) == 1
    assert await disp.spawn_pending(db) == 0

    assert _spawned_ids(docker) == ["txt_1"]


async def test_unclaimed_spawn_takes_an_encode_slot() -> None:
    db = _cpu_db("txt_2")
    docker = MagicMock()
    disp = _dispatcher(db, docker, MAX_PARALLEL_TRANSCODES=1)

    await disp.spawn_pending(db)
    await disp.spawn_pending(db)

    # txt_1 is still starting: the one slot is taken, txt_2 waits.
    assert _spawned_ids(docker) == ["txt_1"]


async def test_claimed_task_leaves_the_watch_and_frees_no_extra_slot() -> None:
    db = _cpu_db("txt_2")
    docker = MagicMock()
    disp = _dispatcher(db, docker, MAX_PARALLEL_TRANSCODES=2)

    await disp.spawn_pending(db)  # txt_1 and txt_2 both spawn
    assert _spawned_ids(docker) == ["txt_1", "txt_2"]
    db.rows["transcode_tasks"][0].status = TranscodeTaskStatus.IN_PROGRESS  # txt_1 claims
    db.rows["transcode_tasks"].append(
        TranscodeTask(
            id="txt_3",
            session_application_id="sap_x",
            source_track_id="trk_9",
            status=TranscodeTaskStatus.QUEUED,
            attempts=0,
            progress_pct=0,
            output_path="Iron Man (2008)/extra 9.mkv",
            created_at=datetime.now(UTC),
        )
    )

    await disp.spawn_pending(db)

    # txt_1 counts once (in progress), txt_2 still holds its slot: no room for txt_3.
    assert _spawned_ids(docker) == ["txt_1", "txt_2"]
    db.rows["transcode_tasks"][1].status = TranscodeTaskStatus.IN_PROGRESS  # txt_2 claims
    db.rows["transcode_tasks"][0].status = TranscodeTaskStatus.DONE  # txt_1 finishes
    await disp.spawn_pending(db)
    assert _spawned_ids(docker) == ["txt_1", "txt_2", "txt_3"]


# --- a claim that lands while the unchecked container is removed --------------------


@pytest.mark.parametrize("attempts_before", [0, 2])  # a middle attempt, and the last one
async def test_a_claim_landing_while_the_container_is_removed_is_kept(
    monkeypatch: pytest.MonkeyPatch, attempts_before: int
) -> None:
    """The removal can take seconds; a /claim that commits meanwhile owns the task.
    The check-in timeout neither counts an attempt nor fails it, and leaves its GPU claimed."""
    db = _nvenc_db()
    task = db.rows["transcode_tasks"][0]
    task.attempts = attempts_before
    docker = MagicMock()
    disp = _dispatcher(db, docker, ARM_TRANSCODE_CHECKIN_TIMEOUT_SECONDS=60, ARM_TRANSCODE_MAX_ATTEMPTS=3)
    await disp.spawn_pending(db)

    def _claim_commits_during_the_removal(_name: str, _task_id: str) -> str:
        task.status = TranscodeTaskStatus.IN_PROGRESS
        task.claimed_by = "arm-transcode-x"
        task.attempts = attempts_before + 1
        return ""

    monkeypatch.setattr(disp, "_discard_container", _claim_commits_during_the_removal)
    now = tdmod.time.monotonic()
    monkeypatch.setattr(tdmod.time, "monotonic", lambda: now + 61)

    await disp.spawn_pending(db)

    assert (task.status, task.attempts, task.last_error) == (
        TranscodeTaskStatus.IN_PROGRESS,
        attempts_before + 1,
        None,
    )
    gpu = db.rows["gpus"][0]
    assert (gpu.status, gpu.claimed_by_task_id) == (GpuStatus.BUSY, "txt_1")
    assert disp._awaiting_checkin == {}
