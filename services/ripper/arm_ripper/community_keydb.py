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

import asyncio
import logging
import os
import re
from dataclasses import dataclass

from arm_common import KeydbState

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
    last = None
    for line in text.splitlines():
        if _STATE_RE.search(line):
            last = line
    if last is None:
        return KeydbResult(state=KeydbState.PROBE_FAILED)
    try:
        state = KeydbState(_STATE_RE.search(last).group("state"))  # type: ignore[union-attr]
    except ValueError:
        return KeydbResult(state=KeydbState.PROBE_FAILED)
    vuk = _VUK_RE.search(last)
    age = _AGE_RE.search(last)
    return KeydbResult(
        state=state,
        vuk_count=int(vuk.group("vuk")) if vuk else None,
        age_days=int(age.group("age")) if age else None,
    )


async def refresh_community_keydb(script_path: str = UPDATE_KEYDB_SCRIPT, enabled: bool = True) -> KeydbResult | None:
    """Run update_keydb.sh and parse its status line. Never raises.

    Returns None when there is nothing to run (script not executable — a
    non-makemkv image or unit-test host). Otherwise returns a KeydbResult;
    PROBE_FAILED when the script can't run cleanly or its output can't be parsed.
    """
    if not os.access(script_path, os.X_OK):
        logger.debug("community keydb refresh skipped: %s not executable", script_path)
        return None

    env = {**os.environ, "ARM_COMMUNITY_KEYDB": "true" if enabled else "false"}

    try:
        proc = await asyncio.create_subprocess_exec(
            script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
    except OSError as exc:
        logger.warning("community keydb refresh could not start (%s): %s", script_path, exc)
        return None

    try:
        stdout_b, _ = await asyncio.wait_for(proc.communicate(), timeout=REFRESH_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        logger.warning("community keydb refresh timed out after %.0fs", REFRESH_TIMEOUT_SECONDS)
        return KeydbResult(state=KeydbState.PROBE_FAILED)

    text = stdout_b.decode(errors="replace").strip()
    if proc.returncode != 0:
        logger.warning("community keydb refresh exited %s: %s", proc.returncode, text or "<no output>")
        return KeydbResult(state=KeydbState.PROBE_FAILED)

    result = _parse(text)
    if text:
        logger.info("community keydb refresh: %s", text.replace("\n", " | "))
    return result
