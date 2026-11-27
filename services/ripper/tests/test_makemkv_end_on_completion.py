"""Ending a makemkvcon run once it has said it is complete and its files are closed, against a faked makemkvcon."""

from __future__ import annotations

import asyncio
import functools
import logging
import os
from pathlib import Path
from typing import Any

import pytest

import arm_ripper.rip.makemkv_process as makemkv_process
import arm_ripper.rip.makemkv_settle as makemkv_settle
from arm_ripper.rip.makemkv_rip import rip_disc
from arm_ripper.rip.makemkv_robot import CopyComplete
from arm_ripper.rip.makemkv_stream import ParserState
from arm_ripper.rip.makemkv_settle import RunWatch

_REAL_SLEEP = asyncio.sleep
_COPY_COMPLETE = 'MSG:5036,0,1,"Copy complete. 1 titles saved.","Copy complete. %1 titles saved.","1"'
_SAVE = ['PRGT:5024,0,"Saving all titles to MKV files"', "PRGV:50,50,100"]


class _LingeringProc:
    """A makemkvcon that prints its lines, then stays alive (stdout open) until it is ended."""

    pid = 4242

    def __init__(self, lines: list[str], *, honours_term: bool = True) -> None:
        self._lines = [(line + "\n").encode() for line in lines]
        self._honours_term = honours_term
        self._exited = asyncio.Event()
        self.returncode: int | None = None
        self.terminated = 0
        self.killed = 0
        self.stdout = self
        self.stderr = self

    async def readline(self) -> bytes:
        if self._lines:
            return self._lines.pop(0)
        await self._exited.wait()
        return b""

    async def read(self) -> bytes:
        return b""

    async def wait(self) -> int:
        await self._exited.wait()
        assert self.returncode is not None
        return self.returncode

    def finish(self, code: int = 0) -> None:
        self.returncode = code
        self._exited.set()

    def terminate(self) -> None:
        self.terminated += 1
        if self._honours_term:
            self.finish(-15)

    def kill(self) -> None:
        self.killed += 1
        self.finish(-9)


@pytest.fixture
def fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shrink the grace, poll and terminate waits so a run settles in milliseconds."""
    monkeypatch.setattr(makemkv_process, "COMPLETION_GRACE_SECONDS", 0.02)
    monkeypatch.setattr(makemkv_process, "SETTLE_POLL_SECONDS", 0.01)
    monkeypatch.setattr(makemkv_process, "TERMINATE_WAIT_SECONDS", 0.02)


async def _no_sleep(_seconds: float) -> None:
    await _REAL_SLEEP(0)


def _fd_tree(tmp_path: Path, pid: int, targets: list[Path]) -> Path:
    fd_dir = tmp_path / "proc" / str(pid) / "fd"
    fd_dir.mkdir(parents=True)
    for n, target in enumerate(targets):
        os.symlink(target, fd_dir / str(n))
    return tmp_path / "proc"


def _use(monkeypatch: pytest.MonkeyPatch, proc: _LingeringProc) -> None:
    async def create(*_a: Any, **_k: Any) -> _LingeringProc:
        return proc

    monkeypatch.setattr(makemkv_process.asyncio, "create_subprocess_exec", create)


def _closed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, held: list[Path] | None = None) -> None:
    """`/proc` as the settle check sees it: the run holds `held` open."""
    proc_root = _fd_tree(tmp_path, _LingeringProc.pid, held or [])
    monkeypatch.setattr(
        makemkv_process,
        "run_is_settled",
        functools.partial(makemkv_settle.run_is_settled, proc_root=proc_root, sleep=_no_sleep),
    )


def _out(tmp_path: Path) -> Path:
    out = tmp_path / "out"
    out.mkdir()
    (out / "Movie_t00.mkv").write_bytes(b"x" * 64)
    return out


async def _rip(out: Path, *, end: bool = True, stop: asyncio.Event | None = None, eligible: list[int] | None = None):
    return await rip_disc(
        "/dev/sr0",
        out,
        eligible_source_indexes=[0] if eligible is None else eligible,
        end_on_completion=end,
        stop=stop,
    )


async def test_a_complete_silent_run_with_closed_files_is_ended_and_its_title_is_done(monkeypatch, tmp_path, fast):
    proc = _LingeringProc([*_SAVE, _COPY_COMPLETE])
    _use(monkeypatch, proc)
    _closed(monkeypatch, tmp_path)
    out = _out(tmp_path)

    result = await asyncio.wait_for(_rip(out), timeout=5)

    assert proc.terminated == 1 and proc.killed == 0
    assert result.overall_error is None  # the signal exit is not "makemkvcon failed"
    assert result.titles[0].ok is True
    assert result.titles[0].output_path == out / "Movie_t00.mkv"


async def test_the_save_reaching_100_percent_ends_the_run_without_a_completion_message(monkeypatch, tmp_path, fast):
    proc = _LingeringProc([*_SAVE, "PRGV:100,100,100"])
    _use(monkeypatch, proc)
    _closed(monkeypatch, tmp_path)

    result = await asyncio.wait_for(_rip(_out(tmp_path)), timeout=5)

    assert proc.terminated == 1
    assert result.overall_error is None and result.titles[0].ok is True


async def test_a_run_that_ignores_sigterm_is_killed_after_the_wait(monkeypatch, tmp_path, fast):
    proc = _LingeringProc([*_SAVE, _COPY_COMPLETE], honours_term=False)
    _use(monkeypatch, proc)
    _closed(monkeypatch, tmp_path)

    result = await asyncio.wait_for(_rip(_out(tmp_path)), timeout=5)

    assert proc.terminated == 1 and proc.killed == 1
    assert result.overall_error is None


async def test_a_file_still_open_means_the_run_is_left_to_exit(monkeypatch, tmp_path, fast):
    proc = _LingeringProc([*_SAVE, _COPY_COMPLETE])
    _use(monkeypatch, proc)
    out = _out(tmp_path)
    _closed(monkeypatch, tmp_path, held=[out / "Movie_t00.mkv"])

    run = asyncio.ensure_future(_rip(out))
    await _REAL_SLEEP(0.2)  # many polls later, still not ended
    assert not run.done() and proc.terminated == 0
    proc.finish(0)
    result = await asyncio.wait_for(run, timeout=5)

    assert proc.terminated == 0 and proc.killed == 0
    assert result.overall_error is None and result.titles[0].ok is True


async def test_with_the_toggle_off_the_run_is_never_ended_early(monkeypatch, tmp_path, fast):
    proc = _LingeringProc([*_SAVE, _COPY_COMPLETE])
    _use(monkeypatch, proc)
    _closed(monkeypatch, tmp_path)
    out = _out(tmp_path)

    run = asyncio.ensure_future(_rip(out, end=False))
    await _REAL_SLEEP(0.1)
    assert not run.done() and proc.terminated == 0
    proc.finish(0)
    result = await asyncio.wait_for(run, timeout=5)

    assert proc.terminated == 0
    assert result.overall_error is None and result.titles[0].ok is True


async def test_stop_during_the_grace_wins_over_ending_on_completion(monkeypatch, tmp_path, fast):
    monkeypatch.setattr(makemkv_process, "COMPLETION_GRACE_SECONDS", 5.0)
    proc = _LingeringProc([*_SAVE, _COPY_COMPLETE])
    _use(monkeypatch, proc)
    _closed(monkeypatch, tmp_path)
    stop = asyncio.Event()

    run = asyncio.ensure_future(_rip(_out(tmp_path), stop=stop))
    await _REAL_SLEEP(0.05)
    stop.set()
    result = await asyncio.wait_for(run, timeout=5)

    assert result.overall_error == makemkv_process.STOPPED_ERROR
    assert proc.terminated == 0 and proc.killed == 1


async def test_a_run_with_no_expected_titles_is_never_ended_early(monkeypatch, tmp_path, fast):
    proc = _LingeringProc([*_SAVE, _COPY_COMPLETE])
    _use(monkeypatch, proc)
    _closed(monkeypatch, tmp_path)

    run = asyncio.ensure_future(_rip(_out(tmp_path), eligible=[]))
    await _REAL_SLEEP(0.1)
    assert not run.done() and proc.terminated == 0
    proc.finish(0)
    await asyncio.wait_for(run, timeout=5)


async def test_a_run_that_reports_a_failed_title_is_left_to_exit(monkeypatch, tmp_path, fast):
    failed = 'MSG:5037,0,2,"Copy complete. 1 titles saved, 1 failed.","f","1","1"'
    proc = _LingeringProc([*_SAVE, failed])
    _use(monkeypatch, proc)
    _closed(monkeypatch, tmp_path)

    run = asyncio.ensure_future(_rip(_out(tmp_path)))
    await _REAL_SLEEP(0.1)
    assert not run.done() and proc.terminated == 0
    proc.finish(0)
    await asyncio.wait_for(run, timeout=5)


async def test_a_wrong_saved_count_is_left_to_exit(monkeypatch, tmp_path, fast):
    proc = _LingeringProc([*_SAVE, 'MSG:5036,0,1,"x","y","2"'])
    _use(monkeypatch, proc)
    _closed(monkeypatch, tmp_path)

    run = asyncio.ensure_future(_rip(_out(tmp_path)))
    await _REAL_SLEEP(0.1)
    assert not run.done() and proc.terminated == 0
    proc.finish(0)
    await asyncio.wait_for(run, timeout=5)


# --- the wait itself, on a fake clock -----------------------------------------------------------


class _World:
    """A clock the fake sleep advances, so the grace and polls cost no time."""

    def __init__(self) -> None:
        self.now = 100.0
        self.on_sleep: Any = None

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds
        if self.on_sleep is not None:
            self.on_sleep(seconds)
        await _REAL_SLEEP(0)


class _Settled:
    """A scripted run_is_settled: answers in turn, recording what it was asked."""

    def __init__(self, answers: list[bool]) -> None:
        self.answers = answers
        self.saved: list[int | None] = []

    async def __call__(self, _watch: RunWatch, pid: int, saved: int | None) -> bool:
        assert pid == _LingeringProc.pid
        self.saved.append(saved)
        return self.answers.pop(0)


def _wait_rig(monkeypatch: pytest.MonkeyPatch, answers: list[bool]) -> tuple[_World, ParserState, _Settled, RunWatch]:
    world = _World()
    monkeypatch.setattr(makemkv_process.asyncio, "sleep", world.sleep)
    settled = _Settled(answers)
    monkeypatch.setattr(makemkv_process, "run_is_settled", settled)
    state = ParserState(clock=world.clock)
    state.last_line_at = world.now
    state.completed.set()
    watch = RunWatch(output_dir=Path("/x"), outputs=lambda: [], expected_files=1, end_on_completion=True)
    return world, state, settled, watch


async def test_the_wait_ends_once_quiet_for_the_grace_and_closed(monkeypatch):
    world, state, settled, watch = _wait_rig(monkeypatch, [True])
    await makemkv_process._wait_until_settled(_LingeringProc([]), state, watch)  # type: ignore[arg-type]
    assert world.now == 100.0 + makemkv_process.COMPLETION_GRACE_SECONDS
    assert settled.saved == [None]


async def test_a_new_line_restarts_the_quiet_period(monkeypatch):
    world, state, _settled, watch = _wait_rig(monkeypatch, [True])
    seen: list[float] = []

    def line_arrives(_seconds: float) -> None:
        if not seen:
            state.last_line_at = world.now  # a line lands at the end of the first sleep
        seen.append(world.now)

    world.on_sleep = line_arrives
    await makemkv_process._wait_until_settled(_LingeringProc([]), state, watch)  # type: ignore[arg-type]
    assert world.now == 100.0 + 2 * makemkv_process.COMPLETION_GRACE_SECONDS


async def test_an_unclosed_run_is_checked_again_after_the_poll(monkeypatch):
    world, state, settled, watch = _wait_rig(monkeypatch, [False, False, True])
    await makemkv_process._wait_until_settled(_LingeringProc([]), state, watch)  # type: ignore[arg-type]
    assert world.now == 100.0 + makemkv_process.COMPLETION_GRACE_SECONDS + 2 * makemkv_process.SETTLE_POLL_SECONDS
    assert len(settled.saved) == 3


async def test_the_reported_count_is_what_the_check_is_given(monkeypatch):
    _world, state, settled, watch = _wait_rig(monkeypatch, [True])
    state.copy_complete = CopyComplete(saved=2, failed=0)
    await makemkv_process._wait_until_settled(_LingeringProc([]), state, watch)  # type: ignore[arg-type]
    assert settled.saved == [2]


async def test_a_run_with_a_failed_title_never_settles(monkeypatch):
    _world, state, settled, watch = _wait_rig(monkeypatch, [True])
    state.copy_complete = CopyComplete(saved=1, failed=1)
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(makemkv_process._wait_until_settled(_LingeringProc([]), state, watch), 0.05)  # type: ignore[arg-type]
    assert settled.saved == []


# --- the exit status and the terminate ----------------------------------------------------------


async def test_a_signal_exit_of_an_ended_run_is_not_an_error_but_the_expiry_still_is():
    proc = _LingeringProc([])
    proc.finish(-15)
    state = ParserState()
    assert await makemkv_process._exit_error(proc, state, ended_early=True) is None  # type: ignore[arg-type]
    assert "makemkvcon failed" in (await makemkv_process._exit_error(proc, state) or "")  # type: ignore[arg-type]
    state.binary_expired = True
    assert "past its hard-coded expiry" in (await makemkv_process._exit_error(proc, state, ended_early=True) or "")  # type: ignore[arg-type]


async def test_terminate_leaves_an_exited_process_alone_and_tolerates_a_vanished_one():
    done = _LingeringProc([])
    done.finish(0)
    await makemkv_process._terminate(done)  # type: ignore[arg-type]
    assert done.terminated == 0

    class _Gone(_LingeringProc):
        def terminate(self) -> None:
            self.terminated += 1
            raise ProcessLookupError

    gone = _Gone([])
    gone.finish(0)
    gone.returncode = None  # as far as the caller can tell it is still running
    gone._exited.set()
    gone.returncode = 0
    await makemkv_process._terminate(gone)  # type: ignore[arg-type]


# --- the INFO line --------------------------------------------------------------------------------


def _run_end_lines(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith("makemkvcon run end:")]


async def test_every_run_logs_when_it_completed_relative_to_its_start(monkeypatch, tmp_path, caplog, fast):
    caplog.set_level(logging.INFO, logger="arm_ripper.rip.makemkv")
    proc = _LingeringProc([*_SAVE, "PRGV:100,100,100", _COPY_COMPLETE])
    _use(monkeypatch, proc)
    _closed(monkeypatch, tmp_path)

    await asyncio.wait_for(_rip(_out(tmp_path)), timeout=5)

    (line,) = _run_end_lines(caplog)
    assert "policy=on ended_on_completion=True" in line
    for field in ("completion_msg_at=+", "save_full_at=+", "last_stdout_at=+", "last_file_write_at=", "ended_at=+"):
        assert field in line
    assert "n/a" not in line


async def test_a_run_with_the_toggle_off_still_logs_its_line(monkeypatch, tmp_path, caplog, fast):
    caplog.set_level(logging.INFO, logger="arm_ripper.rip.makemkv")
    proc = _LingeringProc([*_SAVE])
    _use(monkeypatch, proc)
    proc.finish(0)

    await _rip(_out(tmp_path), end=False)

    (line,) = _run_end_lines(caplog)
    assert "policy=off ended_on_completion=False completion_msg_at=n/a save_full_at=n/a" in line


async def test_the_line_survives_a_run_without_a_watch(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="arm_ripper.rip.makemkv")
    proc = _LingeringProc([])
    proc.finish(0)
    _use(monkeypatch, proc)

    assert await makemkv_process.run_makemkvcon(["makemkvcon"], ParserState()) is None

    (line,) = _run_end_lines(caplog)
    assert "policy=off" in line and "last_file_write_at=n/a" in line


async def test_the_line_tolerates_an_output_that_cannot_be_statted(monkeypatch, tmp_path, caplog):
    caplog.set_level(logging.INFO, logger="arm_ripper.rip.makemkv")
    proc = _LingeringProc([])
    proc.finish(0)
    _use(monkeypatch, proc)
    watch = RunWatch(output_dir=tmp_path, outputs=lambda: [tmp_path / "gone.mkv"], expected_files=1)

    assert await makemkv_process.run_makemkvcon(["makemkvcon"], ParserState(), watch=watch) is None

    (line,) = _run_end_lines(caplog)
    assert "last_file_write_at=n/a" in line
