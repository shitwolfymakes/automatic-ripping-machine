"""A background loop that runs one step every few seconds while a rip tool runs."""

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger("arm_ripper.rip.poller")

PollStep = Callable[[], Awaitable[None]]


class Poller:
    """Runs `step` every `interval` seconds until stopped; a failing step is logged at debug and polling goes on."""

    def __init__(self, interval: float, step: PollStep) -> None:
        self._interval = interval
        self._step = step
        self._stopping = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Begin polling in a background task; the first step runs one interval from now."""
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        """Stop polling and wait for the loop to end. A step already running finishes first, so the side effects
        it started (a callback to the backend) are not cut off halfway."""
        self._stopping.set()
        if self._task is not None:
            await self._task

    async def _run(self) -> None:
        while not await self._stopped_within(self._interval):
            await self._run_step()

    async def _stopped_within(self, seconds: float) -> bool:
        """Wait up to `seconds` for a stop; True once stopping."""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._stopping.wait(), seconds)
        return self._stopping.is_set()

    async def _run_step(self) -> None:
        try:
            await self._step()
        except Exception:  # noqa: BLE001 - a poll step is best-effort and never ends the loop
            logger.debug("poll step failed", exc_info=True)
