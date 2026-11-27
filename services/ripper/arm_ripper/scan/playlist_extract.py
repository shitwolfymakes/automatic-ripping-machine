"""Extract BDMV/PLAYLIST/*.mpls from a disc or image with a killable 7-Zip subprocess.

The disc is only ever read by a child process owned by this coroutine: on
timeout, error or cancellation the child is killed and reaped before control
returns, so nothing keeps reading the drive while makemkvcon starts. The event
loop is never blocked (asyncio subprocess, no thread). Never raises on a
failed or missing read; the outcome is a short reason string.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from arm_ripper.scan import udf_image

logger = logging.getLogger("arm_ripper.scan.playlist_extract")

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


async def extract_mpls(source: str, dest: Path, timeout: float) -> str:
    """Extract the playlists of `source` into `dest`; one of OK, TIMEOUT, UNAVAILABLE, FAILED.

    OK means the child finished (its exit status is ignored: a disc with no
    BDMV extracts nothing and `dest` stays empty).
    """
    exe = udf_image.executable()
    if exe is None:
        return UNAVAILABLE
    args = ["x", f"-o{dest}", "-y", "-bd", "--", source, "BDMV/PLAYLIST/*.mpls"]
    try:
        proc = await asyncio.create_subprocess_exec(
            exe,
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError as e:
        logger.debug("7z spawn failed for %s: %s", source, e)
        return FAILED
    try:
        await asyncio.wait_for(proc.wait(), timeout)
    except asyncio.TimeoutError:
        return TIMEOUT
    finally:
        await _reap(proc)
    return OK
