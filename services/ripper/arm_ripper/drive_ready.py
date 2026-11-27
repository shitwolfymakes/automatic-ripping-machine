"""Waits until the drive can deliver bytes from its disc, so a rip never starts a title on a drive still settling.

A drive that has just re-bound reports `CDS_DISC_OK` while its medium is still becoming ready, and the first read then
fails NOT_READY. The gate therefore needs both the status and a 2 KiB read at offset 0 to succeed.
"""

import asyncio
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum

from arm_ripper.drive_poll import DriveErrorKind, DriveState, classify_drive_error, read_drive_status

# How long a title waits for the drive: enough for the 30-60 s "becoming ready" a re-bound drive reports.
READY_BUDGET_SECONDS = 60.0
# The pause before each re-probe grows to the cap, so a quick settle is caught early and a slow one is not hammered.
_FIRST_BACKOFF_SECONDS = 2.0
_MAX_BACKOFF_SECONDS = 12.0
_SECTOR_BYTES = 2048

# Words a makemkvcon failure carries when the drive, not the title, was the problem (SCSI NOT READY / medium error).
_TRANSIENT_MARKERS = ("not ready", "becoming ready", "medium error")


class ReadyOutcome(StrEnum):
    READY = "ready"
    # The drive answers, but its disc is gone (tray open, no disc).
    LEFT_DISC = "left_disc"
    # The node is missing or has no hardware behind it.
    ABSENT = "absent"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True)
class Probe:
    """One look at the drive: its status, and whether its first sector could be read."""

    state: DriveState
    readable: bool


def backoff_schedule(budget_seconds: float) -> tuple[float, ...]:
    """The pauses between probes that add up to `budget_seconds`: 2 s, doubling to a 12 s cap, the last one cut short."""
    pauses: list[float] = []
    remaining = budget_seconds
    pause = _FIRST_BACKOFF_SECONDS
    while remaining > 0:
        pauses.append(min(pause, remaining))
        remaining -= pauses[-1]
        pause = min(pause * 2, _MAX_BACKOFF_SECONDS)
    return tuple(pauses)


def decide(probe: Probe) -> ReadyOutcome | None:
    """What a probe settles: READY, or the drive's loss; None while the drive may still become ready."""
    if probe.state is DriveState.ABSENT:
        return ReadyOutcome.ABSENT
    if probe.state in (DriveState.NO_DISC, DriveState.TRAY_OPEN):
        return ReadyOutcome.LEFT_DISC
    if probe.state is DriveState.DISC_OK and probe.readable:
        return ReadyOutcome.READY
    return None


def is_drive_transient(error: str | None, state: DriveState) -> bool:
    """Whether a failed title's cause was the drive being not ready: the drive reports NOT_READY now, or the failure
    text carries a SCSI not-ready or medium error. A drive that has gone away is not transient: the rip's drop and
    resume path owns it."""
    if state is DriveState.ABSENT:
        return False
    if state is DriveState.NOT_READY:
        return True
    text = (error or "").lower()
    return any(marker in text for marker in _TRANSIENT_MARKERS)


def _first_sector_readable(device_path: str) -> bool:
    """Whether 2 KiB can be read at offset 0 of the drive."""
    try:
        fd = os.open(device_path, os.O_RDONLY | os.O_NONBLOCK)
        try:
            os.pread(fd, _SECTOR_BYTES, 0)
        finally:
            os.close(fd)
    except OSError:
        return False
    return True


def probe_drive(device_path: str) -> Probe:
    """Look at the drive now. A node that cannot be opened reads as ABSENT, any other failure as not ready."""
    try:
        state = read_drive_status(device_path)
    except OSError as exc:
        absent = classify_drive_error(exc) is DriveErrorKind.ABSENT
        return Probe(DriveState.ABSENT if absent else DriveState.NOT_READY, False)
    return Probe(state, state is DriveState.DISC_OK and _first_sector_readable(device_path))


async def wait_until_readable(
    device_path: str,
    budget_seconds: float = READY_BUDGET_SECONDS,
    *,
    probe: Callable[[str], Probe] = probe_drive,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> ReadyOutcome:
    """Probe the drive now and again after each backoff pause, until it can deliver bytes, loses its disc or goes
    away; TIMED_OUT once `budget_seconds` of pauses have passed."""
    for pause in (0.0, *backoff_schedule(budget_seconds)):
        if pause:
            await sleep(pause)
        outcome = decide(probe(device_path))
        if outcome is not None:
            return outcome
    return ReadyOutcome.TIMED_OUT
