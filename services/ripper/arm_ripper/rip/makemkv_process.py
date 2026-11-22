"""Runs one makemkvcon invocation.

Spawn it, stream its output, wait with a timeout or a stop signal, and map the exit to an error.
"""

import asyncio
import contextlib
import logging

from arm_ripper.rip.makemkv_stream import ParserState, RipCallbacks, stream_output
from arm_ripper.rip.subprocess_cleanup import kill_if_running

logger = logging.getLogger(__name__)

RIP_TIMEOUT_SECONDS = 6 * 60 * 60  # 6 hours: worst-case BD
# After a normal exit every output line is already buffered; the streamer only
# has to finish them, callbacks (backend calls) included. A callback stuck
# retrying against a dead backend is cut off after this so the rip still ends.
DRAIN_TIMEOUT_SECONDS = 30.0
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


async def _wait_for_exit(proc: asyncio.subprocess.Process, stop: asyncio.Event | None) -> bool:
    """Wait for makemkvcon to exit or for `stop` to be set; True when `stop` came first.

    Raises asyncio.TimeoutError when neither happens within RIP_TIMEOUT_SECONDS.
    """
    if stop is None:
        await asyncio.wait_for(proc.wait(), timeout=RIP_TIMEOUT_SECONDS)
        return False
    exited = asyncio.create_task(proc.wait())
    stop_seen = asyncio.create_task(stop.wait())
    try:
        done, _ = await asyncio.wait(
            {exited, stop_seen}, timeout=RIP_TIMEOUT_SECONDS, return_when=asyncio.FIRST_COMPLETED
        )
    finally:
        stop_seen.cancel()
        exited.cancel()
    if not done:
        raise asyncio.TimeoutError
    return exited not in done


async def _exit_error(proc: asyncio.subprocess.Process, state: ParserState) -> str | None:
    """The error text for a makemkvcon run that wasn't stopped: the expired-binary refusal, or the end of stderr on a
    non-zero exit; None for a clean exit.
    """
    if state.binary_expired:
        return compose_error(
            "makemkvcon refused: binary is past its hard-coded expiry "
            "(MSG:5021). MakeMKV beta binaries carry a 60-day kill-switch; "
            "rebuild the ripper image after upstream ships a fresher tarball. "
            "See docs/user/MakeMKV-Ripper.md § Failure modes.",
            state.diagnostics,
        )
    if proc.returncode != 0:
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
) -> str | None:
    """Run one makemkvcon invocation to completion, streaming its robot output
    into `state`. Returns None on a clean exit, else the error text: not on
    PATH, timed out, the expired-binary kill switch, a non-zero exit, or
    STOPPED_ERROR once `stop` is set (the process is killed at once rather
    than left to fail every remaining title against a dead device node).
    Cancel-safe: a cancelled caller kills the subprocess before unwinding."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        return f"makemkvcon not on PATH: {e}"

    streamer = asyncio.create_task(
        stream_output(
            proc,
            state,
            callbacks,
            eligible_source_indexes=eligible_source_indexes,
            gate_disc_progress=gate_disc_progress,
        )
    )
    try:
        stopped = await _wait_for_exit(proc, stop)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        await _cancel(streamer)
        return compose_error(f"makemkvcon timed out after {RIP_TIMEOUT_SECONDS}s", state.diagnostics)
    except BaseException:
        # The caller was cancelled: kill and unwind, nothing left to report.
        await kill_if_running(proc)
        streamer.cancel()
        raise

    if stopped:
        await kill_if_running(proc)
        await _cancel(streamer)
        return STOPPED_ERROR

    # A normal exit: let the streamer finish every buffered line, and any callback it is in the middle of, before
    # callers read `state`. Cancelling it here cut off a callback and lost the lines after it: the last progress,
    # the move to the next title, MakeMKV's own reason for a failure.
    try:
        await asyncio.wait_for(streamer, timeout=DRAIN_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.warning(
            "still processing makemkvcon output %gs after it exited; the remaining lines are dropped",
            DRAIN_TIMEOUT_SECONDS,
        )

    return await _exit_error(proc, state)


async def _cancel(task: asyncio.Task[None]) -> None:
    """Cancel `task` and wait for it to unwind."""
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
