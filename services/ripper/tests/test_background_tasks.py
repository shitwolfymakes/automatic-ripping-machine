"""Unit tests for the fire-and-forget task helper."""

import asyncio

from arm_ripper.background_tasks import spawn_tracked


async def test_task_is_tracked_while_running_and_coroutine_runs():
    """Pin that the task sits in the set while it runs and the coroutine actually executes."""
    release = asyncio.Event()
    ran: list[str] = []

    async def _work() -> None:
        ran.append("started")
        await release.wait()
        ran.append("finished")

    tasks: set[asyncio.Task[None]] = set()
    spawn_tracked(_work(), tasks)
    await asyncio.sleep(0)
    assert len(tasks) == 1
    assert ran == ["started"]
    release.set()
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    assert ran == ["started", "finished"]


async def test_set_drops_the_task_after_a_normal_finish():
    """Pin that a finished task is discarded from the set."""

    async def _work() -> None:
        return None

    tasks: set[asyncio.Task[None]] = set()
    spawn_tracked(_work(), tasks)
    (task,) = tasks
    await task
    await asyncio.sleep(0)
    assert not tasks


async def test_set_drops_the_task_after_the_coroutine_raises():
    """Pin that a task whose coroutine raised is still discarded from the set."""

    async def _boom() -> None:
        raise RuntimeError("boom")

    tasks: set[asyncio.Task[None]] = set()
    spawn_tracked(_boom(), tasks)
    (task,) = tasks
    await asyncio.wait([task])
    await asyncio.sleep(0)
    assert not tasks
    assert isinstance(task.exception(), RuntimeError)
