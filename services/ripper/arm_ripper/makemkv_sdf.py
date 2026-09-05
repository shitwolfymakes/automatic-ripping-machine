"""Per-rip MakeMKV SDF (decryption data file) refresh.

Sibling of `community_keydb.py`. The JobController spawns this fire-and-forget
before each rip; the rip proceeds with whatever SDF is on disk (the baked-in
floor or a prior download) and a fresh SDF benefits the next rip.

`update_sdf.sh` gates on ARM_MAKEMKV_SDF, skips if the on-disk SDF is fresh
(age-gated via a `.sdf_refreshed` sentinel, because MakeMKV consumes sdf.bin
into _private_data.tar on launch), otherwise downloads sdf.bin (official URL
then makemkv.info mirror) and atomically installs it. Its final
`sdf-status: <state> [age_days=<n>]` line is the contract parsed here.

Non-fatal by design: a missing SDF surfaces downstream as a slow makemkvcon
scan, never a pipeline abort.
"""

import asyncio
import logging
import os
import re
from dataclasses import dataclass

from arm_common import MakemkvSdfState

logger = logging.getLogger("arm_ripper.makemkv_sdf")

UPDATE_SDF_SCRIPT = "/usr/local/bin/update_sdf.sh"
# Covers update_sdf.sh's curl budget (official + mirror, retries) plus headroom.
REFRESH_TIMEOUT_SECONDS = 300.0

_STATE_RE = re.compile(r"sdf-status:\s*(?P<state>\S+)")
_AGE_RE = re.compile(r"\bage_days=(?P<age>\d+)")


@dataclass(frozen=True)
class SdfResult:
    state: MakemkvSdfState
    age_days: int | None = None


def _parse(text: str) -> SdfResult:
    """Parse the last `sdf-status:` line. Unknown/absent → PROBE_FAILED."""
    last = None
    for line in text.splitlines():
        if _STATE_RE.search(line):
            last = line
    if last is None:
        return SdfResult(state=MakemkvSdfState.PROBE_FAILED)
    try:
        state = MakemkvSdfState(_STATE_RE.search(last).group("state"))  # type: ignore[union-attr]
    except ValueError:
        return SdfResult(state=MakemkvSdfState.PROBE_FAILED)
    age = _AGE_RE.search(last)
    return SdfResult(state=state, age_days=int(age.group("age")) if age else None)


async def refresh_makemkv_sdf(script_path: str = UPDATE_SDF_SCRIPT, enabled: bool = True) -> SdfResult | None:
    """Run update_sdf.sh and parse its status line. Never raises.

    Returns None when there is nothing to run (script not executable — a
    non-makemkv image or unit-test host). Otherwise returns an SdfResult;
    PROBE_FAILED when the script can't run cleanly or its output can't be parsed.
    """
    if not os.access(script_path, os.X_OK):
        logger.debug("SDF refresh skipped: %s not executable", script_path)
        return None

    env = {**os.environ, "ARM_MAKEMKV_SDF": "true" if enabled else "false"}

    try:
        proc = await asyncio.create_subprocess_exec(
            script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
    except OSError as exc:
        logger.warning("SDF refresh could not start (%s): %s", script_path, exc)
        return None

    try:
        stdout_b, _ = await asyncio.wait_for(proc.communicate(), timeout=REFRESH_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        logger.warning("SDF refresh timed out after %.0fs", REFRESH_TIMEOUT_SECONDS)
        return SdfResult(state=MakemkvSdfState.PROBE_FAILED)

    text = stdout_b.decode(errors="replace").strip()
    if proc.returncode != 0:
        logger.warning("SDF refresh exited %s: %s", proc.returncode, text or "<no output>")
        return SdfResult(state=MakemkvSdfState.PROBE_FAILED)

    result = _parse(text)
    if text:
        logger.info("SDF refresh: %s", text.replace("\n", " | "))
    return result
