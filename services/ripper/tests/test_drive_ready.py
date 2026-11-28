"""The drive-readiness gate: its pure decisions, the probe's I/O mapping and the wait loop."""

import errno
import os

import pytest

from arm_ripper import drive_ready
from arm_ripper.drive_poll import DriveState
from arm_ripper.drive_ready import Probe, ReadyOutcome


@pytest.mark.parametrize(
    ("budget", "expected"),
    [
        (0.0, ()),
        (2.0, (2.0,)),
        (3.0, (2.0, 1.0)),
        (26.0, (2.0, 4.0, 8.0, 12.0)),
        (60.0, (2.0, 4.0, 8.0, 12.0, 12.0, 12.0, 10.0)),
    ],
)
def test_backoff_schedule_adds_up_to_the_budget(budget: float, expected: tuple[float, ...]) -> None:
    assert drive_ready.backoff_schedule(budget) == expected


@pytest.mark.parametrize(
    ("state", "readable", "outcome"),
    [
        (DriveState.DISC_OK, True, ReadyOutcome.READY),
        (DriveState.DISC_OK, False, None),
        (DriveState.NOT_READY, False, None),
        (DriveState.NO_INFO, False, None),
        (DriveState.NO_DISC, False, ReadyOutcome.LEFT_DISC),
        (DriveState.TRAY_OPEN, False, ReadyOutcome.LEFT_DISC),
        (DriveState.ABSENT, False, ReadyOutcome.ABSENT),
    ],
)
def test_decide(state: DriveState, readable: bool, outcome: ReadyOutcome | None) -> None:
    assert drive_ready.decide(Probe(state, readable)) is outcome


@pytest.mark.parametrize(
    ("error", "state", "transient"),
    [
        ("makemkvcon failed: exit=11", DriveState.NOT_READY, True),
        ("makemkvcon failed: SCSI NOT READY, LOGICAL UNIT IS IN PROCESS OF BECOMING READY", DriveState.DISC_OK, True),
        ("Medium Error reading sector", DriveState.DISC_OK, True),
        ("Failed to save title 2", DriveState.DISC_OK, False),
        (None, DriveState.DISC_OK, False),
        ("not ready", DriveState.ABSENT, False),
    ],
)
def test_is_drive_transient(error: str | None, state: DriveState, transient: bool) -> None:
    assert drive_ready.is_drive_transient(error, state) is transient


def test_first_sector_readable_reads_2_kib_at_offset_zero(tmp_path) -> None:
    dev = tmp_path / "sr0"
    dev.write_bytes(b"x" * 4096)
    assert drive_ready._first_sector_readable(str(dev)) is True


def test_first_sector_readable_is_false_when_the_open_fails(tmp_path) -> None:
    assert drive_ready._first_sector_readable(str(tmp_path / "missing")) is False


def test_first_sector_readable_is_false_when_the_read_fails_and_closes_the_fd(monkeypatch, tmp_path) -> None:
    dev = tmp_path / "sr0"
    dev.write_bytes(b"x")
    closed: list[int] = []
    real_close = os.close

    def failing_pread(_fd: int, _n: int, _off: int) -> bytes:
        raise OSError(errno.EIO, "I/O error")

    def tracking_close(fd: int) -> None:
        closed.append(fd)
        real_close(fd)

    monkeypatch.setattr(drive_ready.os, "pread", failing_pread)
    monkeypatch.setattr(drive_ready.os, "close", tracking_close)
    assert drive_ready._first_sector_readable(str(dev)) is False
    assert len(closed) == 1


def test_probe_drive_reads_the_sector_only_when_the_disc_is_ok(monkeypatch) -> None:
    reads: list[str] = []
    monkeypatch.setattr(drive_ready, "read_drive_status", lambda _p: DriveState.DISC_OK)
    monkeypatch.setattr(drive_ready, "_first_sector_readable", lambda p: reads.append(p) or True)
    assert drive_ready.probe_drive("/dev/sr0") == Probe(DriveState.DISC_OK, True)
    monkeypatch.setattr(drive_ready, "read_drive_status", lambda _p: DriveState.NOT_READY)
    assert drive_ready.probe_drive("/dev/sr0") == Probe(DriveState.NOT_READY, False)
    assert reads == ["/dev/sr0"]


@pytest.mark.parametrize(("err", "state"), [(errno.ENODEV, DriveState.ABSENT), (errno.EIO, DriveState.NOT_READY)])
def test_probe_drive_maps_an_open_failure(monkeypatch, err: int, state: DriveState) -> None:
    def boom(_p: str) -> DriveState:
        raise OSError(err, os.strerror(err))

    monkeypatch.setattr(drive_ready, "read_drive_status", boom)
    assert drive_ready.probe_drive("/dev/sr0") == Probe(state, False)


class _Clock:
    """A fake sleep that records the pauses and a probe that replays a script."""

    def __init__(self, probes: list[Probe]) -> None:
        self.pauses: list[float] = []
        self._probes = probes

    async def sleep(self, seconds: float) -> None:
        self.pauses.append(seconds)

    def probe(self, _path: str) -> Probe:
        return self._probes.pop(0) if len(self._probes) > 1 else self._probes[0]


_READY = Probe(DriveState.DISC_OK, True)
_SETTLING = Probe(DriveState.DISC_OK, False)


async def test_a_ready_drive_passes_without_a_pause() -> None:
    clock = _Clock([_READY])
    assert await drive_ready.wait_until_readable("/dev/sr0", probe=clock.probe, sleep=clock.sleep) is ReadyOutcome.READY
    assert clock.pauses == []


async def test_a_settling_drive_is_waited_for_with_growing_pauses() -> None:
    clock = _Clock([_SETTLING, _SETTLING, _SETTLING, _READY])
    outcome = await drive_ready.wait_until_readable("/dev/sr0", probe=clock.probe, sleep=clock.sleep)
    assert outcome is ReadyOutcome.READY
    assert clock.pauses == [2.0, 4.0, 8.0]


async def test_a_drive_that_never_settles_times_out_after_the_whole_budget() -> None:
    clock = _Clock([_SETTLING])
    outcome = await drive_ready.wait_until_readable("/dev/sr0", 14.0, probe=clock.probe, sleep=clock.sleep)
    assert outcome is ReadyOutcome.TIMED_OUT
    assert sum(clock.pauses) == 14.0


@pytest.mark.parametrize(
    ("state", "outcome"),
    [(DriveState.NO_DISC, ReadyOutcome.LEFT_DISC), (DriveState.ABSENT, ReadyOutcome.ABSENT)],
)
async def test_the_wait_ends_early_when_the_drive_loses_its_disc_or_goes_away(
    state: DriveState, outcome: ReadyOutcome
) -> None:
    clock = _Clock([_SETTLING, Probe(state, False)])
    assert await drive_ready.wait_until_readable("/dev/sr0", probe=clock.probe, sleep=clock.sleep) is outcome
    assert clock.pauses == [2.0]


def _iso(tmp_path) -> str:
    iso = tmp_path / "disc.iso"
    iso.write_bytes(b"\0" * 4096)
    return str(iso)


def _disc_folder(tmp_path) -> str:
    (tmp_path / "Movie" / "BDMV").mkdir(parents=True)
    return str(tmp_path / "Movie")


@pytest.mark.parametrize("make_source", [_iso, _disc_folder])
def test_a_file_source_probes_as_a_readable_disc(tmp_path, make_source) -> None:
    # The drive-status ioctl on a regular file fails ENOTTY, which used to read as NOT_READY for the whole budget.
    assert drive_ready.probe_drive(make_source(tmp_path)) == Probe(DriveState.DISC_OK, True)


async def test_an_iso_source_passes_the_gate_without_a_pause(tmp_path) -> None:
    pauses: list[float] = []

    async def sleep(seconds: float) -> None:
        pauses.append(seconds)

    assert await drive_ready.wait_until_readable(_iso(tmp_path), sleep=sleep) is ReadyOutcome.READY
    assert pauses == []
