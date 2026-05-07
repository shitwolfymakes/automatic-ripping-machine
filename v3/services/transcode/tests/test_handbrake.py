"""HandBrakeCLI text-mode progress parser."""

from __future__ import annotations

import asyncio
import re
from typing import Awaitable

import pytest

from arm_transcode.handbrake import _PROGRESS_LINE_RE, _consume_progress, _parse_eta


def _match(line: str) -> re.Match[str] | None:
    return _PROGRESS_LINE_RE.search(line)


def test_full_line_with_eta() -> None:
    m = _match("Encoding: task 1 of 1, 47.30 % (45.67 fps, avg 23.45 fps, ETA 00h12m34s)")
    assert m is not None
    assert int(round(float(m.group("pct")))) == 47
    assert _parse_eta(m) == 12 * 60 + 34
    assert m.group("pass") == "1"
    assert m.group("pass_total") == "1"


def test_zero_progress_no_eta_yet() -> None:
    m = _match("Encoding: task 1 of 1, 0.00 %")
    assert m is not None
    assert int(round(float(m.group("pct")))) == 0
    assert _parse_eta(m) is None


def test_one_hundred_percent() -> None:
    m = _match("Encoding: task 1 of 1, 100.00 % (45.67 fps, avg 23.45 fps, ETA 00h00m00s)")
    assert m is not None
    assert int(round(float(m.group("pct")))) == 100
    assert _parse_eta(m) == 0


def test_eta_with_hours() -> None:
    m = _match("Encoding: task 2 of 3, 5.20 % (12.00 fps, avg 12.00 fps, ETA 01h45m30s)")
    assert m is not None
    assert _parse_eta(m) == 3600 + 45 * 60 + 30


def test_does_not_match_title_scan_line() -> None:
    """`Scanning title 1 of 1, 70.00 %` is title-scan progress, not encode
    progress. Anchoring on `task N of M` skips it cleanly."""
    assert _match("Scanning title 1 of 1, 70.00 %") is None


def test_does_not_match_unrelated_line() -> None:
    assert _match("HandBrake 1.6.1 (2023012900) - Linux x86_64") is None
    assert _match("Cannot load libnvidia-encode.so.1") is None
    assert _match("Muxing: this may take a while...") is None


def test_pass_index_is_extracted() -> None:
    """Two-pass encodes report `task 1 of 2` then `task 2 of 2`."""
    m1 = _match("Encoding: task 1 of 2, 50.00 % (... ETA 00h05m00s)")
    m2 = _match("Encoding: task 2 of 2, 10.00 % (... ETA 00h08m00s)")
    assert m1 is not None and m1.group("pass") == "1" and m1.group("pass_total") == "2"
    assert m2 is not None and m2.group("pass") == "2" and m2.group("pass_total") == "2"


@pytest.mark.asyncio
async def test_current_pass_is_emitted_as_n_over_m() -> None:
    """The progress callback's `current` parameter is `N/M` so the UI can
    render HandBrake's internal pass count directly."""
    raw = "Encoding: task 1 of 2, 50.00 % (... ETA 00h05m00s)\rEncoding: task 2 of 2, 10.00 % (... ETA 00h08m00s)\n"
    stream = _FakeStream([raw.encode()])
    seen: list[str | None] = []

    async def cb(pct: int, eta: int | None, current: str | None) -> Awaitable[None]:  # type: ignore[return]
        seen.append(current)

    await _consume_progress(stream, cb)  # type: ignore[arg-type]
    assert seen == ["1/2", "2/2"]


# --- _consume_progress: the carriage-return splitter ------------------------


class _FakeStream:
    """Minimal `asyncio.StreamReader`-shaped stub. The real reader's
    `read(n)` is what `_consume_progress` calls; we hand it our scripted
    chunks one per call, EOF on exhaustion."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    async def read(self, n: int) -> bytes:
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


@pytest.mark.asyncio
async def test_consume_progress_splits_on_carriage_return() -> None:
    """HandBrake glues progress updates with `\\r` (no newline). A
    naive readline-loop reads them all as one giant final line and the
    UI bar gets stuck at whichever pct happens to be first in the
    buffer. Splitting on `[\\r\\n]` recovers each tick as its own
    logical line so dedupe-by-pct fires per update."""
    raw = (
        "Scanning title 1 of 1, 100.00 %\n"
        "Encoding: task 1 of 1, 0.00 %\r"
        "Encoding: task 1 of 1, 12.50 %\r"
        "Encoding: task 1 of 1, 25.00 % (140 fps, avg 140 fps, ETA 00h00m05s)\r"
        "Encoding: task 1 of 1, 50.00 % (140 fps, avg 140 fps, ETA 00h00m02s)\r"
        "Encoding: task 1 of 1, 100.00 %\n"
    )
    stream = _FakeStream([raw.encode()])

    seen: list[tuple[int, int | None, str | None]] = []

    async def cb(pct: int, eta: int | None, current: str | None) -> Awaitable[None]:  # type: ignore[return]
        seen.append((pct, eta, current))

    await _consume_progress(stream, cb)  # type: ignore[arg-type]

    pcts = [s[0] for s in seen]
    assert pcts == [0, 12, 25, 50, 100]  # one event per unique percent
    assert seen[2][1] == 5  # ETA in seconds at 25 %


@pytest.mark.asyncio
async def test_consume_progress_dedupes_repeated_percent() -> None:
    """HandBrake near 100 % spams the same `99.97 %` line until the encode
    actually finishes. The dedupe should keep the WS publish rate sane."""
    raw = (
        "Encoding: task 1 of 1, 99.97 %\r"
        "Encoding: task 1 of 1, 99.97 %\r"
        "Encoding: task 1 of 1, 99.97 %\r"
        "Encoding: task 1 of 1, 100.00 %\n"
    )
    stream = _FakeStream([raw.encode()])

    seen: list[int] = []

    async def cb(pct: int, eta: int | None, current: str | None) -> Awaitable[None]:  # type: ignore[return]
        seen.append(pct)

    await _consume_progress(stream, cb)  # type: ignore[arg-type]
    assert seen == [100]  # 99.97 → round to 100, then 100.00 same → one fire


@pytest.mark.asyncio
async def test_consume_progress_handles_chunk_boundary_mid_line() -> None:
    """The chunk read may bisect a progress line. The `pending` carry-
    over should stitch the halves back together on the next chunk."""
    chunks = [
        b"Encoding: task 1 of 1, 33.33",  # mid-token
        b" % (140 fps, avg 140 fps, ETA 00h00m05s)\rEncoding: task 1 of 1, 50",
        b".00 %\n",
    ]
    stream = _FakeStream(chunks)
    seen: list[int] = []

    async def cb(pct: int, eta: int | None, current: str | None) -> Awaitable[None]:  # type: ignore[return]
        seen.append(pct)

    await _consume_progress(stream, cb)  # type: ignore[arg-type]
    assert seen == [33, 50]


# Vitest-style asyncio plumbing — pytest-asyncio is already a dev dep.
def _autouse_asyncio_mode() -> None:
    asyncio.get_event_loop_policy()  # touch to silence unused-import warnings
