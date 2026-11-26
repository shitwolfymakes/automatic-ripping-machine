"""rip_data: dd invocation per source kind, byte progress, failure paths."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from arm_ripper.rip import data_rip, subprocess_cleanup


class _FakeProc:
    """Stands in for dd: writes the output file in steps while "running"."""

    def __init__(self, out: Path, chunks: list[bytes], returncode: int = 0) -> None:
        self._out = out
        self._chunks = chunks
        self._rc = returncode
        self.returncode: int | None = None
        self.stderr = None

    async def wait(self) -> int:
        with self._out.open("ab") as fh:
            for chunk in self._chunks:
                fh.write(chunk)
                fh.flush()
                await asyncio.sleep(0.02)
        self.returncode = self._rc
        return self._rc

    def kill(self) -> None:
        self.returncode = -9


def _patch_dd(monkeypatch: pytest.MonkeyPatch, chunks: list[bytes], calls: list[list[str]], rc: int = 0) -> None:
    async def fake_exec(*cmd: str, **_kw: object) -> _FakeProc:
        calls.append(list(cmd))
        out = Path(next(a for a in cmd if a.startswith("of="))[3:])
        return _FakeProc(out, chunks, rc)

    async def fake_sha(_p: Path) -> str:
        return "sha"

    monkeypatch.setattr(data_rip.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(data_rip, "sha256_file", fake_sha)
    monkeypatch.setattr(data_rip, "PROGRESS_INTERVAL_SECONDS", 0.01)


async def test_iso_copy_uses_big_blocks_and_reports_bytes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    src = tmp_path / "movie.iso"
    src.write_bytes(b"x" * 3000)
    calls: list[list[str]] = []
    _patch_dd(monkeypatch, [b"x" * 1000, b"x" * 1000, b"x" * 1000], calls)
    seen: list[tuple[int, int | None]] = []

    async def on_progress(done: int, total: int | None) -> None:
        seen.append((done, total))

    result = await data_rip.rip_data(str(src), tmp_path / "out", on_progress=on_progress)
    assert result.ok and result.size_bytes == 3000
    assert "bs=4M" in calls[0] and not any(a.startswith("conv=") for a in calls[0])
    assert seen[-1] == (3000, 3000)
    assert all(total == 3000 for _done, total in seen)
    assert [done for done, _t in seen] == sorted(done for done, _t in seen)


async def test_device_keeps_sector_blocks_with_noerror(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    _patch_dd(monkeypatch, [b"y" * 2048], calls)
    monkeypatch.setattr(data_rip, "source_size", lambda _p: None)
    result = await data_rip.rip_data("/dev/sr0", tmp_path / "out")
    assert result.ok
    assert "bs=2048" in calls[0] and "conv=noerror,sync" in calls[0]


async def test_progress_callback_errors_never_fail_the_copy(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    src = tmp_path / "movie.iso"
    src.write_bytes(b"x" * 10)
    _patch_dd(monkeypatch, [b"x" * 5, b"x" * 5], [])

    async def boom(_done: int, _total: int | None) -> None:
        raise RuntimeError("ws down")

    result = await data_rip.rip_data(str(src), tmp_path / "out", on_progress=boom)
    assert result.ok


async def test_dd_failure_is_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    src = tmp_path / "movie.iso"
    src.write_bytes(b"x")
    _patch_dd(monkeypatch, [], [], rc=1)
    result = await data_rip.rip_data(str(src), tmp_path / "out")
    assert not result.ok and "dd failed" in (result.error or "")


def test_source_size(tmp_path: Path) -> None:
    f = tmp_path / "a.iso"
    f.write_bytes(b"x" * 42)
    assert data_rip.source_size(str(f)) == 42
    assert data_rip.source_size(str(tmp_path / "missing.iso")) is None


async def test_dd_failure_keeps_the_stderr_tail(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The decisive dd line comes last; a long stderr must keep its end, not its start."""
    src = tmp_path / "movie.iso"
    src.write_bytes(b"x")
    _patch_dd(monkeypatch, [], [], rc=1)
    real_init = _FakeProc.__init__

    def init_with_stderr(self: _FakeProc, *a: object, **kw: object) -> None:
        real_init(self, *a, **kw)  # type: ignore[arg-type]
        reader = asyncio.StreamReader()
        reader.feed_data(("noise " * 200 + "dd: error reading '/dev/sr0': Input/output error").encode())
        reader.feed_eof()
        self.stderr = reader  # type: ignore[assignment]

    monkeypatch.setattr(_FakeProc, "__init__", init_with_stderr)
    result = await data_rip.rip_data(str(src), tmp_path / "out")
    assert not result.ok
    assert (result.error or "").endswith("Input/output error")


class _HangProc:
    """dd that never finishes by itself: wait() blocks until kill() is called."""

    def __init__(self, out: Path, reap_error: Exception | None = None) -> None:
        out.touch()
        self._reap_error = reap_error
        self._killed = asyncio.Event()
        self.returncode: int | None = None
        self.stderr = None
        self.kills = 0
        self.reaped = False

    async def wait(self) -> int:
        if self.kills and self._reap_error is not None:
            raise self._reap_error
        await self._killed.wait()
        self.reaped = True
        return -9

    def kill(self) -> None:
        self.kills += 1
        self.returncode = -9
        self._killed.set()


def _patch_hang(monkeypatch: pytest.MonkeyPatch, procs: list[_HangProc], reap_error: Exception | None = None) -> None:
    async def fake_exec(*cmd: str, **_kw: object) -> _HangProc:
        proc = _HangProc(Path(next(a for a in cmd if a.startswith("of="))[3:]), reap_error)
        procs.append(proc)
        return proc

    monkeypatch.setattr(data_rip.asyncio, "create_subprocess_exec", fake_exec)
    monkeypatch.setattr(data_rip, "PROGRESS_INTERVAL_SECONDS", 0.01)


async def test_dd_missing_from_path_is_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    async def fake_exec(*_cmd: str, **_kw: object) -> _FakeProc:
        raise FileNotFoundError("dd")

    monkeypatch.setattr(data_rip.asyncio, "create_subprocess_exec", fake_exec)
    result = await data_rip.rip_data("/dev/sr0", tmp_path / "out")
    assert not result.ok
    assert result.error == "dd not on PATH: dd"


async def test_timeout_kills_dd_and_stops_progress(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    procs: list[_HangProc] = []
    _patch_hang(monkeypatch, procs)
    monkeypatch.setattr(data_rip, "DATA_RIP_TIMEOUT_SECONDS", 0.05)
    seen: list[int] = []

    async def on_progress(done: int, _total: int | None) -> None:
        seen.append(done)

    result = await data_rip.rip_data("/dev/sr0", tmp_path / "out", on_progress=on_progress)
    assert not result.ok
    assert result.error == "dd timed out after 0.05s"
    assert procs[0].kills == 1 and procs[0].reaped
    assert seen
    count = len(seen)
    await asyncio.sleep(0.05)
    assert len(seen) == count


async def _cancel_mid_copy(tmp_path: Path) -> None:
    task = asyncio.create_task(data_rip.rip_data("/dev/sr0", tmp_path / "out"))
    await asyncio.sleep(0.03)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_cancel_mid_copy_kills_dd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    procs: list[_HangProc] = []
    _patch_hang(monkeypatch, procs)
    await _cancel_mid_copy(tmp_path)
    assert procs[0].kills == 1 and procs[0].reaped


async def test_cancel_mid_copy_swallows_a_failing_reap(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    procs: list[_HangProc] = []
    _patch_hang(monkeypatch, procs, reap_error=RuntimeError("reap failed"))
    await _cancel_mid_copy(tmp_path)
    assert procs[0].kills == 1 and not procs[0].reaped


async def test_empty_output_file_is_an_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_dd(monkeypatch, [b""], [])
    result = await data_rip.rip_data("/dev/sr0", tmp_path / "out")
    assert not result.ok
    assert result.error == "dd exited 0 but produced empty output"


async def test_missing_output_file_is_an_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _patch_dd(monkeypatch, [], [])
    result = await data_rip.rip_data("/dev/sr0", tmp_path / "out")
    assert not result.ok
    assert result.error == "dd exited 0 but produced empty output"


def test_dd_command_image_uses_4m_blocks(tmp_path: Path) -> None:
    image = tmp_path / "disc.iso"
    image.write_bytes(b"")
    out = tmp_path / "dump.iso"
    assert data_rip._dd_command(str(image), out) == ["dd", f"if={image}", f"of={out}", "bs=4M"]


def test_dd_command_device_uses_2k_blocks_with_noerror_sync(tmp_path: Path) -> None:
    out = tmp_path / "dump.iso"
    assert data_rip._dd_command("/dev/sr0", out) == [
        "dd",
        "if=/dev/sr0",
        f"of={out}",
        "bs=2048",
        "conv=noerror,sync",
    ]


async def test_stop_reporter_without_reporter_returns() -> None:
    await data_rip._stop_reporter(None)


async def test_stop_reporter_cancels_running_task() -> None:
    task = asyncio.create_task(asyncio.sleep(60))
    await asyncio.sleep(0)
    await data_rip._stop_reporter(task)
    assert task.cancelled()


async def test_stop_reporter_accepts_finished_task() -> None:
    task = asyncio.create_task(asyncio.sleep(0))
    await task
    await data_rip._stop_reporter(task)
    assert task.done() and not task.cancelled()


async def test_kill_if_running_leaves_finished_proc_alone(tmp_path: Path) -> None:
    proc = _HangProc(tmp_path / "o")
    proc.returncode = 0
    await subprocess_cleanup.kill_if_running(proc)  # type: ignore[arg-type]
    assert proc.kills == 0


async def test_kill_if_running_kills_and_reaps(tmp_path: Path) -> None:
    proc = _HangProc(tmp_path / "o")
    await subprocess_cleanup.kill_if_running(proc)  # type: ignore[arg-type]
    assert proc.kills == 1 and proc.reaped


async def test_kill_if_running_swallows_reap_error(tmp_path: Path) -> None:
    proc = _HangProc(tmp_path / "o", reap_error=RuntimeError("boom"))
    await subprocess_cleanup.kill_if_running(proc)  # type: ignore[arg-type]
    assert proc.kills == 1 and not proc.reaped


async def test_wait_for_dd_exit_in_time_returns_none_and_stops_reporter(tmp_path: Path) -> None:
    proc = _FakeProc(tmp_path / "o", [b"x"])
    reporter = asyncio.create_task(asyncio.sleep(60))
    assert await data_rip._wait_for_dd(proc, reporter) is None  # type: ignore[arg-type]
    assert reporter.cancelled()


async def test_wait_for_dd_without_reporter(tmp_path: Path) -> None:
    proc = _FakeProc(tmp_path / "o", [b"x"])
    assert await data_rip._wait_for_dd(proc, None) is None  # type: ignore[arg-type]


async def test_wait_for_dd_timeout_returns_failure_and_kills_once(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(data_rip, "DATA_RIP_TIMEOUT_SECONDS", 0.05)
    proc = _HangProc(tmp_path / "o")
    reporter = asyncio.create_task(asyncio.sleep(60))
    result = await data_rip._wait_for_dd(proc, reporter)  # type: ignore[arg-type]
    assert result is not None
    assert not result.ok
    assert result.error == "dd timed out after 0.05s"
    assert proc.kills == 1 and proc.reaped
    assert reporter.cancelled()


async def test_wait_for_dd_cancelled_propagates_and_kills(tmp_path: Path) -> None:
    proc = _HangProc(tmp_path / "o")
    task = asyncio.create_task(data_rip._wait_for_dd(proc, None))  # type: ignore[arg-type]
    await asyncio.sleep(0.03)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert proc.kills == 1


class _StderrProc:
    """A finished dd with a canned return code and stderr."""

    def __init__(self, returncode: int, stderr: bytes | None) -> None:
        self.returncode = returncode
        self.stderr = _Reader(stderr) if stderr is not None else None


class _Reader:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self.reads = 0

    async def read(self) -> bytes:
        self.reads += 1
        return self._data


async def test_dd_failure_exit_zero_is_none_and_skips_stderr() -> None:
    proc = _StderrProc(0, b"noise")
    assert await data_rip._dd_failure(proc) is None  # type: ignore[arg-type]
    assert proc.stderr is not None and proc.stderr.reads == 0


async def test_dd_failure_keeps_last_400_stripped_chars() -> None:
    proc = _StderrProc(1, b"A" * 500 + b"B" * 399 + b"  \n")
    result = await data_rip._dd_failure(proc)  # type: ignore[arg-type]
    assert result is not None and not result.ok
    assert result.error == "dd failed: " + "A" * 1 + "B" * 399


async def test_dd_failure_without_stderr_reports_exit_code() -> None:
    result = await data_rip._dd_failure(_StderrProc(3, None))  # type: ignore[arg-type]
    assert result is not None and result.error == "dd failed: exit=3"


@pytest.mark.parametrize("stderr", [b"", b"  \n\t "])
async def test_dd_failure_blank_stderr_reports_exit_code(stderr: bytes) -> None:
    result = await data_rip._dd_failure(_StderrProc(2, stderr))  # type: ignore[arg-type]
    assert result is not None and result.error == "dd failed: exit=2"


def test_empty_output_failure_missing_file(tmp_path: Path) -> None:
    result = data_rip._empty_output_failure(tmp_path / "missing.iso")
    assert result is not None and not result.ok
    assert result.error == "dd exited 0 but produced empty output"


def test_empty_output_failure_empty_file(tmp_path: Path) -> None:
    out = tmp_path / "dump.iso"
    out.touch()
    result = data_rip._empty_output_failure(out)
    assert result is not None and not result.ok
    assert result.error == "dd exited 0 but produced empty output"


def test_empty_output_failure_file_with_bytes_is_none(tmp_path: Path) -> None:
    out = tmp_path / "dump.iso"
    out.write_bytes(b"x")
    assert data_rip._empty_output_failure(out) is None
