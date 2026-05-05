"""Dispatcher between-titles drive-readiness wait.

Reproduces the scenario from the LG BP50NB40 USB Blu-ray drive: after a
long, successful rip of title 0, the drive vanishes from the kernel and
subsequent makemkvcon invocations fail with ENODEV. The fix polls
`/dev/sr0` for a re-open between titles so the bounded wait can rescue
the rip. These tests cover the readiness probe in isolation plus its
integration into rip_all.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path
from typing import Any


import arm_ripper.rip.dispatcher as dispatcher_module
from arm_common import DiscType
from arm_common.enums import TrackKind, TrackStatus
from arm_common.schemas import TrackView

from arm_ripper.rip.dispatcher import _wait_for_drive_ready, rip_all
from arm_ripper.rip.makemkv_rip import RipResult


def _track(idx: int) -> TrackView:
    return TrackView(
        id=f"trk_{idx}",
        job_id="job_test",
        kind=TrackKind.VIDEO_TITLE,
        index=idx,
        source_ref=str(idx),
        status=TrackStatus.QUEUED,
        output_path=None,
        size_bytes=None,
        duration_seconds=None,
        attempts=0,
        last_error=None,
    )


# --- _wait_for_drive_ready ---------------------------------------------------


async def test_wait_returns_immediately_when_drive_is_open(monkeypatch, tmp_path):
    opens: list[str] = []
    closes: list[int] = []

    def fake_open(path: str, flags: int) -> int:
        opens.append(path)
        return 99

    def fake_close(fd: int) -> None:
        closes.append(fd)

    monkeypatch.setattr(os, "open", fake_open)
    monkeypatch.setattr(os, "close", fake_close)

    sleep_calls: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(dispatcher_module.asyncio, "sleep", fake_sleep)

    ok = await _wait_for_drive_ready("/dev/sr0", timeout_seconds=5.0, poll_interval_seconds=0.01)
    assert ok is True
    assert opens == ["/dev/sr0"]
    assert closes == [99]
    # No sleeps because the very first probe succeeded.
    assert sleep_calls == []


async def test_wait_polls_then_succeeds(monkeypatch):
    """Drive returns ENODEV twice, then re-binds. Wait succeeds on the third probe."""
    sequence = iter([OSError(errno.ENODEV, "No such device"), OSError(errno.ENODEV, "No such device"), 7])

    def fake_open(path: str, flags: int) -> int:
        result = next(sequence)
        if isinstance(result, Exception):
            raise result
        return result

    closed: list[int] = []

    monkeypatch.setattr(os, "open", fake_open)
    monkeypatch.setattr(os, "close", lambda fd: closed.append(fd))

    sleep_count = 0

    async def fake_sleep(delay: float) -> None:
        nonlocal sleep_count
        sleep_count += 1

    monkeypatch.setattr(dispatcher_module.asyncio, "sleep", fake_sleep)

    ok = await _wait_for_drive_ready("/dev/sr0", timeout_seconds=5.0, poll_interval_seconds=0.01)
    assert ok is True
    # Two failures + one success → two intermediate sleeps.
    assert sleep_count == 2
    assert closed == [7]


async def test_wait_returns_false_on_timeout(monkeypatch, caplog):
    def fake_open(path: str, flags: int) -> int:
        raise OSError(errno.ENODEV, "No such device")

    monkeypatch.setattr(os, "open", fake_open)

    # Drive monotonic() forward a bit each call so the deadline is hit
    # after a couple of iterations regardless of how many times the
    # function probes the clock.
    counter = {"n": 0}

    def fake_monotonic() -> float:
        counter["n"] += 1
        return counter["n"] * 0.05

    monkeypatch.setattr(dispatcher_module.time, "monotonic", fake_monotonic)

    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(dispatcher_module.asyncio, "sleep", fake_sleep)

    with caplog.at_level("WARNING", logger="arm_ripper.rip.dispatcher"):
        ok = await _wait_for_drive_ready("/dev/sr0", timeout_seconds=0.2, poll_interval_seconds=0.01)

    assert ok is False
    assert any("did not become ready" in r.message for r in caplog.records)
    # Each iteration except the last (which sees the deadline crossed) sleeps.
    assert len(sleeps) >= 1


# --- rip_all integration -----------------------------------------------------


async def test_rip_all_calls_readiness_check_between_tracks(monkeypatch, tmp_path):
    rip_calls: list[int] = []
    readiness_calls: list[str] = []

    async def fake_rip_title(
        *,
        device_path: str,
        title_index: int,
        output_dir: Path,
        expected_duration_seconds: int | None,
        on_progress: Any,
    ) -> RipResult:
        rip_calls.append(title_index)
        return RipResult(ok=True, output_path=output_dir / f"t{title_index}.mkv", size_bytes=1)

    async def fake_wait(device_path: str, **kwargs: Any) -> bool:
        readiness_calls.append(device_path)
        return True

    monkeypatch.setattr(dispatcher_module, "rip_title", fake_rip_title)
    monkeypatch.setattr(dispatcher_module, "_wait_for_drive_ready", fake_wait)

    started: list[str] = []
    done: list[tuple[str, bool]] = []

    async def on_start(track: TrackView) -> None:
        started.append(track.id)

    async def on_done(track: TrackView, result: RipResult) -> None:
        done.append((track.id, result.ok))

    tracks = [_track(0), _track(1), _track(2)]
    await rip_all(
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        tracks=tracks,
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
    )

    assert rip_calls == [0, 1, 2]
    # Readiness wait runs between tracks (i > 0), not before the first.
    assert readiness_calls == ["/dev/sr0", "/dev/sr0"]
    assert started == ["trk_0", "trk_1", "trk_2"]
    assert [t for t, ok in done] == ["trk_0", "trk_1", "trk_2"]
    assert all(ok for _, ok in done)


async def test_rip_all_proceeds_even_if_readiness_times_out(monkeypatch, tmp_path):
    """If the wait fails the next rip still runs — the existing
    makemkvcon error path will produce the user-visible failure, and we
    don't want to silently skip queued work."""
    rip_calls: list[int] = []

    async def fake_rip_title(*, title_index: int, **kwargs: Any) -> RipResult:
        rip_calls.append(title_index)
        return RipResult(ok=True)

    async def fake_wait(device_path: str, **kwargs: Any) -> bool:
        return False  # Drive never came back.

    monkeypatch.setattr(dispatcher_module, "rip_title", fake_rip_title)
    monkeypatch.setattr(dispatcher_module, "_wait_for_drive_ready", fake_wait)

    tracks = [_track(0), _track(1)]

    async def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    await rip_all(
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        tracks=tracks,
        output_dir=tmp_path,
        on_track_start=noop,
        on_track_done=noop,
    )

    assert rip_calls == [0, 1]


async def test_rip_all_skips_readiness_on_single_track(monkeypatch, tmp_path):
    readiness_calls = 0

    async def fake_wait(*args: Any, **kwargs: Any) -> bool:
        nonlocal readiness_calls
        readiness_calls += 1
        return True

    async def fake_rip_title(**kwargs: Any) -> RipResult:
        return RipResult(ok=True)

    monkeypatch.setattr(dispatcher_module, "_wait_for_drive_ready", fake_wait)
    monkeypatch.setattr(dispatcher_module, "rip_title", fake_rip_title)

    async def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    await rip_all(
        disc_type=DiscType.DVD,
        device_path="/dev/sr0",
        tracks=[_track(0)],
        output_dir=tmp_path,
        on_track_start=noop,
        on_track_done=noop,
    )

    assert readiness_calls == 0
