"""Report what an ISO ripper is doing before identify creates its job.

Scanning an image, unpacking one MakeMKV cannot open (`iso_extract`) and
scanning the unpacked folder can take half an hour for a Blu-ray on a
network share, and until identify there is no job to show it on. The ripper
posts its phase here instead (`POST /api/ripper/iso-prepare`), so the
dashboard lists the rip as "preparing".

Only source mode configures it (`configure`); for a physical drive every
call is a no-op. A phase change is always sent, progress within a phase at
most every `min_interval` seconds, and the current phase is re-sent every
`keepalive` seconds so the backend's in-memory status doesn't age out during
a long silent step (a MakeMKV scan). Failures are logged and swallowed: the
report is cosmetic and must never break the pipeline.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from typing import Protocol

from arm_common import IsoPreparePhase

logger = logging.getLogger("arm_ripper.prepare")


class _Client(Protocol):
    async def report_iso_prepare(
        self, *, drive_id: str, phase: IsoPreparePhase, progress_pct: int | None, current_file: str | None
    ) -> None: ...


class _Reporter:
    def __init__(
        self, client: _Client, drive_id: str, *, min_interval: float, keepalive: float, clock: Callable[[], float]
    ) -> None:
        self._client = client
        self._drive_id = drive_id
        self._min_interval = min_interval
        self._keepalive = keepalive
        self._clock = clock
        self._last: tuple[IsoPreparePhase, int | None, str | None] | None = None
        self._last_sent_at = 0.0
        self._keepalive_task: asyncio.Task[None] | None = None

    async def report(self, phase: IsoPreparePhase, progress_pct: int | None, current_file: str | None) -> None:
        now = self._clock()
        phase_changed = self._last is None or self._last[0] != phase
        self._last = (phase, progress_pct, current_file)
        if not phase_changed and now - self._last_sent_at < self._min_interval:
            return
        self._last_sent_at = now
        await self._send()
        if self._keepalive_task is None:
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())

    async def _send(self) -> None:
        assert self._last is not None
        phase, pct, current = self._last
        try:
            await self._client.report_iso_prepare(
                drive_id=self._drive_id, phase=phase, progress_pct=pct, current_file=current
            )
        except Exception as exc:  # noqa: BLE001 - cosmetic; never break the pipeline
            logger.warning("iso-prepare report failed (%s): %s", phase.value, exc)

    async def _keepalive_loop(self) -> None:
        while True:
            await asyncio.sleep(self._keepalive)
            await self._send()

    async def finish(self) -> None:
        task, self._keepalive_task = self._keepalive_task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._last = None


_reporter: _Reporter | None = None


def configure(
    client: _Client,
    drive_id: str,
    *,
    min_interval: float = 3.0,
    keepalive: float = 15.0,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    global _reporter
    _reporter = _Reporter(client, drive_id, min_interval=min_interval, keepalive=keepalive, clock=clock)


def reset() -> None:
    """Forget the configured reporter (tests). Call `finish` first if one ran."""
    global _reporter
    _reporter = None


async def report(phase: IsoPreparePhase, progress_pct: int | None = None, current_file: str | None = None) -> None:
    if _reporter is not None:
        await _reporter.report(phase, progress_pct, current_file)


async def finish() -> None:
    """The preparing steps are over (identify comes next, or the pipeline
    ended): stop the keepalive. The backend drops the status at identify."""
    if _reporter is not None:
        await _reporter.finish()
