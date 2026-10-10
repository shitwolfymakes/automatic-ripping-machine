"""Shared ffmpeg `-progress pipe:1` parsing, used by every ffmpeg-based engine.

ffmpeg streams `key=value` lines on stdout when launched with `-progress
pipe:1`. `out_time_us` (microseconds) + the source's `duration_seconds` →
percent. Moved out of `ffmpeg_audio.py` so the ffmpeg VAAPI video engine can
share it without importing the audio module.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

logger = logging.getLogger("arm_transcode.ffmpeg_progress")

ProgressCallback = Callable[[int, int | None, str | None], Awaitable[None]]


async def drain_stderr(stream: asyncio.StreamReader, buf: list[str]) -> None:
    while True:
        line = await stream.readline()
        if not line:
            break
        buf.append(line.decode(errors="replace").rstrip())


async def consume_progress(
    stream: asyncio.StreamReader,
    duration_seconds: int | None,
    cb: ProgressCallback,
) -> None:
    last_emitted = -1
    while True:
        line = await stream.readline()
        if not line:
            break
        decoded = line.decode(errors="replace").strip()
        if not decoded.startswith("out_time_us="):
            continue
        try:
            us = int(decoded.partition("=")[2])
        except ValueError:
            continue
        if duration_seconds is None or duration_seconds <= 0:
            continue
        pct = min(100, int(us / 1_000_000 / duration_seconds * 100))
        if pct == last_emitted:
            continue
        last_emitted = pct
        try:
            await cb(pct, None, "encoding")
        except Exception as exc:  # noqa: BLE001
            logger.debug("progress_callback raised: %s", exc)
