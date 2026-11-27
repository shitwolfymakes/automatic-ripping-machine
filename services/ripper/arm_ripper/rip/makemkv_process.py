"""Runs one makemkvcon invocation.

Spawn it, stream its output, wait with a timeout or a stop signal, and map the exit to an error.
"""

import asyncio
import contextlib
import enum
import logging
import time
from typing import Any

from arm_ripper.rip.makemkv_settle import (
    COMPLETION_GRACE_SECONDS,
    SETTLE_POLL_SECONDS,
    TERMINATE_WAIT_SECONDS,
    RunWatch,
    run_is_settled,
)
from arm_ripper.rip.makemkv_stream import ParserState, RipCallbacks, stream_output
from arm_ripper.rip.subprocess_cleanup import kill_if_running

logger = logging.getLogger("arm_ripper.rip.makemkv")

RIP_TIMEOUT_SECONDS = 6 * 60 * 60  # 6 hours: worst-case BD
# The error a rip reports when its caller set `stop` (the drive dropped off the
# bus mid-rip, arm_ripper.job_controller): makemkvcon was killed, not failed.
STOPPED_ERROR = "makemkvcon stopped: the drive disconnected"

_NO_CALLBACKS = RipCallbacks()


def compose_error(prefix: str, diagnostics: list[str]) -> str:
    """Stitch the diagnostic MakeMKV messages onto the failure summary so
    the dispatcher can surface the actual cause (e.g. "Error while reading
    input", "Failed to save title 2 to file ...") instead of just the
    generic exit-code wrapper."""
    if not diagnostics:
        return prefix
    seen: list[str] = []
    for d in diagnostics:
        if not seen or seen[-1] != d:
            seen.append(d)
    return f"{prefix}: {'; '.join(seen)}"


class _Ending(enum.Enum):
    """How the wait for a makemkvcon run ended."""

    EXITED = "exited"
    STOPPED = "stopped"
    SETTLED = "settled"


async def _wait_until_settled(proc: asyncio.subprocess.Process, state: ParserState, watch: RunWatch) -> None:
    """Return once the run has said it is complete, its output has been quiet for the grace period and its files are
    provably closed. A run that reported a failed title never settles: it is left to exit."""
    await state.completed.wait()
    if state.copy_complete is not None and state.copy_complete.failed:
        await asyncio.Event().wait()
    saved = state.copy_complete.saved if state.copy_complete is not None else None
    while True:
        assert state.last_line_at is not None  # `completed` is only set by a line
        quiet_for = state.clock() - state.last_line_at
        if quiet_for < COMPLETION_GRACE_SECONDS:
            await asyncio.sleep(COMPLETION_GRACE_SECONDS - quiet_for)
        elif await run_is_settled(watch, proc.pid, saved):
            return
        else:
            await asyncio.sleep(SETTLE_POLL_SECONDS)


async def _wait_for_exit(
    proc: asyncio.subprocess.Process,
    stop: asyncio.Event | None,
    settled: asyncio.Future[None] | None = None,
) -> _Ending:
    """Wait for makemkvcon to exit, for `stop` to be set, or for `settled` to finish; says which came first.

    An exit wins over `stop`, and `stop` over `settled`, when more than one is already true.
    Raises asyncio.TimeoutError when none happens within RIP_TIMEOUT_SECONDS.
    """
    waits: dict[asyncio.Future[Any], _Ending] = {asyncio.ensure_future(proc.wait()): _Ending.EXITED}
    if stop is not None:
        waits[asyncio.ensure_future(stop.wait())] = _Ending.STOPPED
    if settled is not None:
        waits[settled] = _Ending.SETTLED
    try:
        done, _ = await asyncio.wait(waits, timeout=RIP_TIMEOUT_SECONDS, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in waits:
            task.cancel()
    if not done:
        raise asyncio.TimeoutError
    endings = {waits[task] for task in done}
    return next(e for e in (_Ending.EXITED, _Ending.STOPPED, _Ending.SETTLED) if e in endings)


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    """SIGTERM makemkvcon and give it TERMINATE_WAIT_SECONDS to go; the caller's cleanup sends SIGKILL to a run that
    stays."""
    if proc.returncode is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        proc.terminate()
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(proc.wait(), timeout=TERMINATE_WAIT_SECONDS)


def _offset(at: float | None, start: float) -> str:
    return "n/a" if at is None else f"{at - start:+.1f}s"


def _log_run_end(
    state: ParserState,
    watch: RunWatch | None,
    start: float,
    wall_start: float,
    ended_at: float,
    ended_on_completion: bool,
) -> None:
    """One INFO line per run: when MakeMKV said it was complete, when its output last changed and when the run ended,
    all from the run's start. It is logged with the toggle on or off, so a run answers whether its tail is silent."""
    last_write = None
    if watch is not None:
        with contextlib.suppress(OSError):
            last_write = max((p.stat().st_mtime for p in watch.outputs()), default=None)
    logger.info(
        "makemkvcon run end: policy=%s ended_on_completion=%s completion_msg_at=%s save_full_at=%s "
        "last_stdout_at=%s last_file_write_at=%s ended_at=%s",
        "on" if watch is not None and watch.end_on_completion else "off",
        ended_on_completion,
        _offset(state.copy_complete_at, start),
        _offset(state.save_full_at, start),
        _offset(state.last_line_at, start),
        "n/a" if last_write is None else f"{last_write - wall_start:+.1f}s",
        _offset(ended_at, start),
    )


async def _exit_error(proc: asyncio.subprocess.Process, state: ParserState, *, ended_early: bool = False) -> str | None:
    """The error text for a makemkvcon run that wasn't stopped: the expired-binary refusal, or the end of stderr on a
    non-zero exit; None for a clean exit, and for a run we ended ourselves once it was complete, whose signal exit is no
    failure.
    """
    if state.binary_expired:
        return compose_error(
            "makemkvcon refused: binary is past its hard-coded expiry "
            "(MSG:5021). MakeMKV beta binaries carry a 60-day kill-switch; "
            "rebuild the ripper image after upstream ships a fresher tarball. "
            "See docs/user/MakeMKV-Ripper.md § Failure modes.",
            state.diagnostics,
        )
    if proc.returncode != 0 and not ended_early:
        stderr = b""
        if proc.stderr is not None:
            stderr = await proc.stderr.read()
        msg = stderr.decode(errors="replace").strip()[-400:] or f"exit={proc.returncode}"
        return compose_error(f"makemkvcon failed: {msg}", state.diagnostics)
    return None


async def run_makemkvcon(
    cmd: list[str],
    state: ParserState,
    *,
    callbacks: RipCallbacks = _NO_CALLBACKS,
    eligible_source_indexes: list[int] | None = None,
    gate_disc_progress: bool = True,
    stop: asyncio.Event | None = None,
    watch: RunWatch | None = None,
) -> str | None:
    """Run one makemkvcon invocation to completion, streaming its robot output
    into `state`. Returns None on a clean exit, else the error text: not on
    PATH, timed out, the expired-binary kill switch, a non-zero exit, or
    STOPPED_ERROR once `stop` is set (the process is killed at once rather
    than left to fail every remaining title against a dead device node).

    `watch` names the output the run should leave. When it allows ending on completion, a run that has said it is
    complete (MSG:5036/5037, or the save reaching 100 %), whose output is quiet and whose files are provably closed, is
    ended without waiting for it to exit, and that is no failure. Logs one INFO line about when the run completed.
    Cancel-safe: a cancelled caller kills the subprocess before unwinding."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        return f"makemkvcon not on PATH: {e}"
    start, wall_start = state.clock(), time.time()

    streamer = asyncio.create_task(
        stream_output(
            proc,
            state,
            callbacks,
            eligible_source_indexes=eligible_source_indexes,
            gate_disc_progress=gate_disc_progress,
        )
    )
    settled = None
    if watch is not None and watch.end_on_completion:
        settled = asyncio.ensure_future(_wait_until_settled(proc, state, watch))
    try:
        ending = await _wait_for_exit(proc, stop, settled)
        if ending is _Ending.SETTLED:
            await _terminate(proc)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        streamer.cancel()
        return compose_error(f"makemkvcon timed out after {RIP_TIMEOUT_SECONDS}s", state.diagnostics)
    finally:
        await kill_if_running(proc)
        streamer.cancel()

    # Drain the streamer so every line after EOF is processed before callers read `state`.
    try:
        await streamer
    except asyncio.CancelledError:
        pass

    ended_early = ending is _Ending.SETTLED
    _log_run_end(state, watch, start, wall_start, state.clock(), ended_early)
    if ending is _Ending.STOPPED:
        return STOPPED_ERROR

    return await _exit_error(proc, state, ended_early=ended_early)
