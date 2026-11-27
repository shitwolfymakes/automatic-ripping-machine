"""Extract BDMV structure files from a disc or image with killable 7-Zip subprocesses.

One extraction pulls the files matching the given patterns (PLAYLIST/*.mpls,
CLIPINF/*.clpi) into a directory; one metadata listing gives the STREAM file sizes.

Each disc read is a child process owned by this coroutine: on
timeout, error or cancellation the child is killed and reaped before control
returns, so nothing keeps reading the drive while makemkvcon starts. The event
loop is never blocked (asyncio subprocess, no thread). Never raises on a
failed or missing read; the outcome is a short reason string.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from pathlib import Path

from arm_ripper.scan import udf_image

logger = logging.getLogger("arm_ripper.scan.bd_extract")

REAP_TIMEOUT_SECONDS = 10.0

OK = "ok"
TIMEOUT = "timeout"
UNAVAILABLE = "no-7z"
FAILED = "spawn-failed"


async def _reap(proc: asyncio.subprocess.Process) -> None:
    """Kill `proc` if it is still running and wait for it to exit (bounded: a drive in an I/O wedge can pin it)."""
    if proc.returncode is not None:
        return
    proc.kill()
    try:
        await asyncio.wait_for(asyncio.shield(proc.wait()), REAP_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        logger.error("7z (pid %s) did not exit within %.0fs of SIGKILL", proc.pid, REAP_TIMEOUT_SECONDS)


async def _run(args: list[str], timeout: float, *, capture: bool) -> tuple[str, bytes]:
    """Run 7-Zip with `args`; (outcome, stdout). The child is killed and reaped on timeout, error or cancellation."""
    exe = udf_image.executable()
    if exe is None:
        return UNAVAILABLE, b""
    try:
        proc = await asyncio.create_subprocess_exec(
            exe,
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE if capture else asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError as e:
        logger.debug("7z spawn failed for %s: %s", args[-2:], e)
        return FAILED, b""
    try:
        if capture:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout)
        else:
            out = b""
            await asyncio.wait_for(proc.wait(), timeout)
    except asyncio.TimeoutError:
        return TIMEOUT, b""
    finally:
        await _reap(proc)
    return OK, out


async def extract_files(source: str, dest: Path, timeout: float, patterns: Sequence[str]) -> str:
    """Extract the files of `source` matching `patterns` into `dest`; one of OK, TIMEOUT, UNAVAILABLE, FAILED.

    OK means the child finished (its exit status is ignored: a disc with no
    BDMV extracts nothing and `dest` stays empty).
    """
    outcome, _ = await _run(["x", f"-o{dest}", "-y", "-bd", "--", source, *patterns], timeout, capture=False)
    return outcome


async def list_file_sizes(source: str, timeout: float, pattern: str) -> tuple[dict[str, int], str]:
    """({lower-cased file name: size} of the files matching `pattern`, outcome); sizes only, nothing is read."""
    outcome, out = await _run(["l", "-slt", "-ba", "--", source, pattern], timeout, capture=True)
    records = udf_image.parse_listing(out.decode("utf-8", "replace")) if outcome == OK else []
    return {path.rsplit("/", 1)[-1].lower(): size for path, size in records}, outcome
