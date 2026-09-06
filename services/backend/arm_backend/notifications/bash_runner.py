"""Run a bash hook script as a subprocess.

Port of upstream ARM v2's ``BASH_SCRIPT`` hook: the script gets the rendered
title as ``$1`` and body as ``$2``. v3 adds ``ARM_*`` env vars, declared
inputs as plain env vars, a timeout, and captured stdout/stderr so a failing
hook is visible in the UI. The backend's own environment is never inherited.
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

from arm_common.schemas import BashRunResult

OUTPUT_CAP = 4096
ERROR_TAIL = 200
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
    env: dict[str, str] = {k: os.environ[k] for k in _PASSTHROUGH_ENV if k in os.environ}
    env.setdefault("PATH", _DEFAULT_PATH)
    for key, value in context.items():
        env[f"ARM_{key.upper()}"] = value
    env["ARM_TITLE"] = title
    env["ARM_BODY"] = body
    env["ARM_MEDIA_ROOT"] = media_root
    env["ARM_RAW_ROOT"] = raw_root
    env.update(inputs)
    return env


def _text(raw: bytes) -> str:
    return raw.decode("utf-8", "replace")[:OUTPUT_CAP]


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
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        return BashRunResult(
            ok=False,
            exit_code=None,
            duration_ms=int((time.monotonic() - started) * 1000),
            stdout="",
            stderr="",
            error=f"script timed out after {timeout_seconds}s: {path.name}",
        )
    duration_ms = int((time.monotonic() - started) * 1000)
    stdout, stderr = _text(out), _text(err)
    if proc.returncode == 0:
        return BashRunResult(ok=True, exit_code=0, duration_ms=duration_ms, stdout=stdout, stderr=stderr, error=None)
    tail = stderr.strip()[:ERROR_TAIL]
    return BashRunResult(
        ok=False,
        exit_code=proc.returncode,
        duration_ms=duration_ms,
        stdout=stdout,
        stderr=stderr,
        error=f"script exit code {proc.returncode}: {tail}",
    )
