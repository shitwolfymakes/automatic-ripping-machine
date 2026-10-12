"""Run a bash hook script as a subprocess.

Port of upstream ARM v2's ``BASH_SCRIPT`` hook: the script gets the rendered
title as ``$1`` and body as ``$2``. v3 adds ``ARM_*`` env vars, declared
inputs as plain env vars, a timeout, and captured stdout/stderr so a failing
hook is visible in the UI. The backend's own environment is never inherited.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import time
from pathlib import Path

from arm_backend.notifications.script_meta import RESERVED_INPUT_KEYS
from arm_common.schemas import BashRunResult

OUTPUT_CAP = 4096
ERROR_TAIL = 200
# How long to keep reading the pipes once bash has exited (or been killed).
PIPE_GRACE_SECONDS = 1.0
_EXIT_POLL_SECONDS = 0.05
_PASSTHROUGH_ENV = ("PATH", "HOME", "LANG", "LC_ALL")
_DEFAULT_PATH = "/usr/local/bin:/usr/bin:/bin"


def build_env(
    context: dict[str, str],
    *,
    title: str,
    body: str,
    inputs: dict[str, str],
    media_root: str,
    raw_root: str,
) -> dict[str, str]:
    # Inputs go in first so the passthrough and ARM_* values below always win:
    # a declared input can never steer the shell, the loader, or the context.
    env: dict[str, str] = {k: v for k, v in inputs.items() if k not in RESERVED_INPUT_KEYS}
    env.update({k: os.environ[k] for k in _PASSTHROUGH_ENV if k in os.environ})
    env.setdefault("PATH", _DEFAULT_PATH)
    for key, value in context.items():
        env[f"ARM_{key.upper()}"] = value
    env["ARM_TITLE"] = title
    env["ARM_BODY"] = body
    env["ARM_MEDIA_ROOT"] = media_root
    env["ARM_RAW_ROOT"] = raw_root
    return env


def _text(raw: bytes | bytearray) -> str:
    return raw.decode("utf-8", "replace")[:OUTPUT_CAP]


async def _drain(stream: asyncio.StreamReader | None, into: bytearray) -> None:
    # Keep reading past the cap so a chatty script never blocks on a full pipe.
    # 4 bytes per char covers the decoded OUTPUT_CAP.
    if stream is None:
        return
    while chunk := await stream.read(65536):
        into.extend(chunk[: max(0, OUTPUT_CAP * 4 - len(into))])


async def _wait_exit(proc: asyncio.subprocess.Process, deadline: float) -> int | None:
    # Not proc.wait(): asyncio holds that until the pipes close too, which a
    # backgrounded child can keep open long after bash itself exits.
    while proc.returncode is None:
        if time.monotonic() >= deadline:
            return None
        await asyncio.sleep(_EXIT_POLL_SECONDS)
    return proc.returncode


def _kill_group(proc: asyncio.subprocess.Process) -> None:
    # The group id is bash's pid (start_new_session); a group that already
    # emptied out is fine.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)


async def run_script(path: Path, *, title: str, body: str, env: dict[str, str], timeout_seconds: int) -> BashRunResult:
    if not path.is_file():
        return BashRunResult(
            ok=False, exit_code=None, duration_ms=0, stdout="", stderr="", error=f"script not found: {path.name}"
        )
    if not os.access(path, os.X_OK):
        return BashRunResult(
            ok=False,
            exit_code=None,
            duration_ms=0,
            stdout="",
            stderr="",
            error=f"script not executable: {path.name} (chmod +x it on the host)",
        )
    started = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        "/usr/bin/env",
        "bash",
        str(path),
        title,
        body,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        # Its own process group, so a timeout reaches whatever bash is
        # waiting on (curl, sleep, an SMTP client), not just bash.
        start_new_session=True,
    )
    out, err = bytearray(), bytearray()
    readers = [asyncio.ensure_future(_drain(proc.stdout, out)), asyncio.ensure_future(_drain(proc.stderr, err))]
    try:
        returncode = await _wait_exit(proc, started + timeout_seconds)
        if returncode is None:
            _kill_group(proc)
            await asyncio.wait(readers, timeout=PIPE_GRACE_SECONDS)
            return BashRunResult(
                ok=False,
                exit_code=None,
                duration_ms=int((time.monotonic() - started) * 1000),
                stdout="",
                stderr="",
                error=f"script timed out after {timeout_seconds}s: {path.name}",
            )
        # The script is done once bash exits. A background child (`long-task &`)
        # may still hold the pipes; take what arrived within the grace and go.
        await asyncio.wait(readers, timeout=PIPE_GRACE_SECONDS)
    finally:
        for reader in readers:
            reader.cancel()
    duration_ms = int((time.monotonic() - started) * 1000)
    stdout, stderr = _text(out), _text(err)
    if returncode == 0:
        return BashRunResult(ok=True, exit_code=0, duration_ms=duration_ms, stdout=stdout, stderr=stderr, error=None)
    tail = stderr.strip()[:ERROR_TAIL]
    return BashRunResult(
        ok=False,
        exit_code=returncode,
        duration_ms=duration_ms,
        stdout=stdout,
        stderr=stderr,
        error=f"script exit code {returncode}: {tail}",
    )
