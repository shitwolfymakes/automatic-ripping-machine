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

import logging
import os
import re
from dataclasses import dataclass

from arm_common import MakemkvSdfState

from arm_ripper.refresh_script import ScriptOutcome, int_field, last_status, run_refresh_script

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
    found = last_status(text, _STATE_RE, MakemkvSdfState)
    if found is None:
        return SdfResult(state=MakemkvSdfState.PROBE_FAILED)
    state, last = found
    return SdfResult(state=state, age_days=int_field(_AGE_RE, last))


async def refresh_makemkv_sdf(script_path: str = UPDATE_SDF_SCRIPT, enabled: bool = True) -> SdfResult | None:
    """Run update_sdf.sh and parse its status line. Never raises.

    Returns None when there is nothing to run (script not executable — a
    non-makemkv image or unit-test host). Otherwise returns an SdfResult;
    PROBE_FAILED when the script can't run cleanly or its output can't be parsed.
    """
    env = {**os.environ, "ARM_MAKEMKV_SDF": "true" if enabled else "false"}

    run = await run_refresh_script(
        script_path, env=env, timeout=REFRESH_TIMEOUT_SECONDS, label="SDF refresh", logger=logger
    )
    if run.outcome in (ScriptOutcome.SKIPPED, ScriptOutcome.NOT_STARTED):
        return None
    if run.outcome is not ScriptOutcome.SUCCEEDED:
        return SdfResult(state=MakemkvSdfState.PROBE_FAILED)
    return _parse(run.text)
