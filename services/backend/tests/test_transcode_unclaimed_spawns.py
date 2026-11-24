"""Spawned transcoders that have not claimed their task yet (#251, #642).

A task stays QUEUED from its spawn until its container calls /claim. The
dispatcher remembers those spawns: a later pass neither spawns the task again
nor gives its encode slot away, and a spawn still unclaimed after the stale
threshold is stopped, its GPU released and the attempt counted, so one
container that cannot call home no longer holds the only GPU forever.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from arm_backend.transcode_dispatcher import TranscodeDispatcher
from arm_backend.ws import WSHub
from arm_common import GpuStatus, GpuVendor, TranscodeTask, TranscodeTaskStatus
from tests._fakes import FakeSession
from tests.test_transcode_dispatcher import _app_with_one_task, _db_factory, _settings
from tests.test_transcode_dispatcher_gpu import _build_db

_STALE = 90  # ARM_TRANSCODE_STALE_THRESHOLD_SECONDS in `_settings`


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _dispatcher(db: Any, docker: MagicMock, **settings: Any) -> tuple[TranscodeDispatcher, _Clock]:
    disp = TranscodeDispatcher(_settings(**settings), _db_factory(db), docker, WSHub())
    clock = _Clock()
    disp._clock = clock
    return disp, clock


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
    disp, _ = _dispatcher(db, docker)

    assert await disp.spawn_pending(db) == 1
    assert await disp.spawn_pending(db) == 0

    assert _spawned_ids(docker) == ["txt_1"]


async def test_unclaimed_spawn_takes_an_encode_slot() -> None:
    db = _cpu_db("txt_2")
    docker = MagicMock()
    disp, _ = _dispatcher(db, docker, MAX_PARALLEL_TRANSCODES=1)

    await disp.spawn_pending(db)
    await disp.spawn_pending(db)

    # txt_1 is still starting: the one slot is taken, txt_2 waits.
    assert _spawned_ids(docker) == ["txt_1"]


async def test_claimed_task_leaves_the_watch_and_frees_no_extra_slot() -> None:
    db = _cpu_db("txt_2")
    docker = MagicMock()
    disp, _ = _dispatcher(db, docker, MAX_PARALLEL_TRANSCODES=2)

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


# --- #251: a spawn that never claims is recovered --------------------------------


async def test_spawn_unclaimed_past_the_threshold_is_stopped_released_and_respawned() -> None:
    db = _nvenc_db()
    docker = MagicMock()
    survivor = MagicMock()
    docker.containers.list.return_value = [survivor]
    disp, clock = _dispatcher(db, docker)

    await disp.spawn_pending(db)
    gpu = db.rows["gpus"][0]
    assert (gpu.status, gpu.claimed_by_task_id) == (GpuStatus.BUSY, "txt_1")

    clock.now += _STALE + 1
    assert await disp.sweep_unclaimed_spawns(db) == 1

    assert (gpu.status, gpu.claimed_by_task_id) == (GpuStatus.AVAILABLE, None)
    docker.containers.list.assert_called_once_with(filters={"label": "arm.task_id=txt_1"})
    survivor.stop.assert_called_once()
    task = db.rows["transcode_tasks"][0]
    assert (task.status, task.attempts) == (TranscodeTaskStatus.QUEUED, 1)
    assert disp.last_spawn_error is not None and "never claimed" in disp.last_spawn_error

    # The freed GPU goes to a fresh spawn of the same task.
    await disp.spawn_pending(db)
    assert _spawned_ids(docker) == ["txt_1", "txt_1"]
    assert gpu.claimed_by_task_id == "txt_1"


async def test_spawn_within_the_threshold_is_left_alone() -> None:
    db = _nvenc_db()
    docker = MagicMock()
    disp, clock = _dispatcher(db, docker)

    await disp.spawn_pending(db)
    clock.now += _STALE - 1

    assert await disp.sweep_unclaimed_spawns(db) == 0
    assert db.rows["gpus"][0].status == GpuStatus.BUSY
    docker.containers.list.assert_not_called()


async def test_claimed_spawn_is_never_swept() -> None:
    db = _nvenc_db()
    docker = MagicMock()
    disp, clock = _dispatcher(db, docker)

    await disp.spawn_pending(db)
    db.rows["transcode_tasks"][0].status = TranscodeTaskStatus.IN_PROGRESS
    clock.now += _STALE + 1

    assert await disp.sweep_unclaimed_spawns(db) == 0
    assert db.rows["gpus"][0].status == GpuStatus.BUSY
    docker.containers.list.assert_not_called()


async def test_unclaimed_spawn_on_its_last_attempt_fails_the_task() -> None:
    db = _nvenc_db()
    db.rows["transcode_tasks"][0].attempts = 2  # ARM_TRANSCODE_MAX_ATTEMPTS = 3
    docker = MagicMock()
    docker.containers.list.return_value = []
    disp, clock = _dispatcher(db, docker)

    await disp.spawn_pending(db)
    clock.now += _STALE + 1
    await disp.sweep_unclaimed_spawns(db)

    task = db.rows["transcode_tasks"][0]
    assert task.status == TranscodeTaskStatus.FAILED
    assert task.last_error is not None and "never claimed" in task.last_error
    assert db.rows["gpus"][0].status == GpuStatus.AVAILABLE


async def test_a_failed_container_stop_still_releases_the_gpu() -> None:
    db = _nvenc_db()
    docker = MagicMock()
    docker.containers.list.side_effect = RuntimeError("docker host unreachable")
    disp, clock = _dispatcher(db, docker)

    await disp.spawn_pending(db)
    clock.now += _STALE + 1
    await disp.sweep_unclaimed_spawns(db)

    assert db.rows["gpus"][0].status == GpuStatus.AVAILABLE


# --- backend restart -----------------------------------------------------------


async def test_queued_gpu_claim_left_by_a_restart_is_recovered() -> None:
    """The dispatcher's memory starts empty after a restart; a queued task
    still holding a GPU is picked up at startup and swept after the threshold
    like any other unclaimed spawn, instead of holding the GPU for good."""
    db = _build_db(encoder="any_h265", gpus=[(GpuVendor.NVENC, GpuStatus.BUSY, ["h265"], "txt_1")])
    docker = MagicMock()
    docker.containers.list.return_value = []
    disp, clock = _dispatcher(db, docker)

    await disp.watch_restart_claims(db)
    assert await disp.spawn_pending(db) == 0  # still awaiting its claim: not spawned twice
    assert await disp.sweep_unclaimed_spawns(db) == 0
    clock.now += _STALE + 1
    assert await disp.sweep_unclaimed_spawns(db) == 1

    assert db.rows["gpus"][0].status == GpuStatus.AVAILABLE
    assert db.rows["transcode_tasks"][0].attempts == 1


async def test_restart_ignores_a_gpu_claimed_by_a_task_already_running() -> None:
    """An in-progress claimant has a live heartbeat; the stale-claim sweep owns it."""
    db = _build_db(encoder="any_h265", gpus=[(GpuVendor.NVENC, GpuStatus.BUSY, ["h265"], "txt_1")])
    db.rows["transcode_tasks"][0].status = TranscodeTaskStatus.IN_PROGRESS
    disp, clock = _dispatcher(db, MagicMock())

    await disp.watch_restart_claims(db)
    clock.now += _STALE + 1

    assert await disp.sweep_unclaimed_spawns(db) == 0
    assert db.rows["gpus"][0].status == GpuStatus.BUSY


async def test_run_picks_up_restart_claims_before_its_first_tick() -> None:
    db = _build_db(encoder="any_h265", gpus=[(GpuVendor.NVENC, GpuStatus.BUSY, ["h265"], "txt_1")])
    disp, _ = _dispatcher(db, MagicMock())
    ticks: list[set[str]] = []

    async def _first_tick() -> None:
        ticks.append(set(disp._awaiting_claim))
        disp.stop()

    disp._tick = _first_tick  # type: ignore[method-assign]
    await asyncio.wait_for(disp.run(), timeout=2.0)

    assert ticks == [{"txt_1"}]


async def test_run_starts_even_when_the_restart_check_fails(monkeypatch: Any) -> None:
    disp, _ = _dispatcher(FakeSession(), MagicMock())
    ticked: list[bool] = []

    async def _boom(_db: Any) -> None:
        raise RuntimeError("db down")

    async def _tick() -> None:
        ticked.append(True)
        disp.stop()

    monkeypatch.setattr(disp, "watch_restart_claims", _boom)
    disp._tick = _tick  # type: ignore[method-assign]
    await asyncio.wait_for(disp.run(), timeout=2.0)

    assert ticked == [True]


async def test_a_failing_recovery_is_logged_and_does_not_abort_the_tick(monkeypatch: Any) -> None:
    import arm_backend.transcode_dispatcher as dispatcher_mod

    db = _nvenc_db()
    docker = MagicMock()
    docker.containers.list.return_value = []
    disp, clock = _dispatcher(db, docker)
    await disp.spawn_pending(db)
    clock.now += _STALE + 1

    async def _boom(_db: Any, _task_id: str) -> None:
        raise RuntimeError("release failed")

    monkeypatch.setattr(dispatcher_mod, "release_gpu_for_task", _boom)

    assert await disp.sweep_unclaimed_spawns(db) == 1
    # Forgotten, not retried every tick: the next spawn pass handles the task.
    assert disp._awaiting_claim == {}


async def test_recovery_skips_a_task_claimed_since_the_check() -> None:
    db = _nvenc_db()
    docker = MagicMock()
    disp, _ = _dispatcher(db, docker)
    await disp.spawn_pending(db)
    db.rows["transcode_tasks"][0].status = TranscodeTaskStatus.IN_PROGRESS

    await disp._recover_unclaimed_spawn(db, "txt_1", _STALE)

    assert db.rows["gpus"][0].status == GpuStatus.BUSY
    assert db.rows["transcode_tasks"][0].attempts == 0
    docker.containers.list.assert_not_called()


@pytest.mark.parametrize("attempts_before", [0, 2])  # a middle attempt, and the last one
async def test_a_claim_landing_while_the_container_stops_is_kept(attempts_before: int) -> None:
    """The stop can take seconds; a /claim that commits meanwhile owns the task.
    Recovery neither requeues nor fails it, keeps the claim's attempt count and
    leaves its GPU claimed."""
    db = _nvenc_db()
    task = db.rows["transcode_tasks"][0]
    task.attempts = attempts_before
    docker = MagicMock()

    def _claim_commits_during_the_stop(**_: Any) -> list[MagicMock]:
        task.status = TranscodeTaskStatus.IN_PROGRESS
        task.claimed_by = "arm-transcode-x"
        task.attempts = attempts_before + 1
        return [MagicMock()]

    docker.containers.list.side_effect = _claim_commits_during_the_stop
    disp, clock = _dispatcher(db, docker)
    await disp.spawn_pending(db)
    clock.now += _STALE + 1
    locks_before = db.locked.count("transcode_tasks")

    await disp.sweep_unclaimed_spawns(db)

    # Re-read under its row lock, then the lock is dropped right away.
    assert db.locked.count("transcode_tasks") == locks_before + 1
    assert db.call_log[-1] == "rollback"
    assert (task.status, task.attempts, task.last_error) == (
        TranscodeTaskStatus.IN_PROGRESS,
        attempts_before + 1,
        None,
    )
    gpu = db.rows["gpus"][0]
    assert (gpu.status, gpu.claimed_by_task_id) == (GpuStatus.BUSY, "txt_1")


async def test_each_tick_recovers_unclaimed_spawns() -> None:
    db = _nvenc_db()
    docker = MagicMock()
    docker.containers.list.return_value = []
    disp, clock = _dispatcher(db, docker)
    await disp.spawn_pending(db)
    clock.now += _STALE + 1

    await disp._tick()

    docker.containers.list.assert_any_call(filters={"label": "arm.task_id=txt_1"})
    assert db.rows["transcode_tasks"][0].attempts == 1


def test_stopping_containers_without_a_docker_client_is_a_no_op() -> None:
    disp = TranscodeDispatcher(_settings(), _db_factory(FakeSession()), None, WSHub())

    disp._stop_task_containers("txt_1")
