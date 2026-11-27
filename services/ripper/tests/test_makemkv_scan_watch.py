"""The scan reader: line classification, the watch's deadline rules, and the run's kill paths."""

from __future__ import annotations

import os

os.environ.setdefault("ARM_DRIVE_DEV", "/dev/sr0")
os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend.invalid")
os.environ.setdefault("ARM_SERVICE_TOKEN", "test-token")

import asyncio  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402
from arm_common.enums import ScanFailureReason  # noqa: E402

import arm_ripper.scan.makemkv as mk  # noqa: E402
from arm_ripper.scan.disc_probe import DiscProbe  # noqa: E402
from arm_ripper.scan.makemkv import (  # noqa: E402
    MakemkvScanFailed,
    _Chunk,
    _classify_line,
    _EventKind,
    _failure_of,
    _feed,
    _info_command,
    _InfoRun,
    _next_chunk,
    _pump,
    _run_info,
    _ScanWatch,
    _watch,
    scan_disc,
)

FIXTURES = Path(__file__).parent / "fixtures"


class _FakeClock:
    """A monotonic clock the test moves by hand."""

    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


# ---- _classify_line -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "kind", "reason"),
    [
        ('MSG:5021,131332,1,"too old"', _EventKind.EXPIRED, None),
        ("TCOUNT:0", _EventKind.TCOUNT_ZERO, None),
        ("TCOUNT:0\r", _EventKind.TCOUNT_ZERO, None),
        ("TCOUNT:2", _EventKind.OTHER, None),
        ("TCOUNT:10", _EventKind.OTHER, None),
        ('MSG:3303,0,1,"Volume key unknown"', _EventKind.REASON, ScanFailureReason.VOLUME_KEY_UNKNOWN),
        ('MSG:5010,0,0,"Failed to open disc"', _EventKind.REASON, ScanFailureReason.DISC_OPEN_FAILED),
        ('MSG:5010,0,0,"FAILED TO OPEN DISC"', _EventKind.REASON, ScanFailureReason.DISC_OPEN_FAILED),
        ('CINFO:2,0,"Failed to open disc"', _EventKind.OTHER, None),
        ("PRGV:1,2,3", _EventKind.PROGRESS, None),
        ('PRGT:1,0,"Opening"', _EventKind.PROGRESS, None),
        ('PRGC:1,0,"Scanning"', _EventKind.PROGRESS, None),
        ('MSG:3025,0,1,"see MSG:5021, nothing"', _EventKind.OTHER, None),
        ('MSG:1005,0,1,"started"', _EventKind.OTHER, None),
    ],
)
def test_classify_line(line: str, kind: _EventKind, reason: ScanFailureReason | None) -> None:
    event = _classify_line(line)

    assert (event.kind, event.reason) == (kind, reason)


# ---- _ScanWatch -----------------------------------------------------------------------------


def _fresh(now: float = 0.0) -> _ScanWatch:
    return _ScanWatch(started_at=now, last_line_at=now)


def test_observe_records_tail_and_stamps_time_but_skips_progress() -> None:
    watch = _fresh()

    watch.observe("PRGV:1,2,3", 4.0)
    watch.observe('CINFO:2,0,"X"', 5.0)

    assert list(watch.tail) == ['CINFO:2,0,"X"']
    assert watch.last_line_at == 5.0


def test_observe_sets_state_for_each_terminal_event() -> None:
    watch = _fresh()

    watch.observe("MSG:5021,1", 1.0)
    watch.observe("TCOUNT:0", 2.0)

    assert (watch.expired, watch.tcount_zero) == (True, True)


def test_observe_keeps_the_first_reason() -> None:
    watch = _fresh()

    watch.observe("MSG:3303,0,1,key", 1.0)
    watch.observe('MSG:5010,0,0,"Failed to open disc"', 2.0)

    assert watch.reason is ScanFailureReason.VOLUME_KEY_UNKNOWN


def test_tail_is_capped_and_oldest_lines_fall_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mk, "SCAN_TAIL_LINES", 3)
    watch = _fresh()

    for i in range(5):
        watch.observe(f"line {i}", float(i))

    assert list(watch.tail) == ["line 2", "line 3", "line 4"]


def test_default_tail_cap_is_60() -> None:
    assert _fresh().tail.maxlen == 60


def test_deadline_is_the_idle_window_after_the_last_line() -> None:
    watch = _fresh(100.0)
    watch.observe("x", 110.0)

    assert watch.deadline() == 110.0 + mk.SCAN_IDLE_TIMEOUT_SECONDS


def test_deadline_shrinks_to_the_grace_window_after_tcount_zero() -> None:
    watch = _fresh()
    watch.observe("TCOUNT:0", 10.0)

    assert watch.deadline() == 10.0 + mk.SCAN_TERMINAL_GRACE_SECONDS


def test_deadline_never_passes_the_hard_ceiling() -> None:
    watch = _fresh(0.0)
    watch.observe("PRGV:1,1,1", mk.SCAN_MAX_SECONDS - 1.0)

    assert watch.deadline() == mk.SCAN_MAX_SECONDS


def test_expire_is_a_timeout_unless_tcount_zero_was_seen() -> None:
    quiet, terminal = _fresh(), _fresh()
    terminal.observe("TCOUNT:0", 1.0)

    quiet.expire()
    terminal.expire()

    assert (quiet.timed_out, terminal.timed_out) == (True, False)


# ---- _failure_of ----------------------------------------------------------------------------


def _watch_of(*lines: str) -> _ScanWatch:
    watch = _fresh()
    for line in lines:
        watch.observe(line, 1.0)
    return watch


def test_failure_of_expired_wins_over_everything() -> None:
    watch = _watch_of("MSG:3303,0,1,key", "TCOUNT:0", "MSG:5021,1")
    watch.timed_out = True

    failure = _failure_of(_InfoRun(watch, 1))

    assert failure is not None
    assert failure.reason is ScanFailureReason.MAKEMKV_EXPIRED
    assert failure.tail[-1] == "MSG:5021,1"


@pytest.mark.parametrize(
    ("timed_out", "returncode", "lines"),
    [
        (False, 0, ("MSG:3303,0,1,key", "TCOUNT:0")),  # exit 0, no titles
        (True, -9, ("MSG:3303,0,1,key",)),  # killed on the idle timeout
        (False, 2, ("MSG:3303,0,1,key",)),  # plain non-zero exit
    ],
)
def test_failure_of_a_seen_reason_names_it(timed_out: bool, returncode: int, lines: tuple[str, ...]) -> None:
    watch = _watch_of(*lines)
    watch.timed_out = timed_out

    failure = _failure_of(_InfoRun(watch, returncode))

    assert failure is not None
    assert failure.reason is ScanFailureReason.VOLUME_KEY_UNKNOWN
    assert failure.tail == lines


def test_failure_of_a_reason_with_a_clean_run_that_found_titles_is_not_a_failure() -> None:
    assert _failure_of(_InfoRun(_watch_of("MSG:3303,0,1,key", "TCOUNT:2"), 0)) is None


def test_failure_of_timeout_without_reason() -> None:
    watch = _watch_of("PRGV:1,1,1")
    watch.timed_out = True

    failure = _failure_of(_InfoRun(watch, -9))

    assert failure is not None
    assert failure.reason is ScanFailureReason.TIMED_OUT
    assert "180s" in failure.detail
    assert "1200s" in failure.detail


def test_failure_of_tcount_zero_without_reason_is_the_empty_result_even_when_we_killed_it() -> None:
    assert _failure_of(_InfoRun(_watch_of("TCOUNT:0"), -9)) is None


def test_failure_of_clean_exit_is_not_a_failure() -> None:
    assert _failure_of(_InfoRun(_watch_of('CINFO:1,0,"DVD"'), 0)) is None


def test_failure_of_nonzero_exit_reports_the_last_tail_line() -> None:
    failure = _failure_of(_InfoRun(_watch_of("one", "two"), 3))

    assert failure is not None
    assert failure.reason is ScanFailureReason.MAKEMKV_ERROR
    assert failure.detail == "makemkvcon exited 3: two"


def test_failure_of_nonzero_exit_with_no_output() -> None:
    failure = _failure_of(_InfoRun(_fresh(), 1))

    assert failure is not None
    assert failure.detail == "makemkvcon exited 1: "


def test_scan_failed_is_a_scan_error_with_its_fields() -> None:
    err = MakemkvScanFailed(ScanFailureReason.TIMED_OUT, "slow", ("a",))

    assert (str(err), err.reason, err.detail, err.tail) == ("slow", ScanFailureReason.TIMED_OUT, "slow", ("a",))


def test_info_command_requests_progress_on_stdout() -> None:
    assert _info_command("/dev/sr0")[:5] == ["makemkvcon", "-r", "--cache=1", "--progress=-stdout", "info"]


# ---- _pump / _next_chunk / _feed / _watch ---------------------------------------------------


class _Lines:
    """Async-iterable pipe: yields byte lines, optionally raising at the end."""

    def __init__(self, lines: list[bytes], error: BaseException | None = None) -> None:
        self._lines = list(lines)
        self._error = error

    def __aiter__(self) -> _Lines:
        return self

    async def __anext__(self) -> bytes:
        if self._lines:
            return self._lines.pop(0)
        if self._error is not None:
            raise self._error
        raise StopAsyncIteration


async def _drain(queue: asyncio.Queue[_Chunk]) -> list[_Chunk]:
    out: list[_Chunk] = []
    while not queue.empty():
        out.append(queue.get_nowait())
    return out


async def test_pump_decodes_lines_and_posts_eof() -> None:
    queue: asyncio.Queue[_Chunk] = asyncio.Queue()

    await _pump(_Lines([b"a\r\n", b"\xffb\n"]), queue, True)  # type: ignore[arg-type]

    assert await _drain(queue) == [_Chunk(True, "a"), _Chunk(True, "�b"), _Chunk(True, None)]


async def test_pump_posts_eof_even_when_the_pipe_breaks() -> None:
    queue: asyncio.Queue[_Chunk] = asyncio.Queue()

    with pytest.raises(OSError):
        await _pump(_Lines([], OSError("boom")), queue, False)  # type: ignore[arg-type]

    assert await _drain(queue) == [_Chunk(False, None)]


async def test_next_chunk_returns_a_queued_line() -> None:
    queue: asyncio.Queue[_Chunk] = asyncio.Queue()
    queue.put_nowait(_Chunk(True, "x"))

    assert await _next_chunk(queue, 5.0) == _Chunk(True, "x")


async def test_next_chunk_is_none_when_no_time_remains() -> None:
    queue: asyncio.Queue[_Chunk] = asyncio.Queue()
    queue.put_nowait(_Chunk(True, "x"))

    assert await _next_chunk(queue, 0.0) is None
    assert queue.qsize() == 1


async def test_next_chunk_is_none_when_the_wait_times_out() -> None:
    assert await _next_chunk(asyncio.Queue(), 0.01) is None


def test_feed_eof_marker_records_nothing() -> None:
    watch = _fresh()

    assert _feed(watch, _Chunk(True, None), 1.0) is True
    assert (watch.stdout, list(watch.tail)) == ([], [])


def test_feed_keeps_stdout_lines_but_not_stderr_ones() -> None:
    watch = _fresh()

    assert _feed(watch, _Chunk(True, "out"), 1.0) is False
    assert _feed(watch, _Chunk(False, "err"), 2.0) is False

    assert watch.stdout == ["out"]
    assert list(watch.tail) == ["out", "err"]


def _queue_of(*chunks: _Chunk) -> asyncio.Queue[_Chunk]:
    queue: asyncio.Queue[_Chunk] = asyncio.Queue()
    for chunk in chunks:
        queue.put_nowait(chunk)
    return queue


_EOFS = (_Chunk(True, None), _Chunk(False, None))


async def test_watch_returns_true_once_both_pipes_hit_eof() -> None:
    watch = _fresh()
    queue = _queue_of(_Chunk(True, "a"), _Chunk(False, "b"), *_EOFS)

    assert await _watch(queue, watch, _FakeClock()) is True
    assert list(watch.tail) == ["a", "b"]


async def test_watch_stops_on_expired_without_reading_further() -> None:
    watch = _fresh()
    queue = _queue_of(_Chunk(True, "MSG:5021,1"), _Chunk(True, "later"), *_EOFS)

    assert await _watch(queue, watch, _FakeClock()) is False
    assert watch.expired is True
    assert "later" not in watch.tail


async def test_watch_idle_timeout_fires_when_lines_stop() -> None:
    clock = _FakeClock()
    watch = _fresh()
    queue = _queue_of(_Chunk(True, "a"))
    clock.now = mk.SCAN_IDLE_TIMEOUT_SECONDS + 1  # time has passed with nothing else printed

    assert await _watch(queue, watch, clock) is False
    # the queued line was never read: no time remained at the first look
    assert watch.timed_out is True


async def test_watch_idle_timeout_after_a_line_then_silence(monkeypatch: pytest.MonkeyPatch) -> None:
    """A real wait elapses: one line arrives, then nothing for the (shrunk) idle window."""
    monkeypatch.setattr(mk, "SCAN_IDLE_TIMEOUT_SECONDS", 0.05)
    watch = _fresh(time.monotonic())
    queue = _queue_of(_Chunk(True, "a"))

    assert await _watch(queue, watch, time.monotonic) is False

    assert (watch.timed_out, list(watch.tail)) == (True, ["a"])


async def test_watch_steady_progress_keeps_it_alive_until_the_ceiling() -> None:
    clock = _FakeClock()
    watch = _fresh()
    queue: asyncio.Queue[_Chunk] = asyncio.Queue()
    for _ in range(100):
        queue.put_nowait(_Chunk(True, "PRGV:1,1,1"))

    ticks = iter(range(0, 10_000, 100))  # each clock read moves 100 s: never idle for 180 s

    def _clock() -> float:
        clock.now = float(next(ticks))
        return clock.now

    assert await _watch(queue, watch, _clock) is False
    assert watch.timed_out is True
    assert clock.now >= mk.SCAN_MAX_SECONDS - mk.SCAN_IDLE_TIMEOUT_SECONDS
    assert queue.qsize() > 0  # killed with progress still arriving


async def test_watch_tcount_zero_keeps_cinfo_within_the_grace_then_ends_normally() -> None:
    clock = _FakeClock()
    watch = _fresh()
    queue = _queue_of(_Chunk(True, "TCOUNT:0"), _Chunk(True, 'CINFO:1,6206,"Blu-ray disc"'))
    reads = iter([1.0, 2.0, 2.0, 2.0, 100.0])  # two lines arrive, then the grace lapses

    def _clock() -> float:
        clock.now = next(reads)
        return clock.now

    assert await _watch(queue, watch, _clock) is False
    assert watch.stdout == ["TCOUNT:0", 'CINFO:1,6206,"Blu-ray disc"']
    assert (watch.tcount_zero, watch.timed_out) == (True, False)


# ---- _run_info with a fake subprocess -------------------------------------------------------


class _Hang:
    """A pipe that never produces a line until released."""

    def __init__(self) -> None:
        self.event = asyncio.Event()

    def __aiter__(self) -> _Hang:
        return self

    async def __anext__(self) -> bytes:
        await self.event.wait()
        raise StopAsyncIteration


class _Proc:
    def __init__(self, stdout: Any, stderr: Any | None = None, returncode: int = 0) -> None:
        self.stdout = stdout
        self.stderr = stderr if stderr is not None else _Lines([])
        self.returncode: int | None = None
        self._rc = returncode
        self.killed = False
        self.kills = 0

    def kill(self) -> None:
        self.kills += 1
        self.killed = True
        for pipe in (self.stdout, self.stderr):
            if isinstance(pipe, _Hang):
                pipe.event.set()

    async def wait(self) -> int:
        if self.returncode is None:
            self.returncode = -9 if self.killed else self._rc
        return self.returncode


def _spawn(monkeypatch: pytest.MonkeyPatch, proc: _Proc) -> None:
    async def _factory(*_a: Any, **_kw: Any) -> _Proc:
        return proc

    monkeypatch.setattr(mk.asyncio, "create_subprocess_exec", _factory)


async def test_run_info_completes_without_killing_a_process_that_exits_on_its_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proc = _Proc(_Lines([b'CINFO:1,0,"DVD"\n']), _Lines([b"warn\n"]), returncode=0)
    _spawn(monkeypatch, proc)

    run = await _run_info("/dev/sr0")

    assert (run.returncode, proc.kills) == (0, 0)
    assert run.watch.stdout == ['CINFO:1,0,"DVD"']
    assert list(run.watch.tail) == ['CINFO:1,0,"DVD"', "warn"]


async def test_run_info_binary_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _boom(*_a: Any, **_kw: Any) -> None:
        raise FileNotFoundError("makemkvcon")

    monkeypatch.setattr(mk.asyncio, "create_subprocess_exec", _boom)

    with pytest.raises(mk.ScanError, match="not found"):
        await _run_info("/dev/sr0")


async def test_run_info_kills_on_idle_timeout_using_the_injected_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    proc = _Proc(_Hang(), _Hang())
    _spawn(monkeypatch, proc)
    clock = _FakeClock()
    calls = iter([0.0, 0.0, 10_000.0])  # started_at, last_line_at, then far past the idle window

    run = await _run_info("/dev/sr0", lambda: next(calls, clock()))

    assert run.watch.timed_out is True
    assert (proc.killed, run.returncode) == (True, -9)


async def test_run_info_kills_on_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    proc = _Proc(_Hang(), _Hang())
    _spawn(monkeypatch, proc)

    task = asyncio.create_task(_run_info("/dev/sr0"))
    await asyncio.sleep(0.01)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    assert proc.killed is True
    assert proc.returncode == -9


async def test_run_info_terminal_tcount_zero_kills_after_the_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mk, "SCAN_TERMINAL_GRACE_SECONDS", 0.05)
    proc = _Proc(_Lines([b"TCOUNT:0\n", b'CINFO:1,6206,"Blu-ray disc"\n']), _Hang())
    _spawn(monkeypatch, proc)

    run = await _run_info("/dev/sr0")

    assert proc.killed is True
    assert run.watch.stdout == ["TCOUNT:0", 'CINFO:1,6206,"Blu-ray disc"']
    assert run.watch.timed_out is False


async def test_run_info_ignores_a_process_that_is_already_gone_when_killed(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Gone(_Proc):
        def kill(self) -> None:
            raise ProcessLookupError

    proc = _Gone(_Lines([b"MSG:5021,1\n"]), _Hang())
    _spawn(monkeypatch, proc)

    run = await _run_info("/dev/sr0")

    assert run.watch.expired is True


# ---- scan_disc end to end on the key-unknown fixture ----------------------------------------


async def _no_probe(_device: str, *, bluray: bool) -> DiscProbe:
    return DiscProbe(crc64=None)


def _fixture_lines(name: str) -> list[bytes]:
    return (FIXTURES / name).read_bytes().splitlines(keepends=True)


@pytest.mark.parametrize("returncode", [0, 1])
async def test_scan_disc_key_unknown_raises_with_reason_and_tail(
    monkeypatch: pytest.MonkeyPatch, returncode: int
) -> None:
    monkeypatch.setattr(mk, "probe_disc", _no_probe)
    _spawn(monkeypatch, _Proc(_Lines(_fixture_lines("makemkvcon_uhd_key_unknown.txt")), returncode=returncode))

    with pytest.raises(MakemkvScanFailed) as excinfo:
        await scan_disc("/dev/sr0")

    assert excinfo.value.reason is ScanFailureReason.VOLUME_KEY_UNKNOWN
    assert excinfo.value.tail[-1] == "TCOUNT:0"
    assert all(not line.startswith("PRG") for line in excinfo.value.tail)
    assert len(excinfo.value.tail) == 4


async def test_scan_disc_tcount_zero_without_a_reason_is_the_empty_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mk, "probe_disc", _no_probe)
    _spawn(monkeypatch, _Proc(_Lines([b"TCOUNT:0\n", b'CINFO:1,6206,"DVD disc"\n'])))

    result = await scan_disc("/dev/sr0")

    assert result.titles == []


async def test_scan_disc_ignores_progress_lines_in_a_good_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mk, "probe_disc", _no_probe)
    lines = [b"PRGV:1,2,3\n", b'CINFO:2,0,"LBL"\n', b"PRGV:2,2,3\n", b'TINFO:0,9,0,"1:00:00"\n']
    _spawn(monkeypatch, _Proc(_Lines(lines)))

    result = await scan_disc("/dev/sr0")

    assert (result.volume_label, len(result.titles)) == ("LBL", 1)
