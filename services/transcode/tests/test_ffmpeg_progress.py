"""`consume_progress` carries ffmpeg's `fps=` line onto the percent tick (D-248)."""

from __future__ import annotations

import pytest

from arm_transcode.ffmpeg_progress import consume_progress


class _FakeStream:
    def __init__(self, lines: list[str]) -> None:
        self._lines = [(line + "\n").encode() for line in lines]

    async def readline(self) -> bytes:
        if not self._lines:
            return b""
        return self._lines.pop(0)


async def _collect(lines: list[str], duration_seconds: int = 100) -> list[tuple]:
    seen: list[tuple] = []

    async def cb(pct: int, eta: int | None, note: str | None, fps: float | None, avg_fps: float | None) -> None:
        seen.append((pct, eta, note, fps, avg_fps))

    await consume_progress(_FakeStream(lines), duration_seconds, cb)  # type: ignore[arg-type]
    return seen


@pytest.mark.asyncio
async def test_fps_line_rides_on_the_next_percent_tick() -> None:
    # ffmpeg prints `fps=` ahead of `out_time_us=` in each progress block.
    seen = await _collect(["frame=10", "fps=45.67", "out_time_us=25000000", "fps=50.0", "out_time_us=50000000"])
    assert seen == [(25, None, "encoding", 45.67, None), (50, None, "encoding", 50.0, None)]


@pytest.mark.asyncio
async def test_zero_or_garbled_fps_reads_as_unknown() -> None:
    # Audio-only encodes report fps=0.00; a bad value never breaks progress.
    seen = await _collect(["fps=0.00", "out_time_us=25000000", "fps=n/a", "out_time_us=50000000"])
    assert [s[3] for s in seen] == [None, None]
    assert [s[0] for s in seen] == [25, 50]


@pytest.mark.asyncio
async def test_tick_before_any_fps_line_has_no_rate() -> None:
    seen = await _collect(["out_time_us=25000000"])
    assert seen == [(25, None, "encoding", None, None)]
