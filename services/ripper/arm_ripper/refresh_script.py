"""Run one of the ripper's MakeMKV refresh scripts and report how it ended.

The community keydb, SDF and key refreshers share it: each passes its script, env, timeout and
log label, and maps the ScriptRun to its own result.
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from enum import Enum


class ScriptOutcome(Enum):
    SKIPPED = "skipped"  # script not executable: nothing to run
    NOT_STARTED = "not_started"  # spawning it raised OSError
    TIMED_OUT = "timed_out"
    FAILED = "failed"  # non-zero exit
    SUCCEEDED = "succeeded"  # exit 0


@dataclass(frozen=True)
class ScriptRun:
    outcome: ScriptOutcome
    text: str = ""  # the script's stripped stdout+stderr; empty unless it exited


async def run_refresh_script(
    script_path: str, *, env: dict[str, str] | None, timeout: float, label: str, logger: logging.Logger
) -> ScriptRun:
    """Run the script and log how it ended under `label` on the caller's logger. Never raises."""
    if not os.access(script_path, os.X_OK):
        logger.debug("%s skipped: %s not executable", label, script_path)
        return ScriptRun(ScriptOutcome.SKIPPED)

    try:
        proc = await asyncio.create_subprocess_exec(
            script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
    except OSError as exc:
        logger.warning("%s could not start (%s): %s", label, script_path, exc)
        return ScriptRun(ScriptOutcome.NOT_STARTED)

    try:
        stdout_b, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        logger.warning("%s timed out after %.0fs", label, timeout)
        return ScriptRun(ScriptOutcome.TIMED_OUT)

    text = stdout_b.decode(errors="replace").strip()
    if proc.returncode != 0:
        logger.warning("%s exited %s: %s", label, proc.returncode, text or "<no output>")
        return ScriptRun(ScriptOutcome.FAILED, text)

    if text:
        logger.info("%s: %s", label, text.replace("\n", " | "))
    return ScriptRun(ScriptOutcome.SUCCEEDED, text)
