import asyncio
import contextlib
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import NamedTuple

from arm_common.schemas.drives import DEFAULT_SCAN_TIMEOUT_SECONDS
from arm_common import DiscType, ScanFailureReason
from arm_common.schemas import DiscFingerprintInput, ScanResult, ScanTitle
from arm_ripper.scan.data import sniff_video_image
from arm_ripper.scan.disc_probe import DiscProbe, probe_disc
from arm_ripper.scan.makemkv_info import parse_makemkvcon_info
from arm_ripper.source import makemkv_source_url

logger = logging.getLogger("arm_ripper.scan.makemkv")

# Stop waiting when makemkvcon has printed nothing (progress lines count) for
# this long, or has been running for the drive's scan ceiling in total (its
# override, else this default).
SCAN_IDLE_TIMEOUT_SECONDS = 180.0
SCAN_MAX_SECONDS = float(DEFAULT_SCAN_TIMEOUT_SECONDS)
# makemkvcon keeps printing the disc's CINFO (after `TCOUNT:0`) or title blocks
# (after a successful end of output) and can then linger for minutes before it
# exits; wait this long for the output to go quiet, then kill instead of waiting.
SCAN_TERMINAL_GRACE_SECONDS = 5.0
# Non-progress lines kept (stdout and stderr, in arrival order) for a failure report.
SCAN_TAIL_LINES = 60

_PIPE_COUNT = 2  # stdout and stderr

# MakeMKV emits this when its hard-coded 60-day beta kill-switch has fired.
# No registration key overrides it; the binary refuses all protected-disc
# work and the only fix is rebuilding against a fresher upstream tarball.
MAKEMKV_EXPIRED_PREFIX = b"MSG:5021,"
TCOUNT_ZERO_LINE = "TCOUNT:0"
TCOUNT_PREFIX = "TCOUNT:"
# "Operation successfully completed": makemkvcon has finished enumerating the disc.
OPERATION_COMPLETED_PREFIX = "MSG:5011,"
# Disc-open failure messages. The code and text come from the issue report.
VOLUME_KEY_UNKNOWN_PREFIX = "MSG:3303,"
DISC_OPEN_FAILED_TEXT = "failed to open disc"

_EXPIRED_DETAIL = (
    "makemkvcon refused: binary is past its hard-coded expiry (MSG:5021 'application version is too old'); "
    "rebuild the ripper image after upstream ships a fresher tarball"
)


def _timed_out_detail(max_seconds: float) -> str:
    return f"makemkvcon timed out: no output for {SCAN_IDLE_TIMEOUT_SECONDS:g}s or still running after {max_seconds:g}s"


class ScanError(Exception):
    pass


class MakemkvScanFailed(ScanError):
    """makemkvcon ran but its scan failed; carries why, and the last non-progress output."""

    def __init__(
        self,
        reason: ScanFailureReason,
        detail: str,
        tail: tuple[str, ...],
        disc_type: DiscType | None = None,
    ) -> None:
        super().__init__(detail)
        self.reason = reason
        self.detail = detail
        self.tail = tail
        # What kind of disc failed: MakeMKV's CINFO:1, else a layout sniff; None when neither knew.
        self.disc_type = disc_type


def _info_command(device_path: str, min_title_length_seconds: int) -> list[str]:
    return [
        "makemkvcon",
        "-r",
        "--cache=1",
        "--progress=-stdout",
        f"--minlength={min_title_length_seconds}",
        "info",
        makemkv_source_url(device_path),
    ]


def _classify_from_titles(titles: list[ScanTitle]) -> DiscType:
    """Last-resort fallback used only when MakeMKV's CINFO:1 disc-type
    string was missing. Title size > 4.7GB is unreliable (DVD-9s exceed it
    routinely) but better than UNKNOWN.
    """
    if not titles:
        return DiscType.UNKNOWN
    longest = max(t.duration_seconds for t in titles)
    return (
        DiscType.BLURAY
        if longest >= 60 * 60 * 1.5 and any(t.size_bytes is not None and t.size_bytes > 4_700_000_000 for t in titles)
        else DiscType.DVD
    )


class _EventKind(StrEnum):
    EXPIRED = "expired"
    TCOUNT_ZERO = "tcount_zero"
    TCOUNT_TITLES = "tcount_titles"
    COMPLETED = "completed"
    REASON = "reason"
    PROGRESS = "progress"
    OTHER = "other"


@dataclass(frozen=True)
class _LineEvent:
    kind: _EventKind
    reason: ScanFailureReason | None = None


_PROGRESS_PREFIXES = ("PRGV:", "PRGT:", "PRGC:")


def _classify_line(line: str) -> _LineEvent:
    """Pure: what one line of makemkvcon output means for the scan."""
    if line.startswith(MAKEMKV_EXPIRED_PREFIX.decode()):
        return _LineEvent(_EventKind.EXPIRED)
    if line.strip() == TCOUNT_ZERO_LINE:
        return _LineEvent(_EventKind.TCOUNT_ZERO)
    if line.startswith(TCOUNT_PREFIX):
        return _LineEvent(_EventKind.TCOUNT_TITLES)
    if line.startswith(OPERATION_COMPLETED_PREFIX):
        return _LineEvent(_EventKind.COMPLETED)
    if line.startswith(VOLUME_KEY_UNKNOWN_PREFIX):
        return _LineEvent(_EventKind.REASON, ScanFailureReason.VOLUME_KEY_UNKNOWN)
    if line.startswith("MSG:") and DISC_OPEN_FAILED_TEXT in line.lower():
        return _LineEvent(_EventKind.REASON, ScanFailureReason.DISC_OPEN_FAILED)
    if line.startswith(_PROGRESS_PREFIXES):
        return _LineEvent(_EventKind.PROGRESS)
    return _LineEvent(_EventKind.OTHER)


def _on_expired(watch: "_ScanWatch", _event: _LineEvent) -> None:
    watch.expired = True


def _on_tcount_zero(watch: "_ScanWatch", _event: _LineEvent) -> None:
    watch.tcount_zero = True


def _on_tcount_titles(watch: "_ScanWatch", _event: _LineEvent) -> None:
    watch.titles_seen = True


def _on_completed(watch: "_ScanWatch", _event: _LineEvent) -> None:
    watch.completed = True


def _on_reason(watch: "_ScanWatch", event: _LineEvent) -> None:
    watch.reason = watch.reason or event.reason


def _on_other(_watch: "_ScanWatch", _event: _LineEvent) -> None:
    return None


_EVENT_HANDLERS: dict[_EventKind, Callable[["_ScanWatch", _LineEvent], None]] = {
    _EventKind.EXPIRED: _on_expired,
    _EventKind.TCOUNT_ZERO: _on_tcount_zero,
    _EventKind.TCOUNT_TITLES: _on_tcount_titles,
    _EventKind.COMPLETED: _on_completed,
    _EventKind.REASON: _on_reason,
    _EventKind.PROGRESS: _on_other,
    _EventKind.OTHER: _on_other,
}


@dataclass
class _ScanWatch:
    """What the scan has shown so far; decides when to stop waiting for makemkvcon."""

    started_at: float
    last_line_at: float
    # The hard ceiling on the whole scan: the drive's scan timeout.
    max_seconds: float = SCAN_MAX_SECONDS
    stdout: list[str] = field(default_factory=list)
    tail: deque[str] = field(default_factory=lambda: deque(maxlen=SCAN_TAIL_LINES))
    reason: ScanFailureReason | None = None
    expired: bool = False
    tcount_zero: bool = False
    titles_seen: bool = False
    completed: bool = False
    timed_out: bool = False

    def observe(self, line: str, now: float) -> None:
        self.last_line_at = now
        event = _classify_line(line)
        if event.kind is not _EventKind.PROGRESS:
            self.tail.append(line)
        _EVENT_HANDLERS[event.kind](self, event)

    @property
    def scan_complete(self) -> bool:
        """Pure: makemkvcon reported a successful end of output and a (non-zero) title count."""
        return self.completed and self.titles_seen

    @property
    def finished(self) -> bool:
        """Pure: the scan's output is over, whether or not makemkvcon has exited yet."""
        return self.tcount_zero or self.scan_complete

    def deadline(self) -> float:
        """Pure: the monotonic time at which to stop waiting (idle window or the hard ceiling)."""
        window = SCAN_TERMINAL_GRACE_SECONDS if self.finished else SCAN_IDLE_TIMEOUT_SECONDS
        return min(self.last_line_at + window, self.started_at + self.max_seconds)

    def expire(self) -> None:
        """The deadline passed. Once the output is over that is the normal end of the scan, otherwise a timeout."""
        self.timed_out = not self.finished


@dataclass(frozen=True)
class _Chunk:
    """One decoded line from one pipe; `line is None` marks that pipe's EOF."""

    is_stdout: bool
    line: str | None


async def _pump(stream: asyncio.StreamReader, queue: "asyncio.Queue[_Chunk]", is_stdout: bool) -> None:
    """I/O: copy one pipe into the queue, line by line, then post its EOF marker."""
    try:
        async for raw in stream:
            await queue.put(_Chunk(is_stdout, raw.decode(errors="replace").rstrip("\r\n")))
    finally:
        queue.put_nowait(_Chunk(is_stdout, None))


async def _next_chunk(queue: "asyncio.Queue[_Chunk]", remaining: float) -> _Chunk | None:
    """The next queued line, or None when `remaining` seconds pass first."""
    if remaining <= 0:
        return None
    try:
        return await asyncio.wait_for(queue.get(), timeout=remaining)
    except asyncio.TimeoutError:
        return None


def _feed(watch: _ScanWatch, chunk: _Chunk, now: float) -> bool:
    """Record one chunk in the watch; True when it was a pipe's EOF marker."""
    if chunk.line is None:
        return True
    if chunk.is_stdout:
        watch.stdout.append(chunk.line)
    watch.observe(chunk.line, now)
    return False


async def _watch(queue: "asyncio.Queue[_Chunk]", watch: _ScanWatch, clock: Callable[[], float]) -> bool:
    """Feed the watch until both pipes reach EOF (returns True), or it is time to give up (False)."""
    open_pipes = _PIPE_COUNT
    while open_pipes and not watch.expired:
        chunk = await _next_chunk(queue, watch.deadline() - clock())
        if chunk is None:
            watch.expire()
            return False
        open_pipes -= _feed(watch, chunk, clock())
    return open_pipes == 0


class _InfoRun(NamedTuple):
    """What one `makemkvcon info` run printed, and how it exited."""

    watch: _ScanWatch
    returncode: int | None


async def _reap(proc: asyncio.subprocess.Process, pumps: list["asyncio.Task[None]"]) -> None:
    """Side effect: kill makemkvcon if it is still running, reap it and stop the pipe readers."""
    if proc.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
    await proc.wait()
    for pump in pumps:
        pump.cancel()
    await asyncio.gather(*pumps, return_exceptions=True)


async def _run_info(
    device_path: str,
    min_title_length_seconds: int,
    clock: Callable[[], float] = time.monotonic,
    *,
    max_seconds: float = SCAN_MAX_SECONDS,
) -> _InfoRun:
    """Run `makemkvcon info` on the device, listing titles down to `min_title_length_seconds`, watching its output
    instead of a flat timeout.

    Raises ScanError when makemkvcon is not on PATH. Whatever the exit path
    (done, timed out, terminal line, cancelled) the process is killed and reaped.
    """
    logger.info("makemkvcon info device=%s", device_path)
    try:
        proc = await asyncio.create_subprocess_exec(
            *_info_command(device_path, min_title_length_seconds),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        raise ScanError("makemkvcon binary not found on PATH") from e

    assert proc.stdout is not None
    assert proc.stderr is not None
    queue: asyncio.Queue[_Chunk] = asyncio.Queue()
    pumps = [
        asyncio.create_task(_pump(proc.stdout, queue, True)),
        asyncio.create_task(_pump(proc.stderr, queue, False)),
    ]
    watch = _ScanWatch(started_at=clock(), last_line_at=clock(), max_seconds=max_seconds)
    try:
        if await _watch(queue, watch, clock):
            await proc.wait()
    finally:
        await _reap(proc, pumps)
    return _InfoRun(watch, proc.returncode)


def _failed(reason: ScanFailureReason, detail: str, watch: _ScanWatch) -> MakemkvScanFailed:
    return MakemkvScanFailed(reason, detail, tuple(watch.tail))


def _failure_of(run: _InfoRun) -> MakemkvScanFailed | None:
    """Pure: the failure this run amounts to, or None when its output can be used."""
    watch = run.watch
    if watch.expired:
        return _failed(ScanFailureReason.MAKEMKV_EXPIRED, _EXPIRED_DETAIL, watch)
    if watch.scan_complete:
        return None
    if watch.reason and (watch.tcount_zero or watch.timed_out or run.returncode != 0):
        return _failed(watch.reason, f"makemkvcon reported {watch.reason.value}", watch)
    if watch.timed_out:
        return _failed(ScanFailureReason.TIMED_OUT, _timed_out_detail(watch.max_seconds), watch)
    if watch.tcount_zero or run.returncode == 0:
        return None
    last = watch.tail[-1] if watch.tail else ""
    return _failed(ScanFailureReason.MAKEMKV_ERROR, f"makemkvcon exited {run.returncode}: {last}", watch)


def disc_fingerprints(probe: DiscProbe) -> list[DiscFingerprintInput]:
    """The disc fingerprints the probe found, in the order crc64, thediscdb, matrix256; empty values are skipped."""
    fingerprints: list[DiscFingerprintInput] = []
    if probe.crc64:
        fingerprints.append(DiscFingerprintInput(algo="crc64", value=probe.crc64))
    if probe.thediscdb:
        fingerprints.append(DiscFingerprintInput(algo="thediscdb", value=probe.thediscdb))
    if probe.matrix256:
        fingerprints.append(DiscFingerprintInput(algo="matrix256", value=probe.matrix256))
    return fingerprints


async def _failed_disc_type(device_path: str, stdout: list[str]) -> DiscType | None:
    """The disc type of a scan that failed: MakeMKV's CINFO:1 when it got that far, else the video layout the
    disc's directory names reveal; None when neither says."""
    _label, _titles, cinfo_type = parse_makemkvcon_info(stdout)
    if cinfo_type is not None:
        return cinfo_type
    return await asyncio.to_thread(sniff_video_image, device_path)


async def scan_titles(
    device_path: str, min_title_length_seconds: int, *, timeout_seconds: float = SCAN_MAX_SECONDS
) -> list[ScanTitle]:
    """The titles `makemkvcon info` lists on the disc, down to `min_title_length_seconds`, never running longer than
    `timeout_seconds`. Raises ScanError (MakemkvScanFailed when makemkvcon ran and its scan failed); used on its own
    for a disc whose structure was read separately."""
    run = await _run_info(device_path, min_title_length_seconds, max_seconds=timeout_seconds)
    failure = _failure_of(run)
    if failure is not None:
        raise failure
    _, titles, _ = parse_makemkvcon_info(run.watch.stdout)
    return titles


async def scan_disc(
    device_path: str, min_title_length_seconds: int, *, timeout_seconds: float = SCAN_MAX_SECONDS
) -> ScanResult:
    """Scan the disc with `makemkvcon info`, listing titles down to `min_title_length_seconds`, never running longer
    than `timeout_seconds` (the drive's scan ceiling)."""
    run = await _run_info(device_path, min_title_length_seconds, max_seconds=timeout_seconds)

    failure = _failure_of(run)
    if failure is not None:
        failure.disc_type = await _failed_disc_type(device_path, run.watch.stdout)
        raise failure

    volume_label, titles, mkv_disc_type = parse_makemkvcon_info(run.watch.stdout)

    # MakeMKV's CINFO:1 is the authoritative disc-type signal — works on
    # region-locked discs that the kernel refuses to mount, and on UDF
    # quirks; when CINFO:1 is missing we fall back to a title-size heuristic.
    # Classify before probing so the probe knows whether to bother opening
    # the disc a third time for the Blu-ray-only BDMT read.
    if mkv_disc_type is not None:
        disc_type = mkv_disc_type
    else:
        disc_type = _classify_from_titles(titles)
    probe = await probe_disc(device_path, bluray=disc_type == DiscType.BLURAY)

    return ScanResult(
        disc_type=disc_type,
        volume_label=volume_label,
        titles=titles,
        fingerprints=disc_fingerprints(probe),
        bd_meta=probe.bd_meta,
        min_title_length_seconds=min_title_length_seconds,
    )
