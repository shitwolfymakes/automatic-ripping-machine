"""Per-rip community-keydb (FindVUK) refresh.

Sibling of `makemkv_key.py`. The JobController spawns this as a fire-and-forget
background task before each rip; the rip proceeds immediately with whatever
keydb is already on disk, and a fresh keydb benefits the next rip.

The heavy lifting lives in `update_keydb.sh`: it gates on ARM_COMMUNITY_KEYDB,
skips if the on-disk keydb is fresh, otherwise downloads the FindVUK ZIP,
filters to VUK (| V |) entries, and atomically installs ~/.MakeMKV/keydb.cfg.
The script's final `keydb-status: <state> [vuk=<n>] [age_days=<n>]` line is the
contract we parse here.

Non-fatal by design: a dead keydb surfaces downstream as a distinct makemkvcon
decrypt error, not a pipeline abort.
"""

import logging
import os
import re
from dataclasses import dataclass

from arm_common import KeydbState

from arm_ripper.refresh_script import ScriptOutcome, int_field, last_status, run_refresh_script

logger = logging.getLogger("arm_ripper.community_keydb")

UPDATE_KEYDB_SCRIPT = "/usr/local/bin/update_keydb.sh"
# Covers update_keydb.sh's CURL_MAX_TIME (600s) plus retry/backoff headroom.
# Harmless to be generous — the wrapper runs as a background task off the rip path.
REFRESH_TIMEOUT_SECONDS = 660.0

# The status line is `keydb-status: <state> [vuk=<n>] [age_days=<n>]`. State is
# matched anchored to the marker; vuk= / age_days= are looked up independently so
# their order on the line never matters (a single combined regex would silently
# drop the second field if the script ever emitted them reversed).
_STATE_RE = re.compile(r"keydb-status:\s*(?P<state>\S+)")
_VUK_RE = re.compile(r"\bvuk=(?P<vuk>\d+)")
_AGE_RE = re.compile(r"\bage_days=(?P<age>\d+)")


@dataclass(frozen=True)
class KeydbResult:
    state: KeydbState
    vuk_count: int | None = None
    age_days: int | None = None


def _parse(text: str) -> KeydbResult:
    """Parse the last `keydb-status:` line. Unknown/absent → PROBE_FAILED."""
    found = last_status(text, _STATE_RE, KeydbState)
    if found is None:
        return KeydbResult(state=KeydbState.PROBE_FAILED)
    state, last = found
    return KeydbResult(state=state, vuk_count=int_field(_VUK_RE, last), age_days=int_field(_AGE_RE, last))


async def refresh_community_keydb(script_path: str = UPDATE_KEYDB_SCRIPT, enabled: bool = True) -> KeydbResult | None:
    """Run update_keydb.sh and parse its status line. Never raises.

    Returns None when there is nothing to run (script not executable — a
    non-makemkv image or unit-test host). Otherwise returns a KeydbResult;
    PROBE_FAILED when the script can't run cleanly or its output can't be parsed.
    """
    env = {**os.environ, "ARM_COMMUNITY_KEYDB": "true" if enabled else "false"}

    run = await run_refresh_script(
        script_path, env=env, timeout=REFRESH_TIMEOUT_SECONDS, label="community keydb refresh", logger=logger
    )
    if run.outcome in (ScriptOutcome.SKIPPED, ScriptOutcome.NOT_STARTED):
        return None
    if run.outcome is not ScriptOutcome.SUCCEEDED:
        return KeydbResult(state=KeydbState.PROBE_FAILED)
    return _parse(run.text)
