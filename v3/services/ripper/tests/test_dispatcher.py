"""Dispatcher between-titles drive-readiness wait.

Reproduces two failure modes seen on an LG BP50NB40 USB Blu-ray drive
after a long, successful rip of title 0:
  (1) the kernel unbinds /dev/sr0 entirely (open returns ENODEV), and
  (2) the device re-binds but the medium stays in SCSI "becoming
      ready" state for another 30-60s.
The fix polls (open + CDROM_DRIVE_STATUS) between titles. Tests cover
the probe + the wait + the rip_all integration.
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

from arm_ripper.rip.dispatcher import _drive_status, _wait_for_drive_ready, rip_all
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


# --- _drive_status (single probe) -------------------------------------------


def _patch_open_close_ioctl(monkeypatch, *, open_result, ioctl_result):
    """Helper: stub os.open/os.close/fcntl.ioctl together so a single
    test can describe one probe's worth of behaviour. open_result is
    either a fake fd (int) or an Exception to raise; ioctl_result is
    either an int CDS_* status or an Exception."""

    def fake_open(path: str, flags: int) -> int:
        if isinstance(open_result, Exception):
            raise open_result
        return open_result

    def fake_close(fd: int) -> None:
        return None

    def fake_ioctl(fd: int, request: int, arg: int) -> int:
        if isinstance(ioctl_result, Exception):
            raise ioctl_result
        return ioctl_result

    monkeypatch.setattr(os, "open", fake_open)
    monkeypatch.setattr(os, "close", fake_close)
    monkeypatch.setattr(dispatcher_module.fcntl, "ioctl", fake_ioctl)


def test_drive_status_ready_when_open_and_disc_ok(monkeypatch):
    _patch_open_close_ioctl(monkeypatch, open_result=11, ioctl_result=4)  # CDS_DISC_OK
    ready, reason = _drive_status("/dev/sr0")
    assert ready is True
    assert "CDS_DISC_OK" in reason


def test_drive_status_not_ready_when_open_fails(monkeypatch):
    _patch_open_close_ioctl(
        monkeypatch,
        open_result=OSError(errno.ENODEV, "No such device"),
        ioctl_result=4,
    )
    ready, reason = _drive_status("/dev/sr0")
    assert ready is False
    assert "errno=19" in reason


def test_drive_status_not_ready_when_disc_becoming_ready(monkeypatch):
    """SCSI 'IS IN PROCESS OF BECOMING READY' — open() works, ioctl
    returns CDS_DRIVE_NOT_READY (3). This is the second failure mode
    seen in production; the previous fix only checked open()."""
    _patch_open_close_ioctl(monkeypatch, open_result=11, ioctl_result=3)
    ready, reason = _drive_status("/dev/sr0")
    assert ready is False
    assert "CDROM_DRIVE_STATUS=3" in reason


def test_drive_status_assumes_ready_when_ioctl_unsupported(monkeypatch):
    """A non-CDROM block device backing /dev/sr0 (rare; happens in
    container test setups) returns ENOTTY from CDROM_DRIVE_STATUS.
    Better to proceed than to deadlock — makemkvcon will give us a
    real signal."""
    _patch_open_close_ioctl(
        monkeypatch,
        open_result=11,
        ioctl_result=OSError(errno.ENOTTY, "Inappropriate ioctl for device"),
    )
    ready, reason = _drive_status("/dev/sr0")
    assert ready is True
    assert "ioctl unsupported" in reason


# --- _wait_for_drive_ready (loop) -------------------------------------------


async def test_wait_returns_immediately_when_drive_is_ready(monkeypatch):
    _patch_open_close_ioctl(monkeypatch, open_result=11, ioctl_result=4)

    sleep_calls: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleep_calls.append(delay)

    monkeypatch.setattr(dispatcher_module.asyncio, "sleep", fake_sleep)

    ok = await _wait_for_drive_ready("/dev/sr0", timeout_seconds=5.0, poll_interval_seconds=0.01)
    assert ok is True
    # No sleeps because the very first probe succeeded.
    assert sleep_calls == []


async def test_wait_polls_through_not_ready_until_ok(monkeypatch):
    """ENODEV → CDS_DRIVE_NOT_READY → CDS_DISC_OK. Three probes, two sleeps."""
    open_seq = iter([OSError(errno.ENODEV, "No such device"), 11, 11])
    # Probe 1 fails on open, ioctl never called. Probes 2-3 hit ioctl: first NOT_READY, then OK.
    ioctl_seq = iter([3, 4])

    def fake_open(path: str, flags: int) -> int:
        result = next(open_seq)
        if isinstance(result, Exception):
            raise result
        return result

    def fake_ioctl(fd: int, request: int, arg: int) -> int:
        return next(ioctl_seq)

    monkeypatch.setattr(os, "open", fake_open)
    monkeypatch.setattr(os, "close", lambda fd: None)
    monkeypatch.setattr(dispatcher_module.fcntl, "ioctl", fake_ioctl)

    sleeps = 0

    async def fake_sleep(delay: float) -> None:
        nonlocal sleeps
        sleeps += 1

    monkeypatch.setattr(dispatcher_module.asyncio, "sleep", fake_sleep)

    ok = await _wait_for_drive_ready("/dev/sr0", timeout_seconds=5.0, poll_interval_seconds=0.01)
    assert ok is True
    assert sleeps == 2


async def test_wait_returns_false_on_timeout(monkeypatch, caplog):
    _patch_open_close_ioctl(monkeypatch, open_result=11, ioctl_result=3)  # forever NOT_READY

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
