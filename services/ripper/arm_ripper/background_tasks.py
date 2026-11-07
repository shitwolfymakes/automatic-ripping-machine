"""Fire-and-forget task helper shared by the job controller and the MakeMKV prep."""

import asyncio
from collections.abc import Coroutine
from typing import Any


def spawn_tracked(coro: Coroutine[Any, Any, None], tasks: set[asyncio.Task[None]]) -> None:
    """Run `coro` as a fire-and-forget task, held in `tasks` until it finishes so it is not garbage-collected
    mid-run."""
    task = asyncio.create_task(coro)
    tasks.add(task)
    task.add_done_callback(tasks.discard)
