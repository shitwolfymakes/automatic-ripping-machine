"""TitleHasher: hashing ripped titles while the rip continues."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from arm_ripper.rip import hashing
from arm_ripper.rip.title_hasher import TitleHasher, _transfer_rate


def test_transfer_rate_is_bytes_per_second() -> None:
    assert _transfer_rate(100, 2.0) == 50.0


def test_transfer_rate_is_none_when_no_bytes_moved() -> None:
    assert _transfer_rate(0, 2.0) is None


def test_transfer_rate_is_none_when_no_time_has_passed() -> None:
    assert _transfer_rate(100, 0.0) is None


def test_transfer_rate_is_none_for_a_negative_elapsed() -> None:
    assert _transfer_rate(100, -1.0) is None


async def test_cancel_stops_the_hashing_thread_mid_file(tmp_path: Path, monkeypatch) -> None:
    """Cancelling the task cannot stop asyncio.to_thread, so
    the thread itself must stop reading; a wiped raw dir's file must not be
    read to the end at full disk bandwidth."""
    monkeypatch.setattr(hashing, "_CHUNK", 1)
    path = tmp_path / "t00.mkv"
    path.write_bytes(b"x" * 10_000)
    hasher = TitleHasher()
    first_chunk, release = threading.Event(), threading.Event()
    chunks = 0
    real_on_bytes = hasher._on_bytes

    def on_bytes(n: int) -> None:
        nonlocal chunks
        chunks += 1
        if chunks == 1:
            first_chunk.set()
            release.wait(5)
        real_on_bytes(n)

    hasher._on_bytes = on_bytes  # type: ignore[method-assign]

    async def then(digest: str | None) -> None:
        raise AssertionError("a cancelled hash must not report a digest")

    hasher.submit(path, 10_000, then)
    while not first_chunk.is_set():
        await asyncio.sleep(0.01)
    hasher.cancel()
    release.set()
    await asyncio.sleep(0.3)
    assert chunks <= 2
