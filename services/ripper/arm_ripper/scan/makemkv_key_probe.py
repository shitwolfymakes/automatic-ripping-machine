"""Disc-free check of the configured MakeMKV key.

Runs makemkvcon against no disc and classifies its startup messages.
"""

import asyncio
import re

from arm_common import MakemkvKeyState
from arm_ripper.scan.makemkv import MAKEMKV_EXPIRED_PREFIX

_MAKEMKV_EVAL_PREFIXES = (b"MSG:5052,", b"MSG:5055,")
_MAKEMKV_SERIAL_RE = re.compile(r"^[A-Z]-.+$")
PROBE_TIMEOUT_SECONDS = 30.0
_PROBE_DETAILS: dict[MakemkvKeyState, str] = {
    MakemkvKeyState.VALID: "makemkv key accepted",
    MakemkvKeyState.BINARY_EXPIRED: (
        "makemkvcon binary expired (MSG:5021); no key overrides — rebuild the ripper image"
    ),
    MakemkvKeyState.UNREGISTERED_OR_EXPIRED: "no valid makemkv key in effect (MSG:5052/5055)",
}


def _is_malformed_key(key: str | None) -> bool:
    """A configured key that is set but isn't a MakeMKV serial; no key at all is not malformed."""
    return bool(key and key.strip() and not _MAKEMKV_SERIAL_RE.match(key.strip()))


def _probe_line_state(raw: bytes, state: MakemkvKeyState) -> MakemkvKeyState | None:
    """The key state a makemkvcon stdout line reports, or None when the line says nothing about the key."""
    if raw.startswith(MAKEMKV_EXPIRED_PREFIX):
        return MakemkvKeyState.BINARY_EXPIRED
    # BINARY_EXPIRED wins: real MakeMKV never emits both, but guard
    # the assignment so a pathological stream can't downgrade it.
    if any(raw.startswith(p) for p in _MAKEMKV_EVAL_PREFIXES) and state != MakemkvKeyState.BINARY_EXPIRED:
        return MakemkvKeyState.UNREGISTERED_OR_EXPIRED
    return None


async def _scan_probe_stdout(proc: asyncio.subprocess.Process) -> MakemkvKeyState:
    """Read the probe's stdout to EOF and return the key state it reports, killing makemkvcon on every key message."""
    assert proc.stdout is not None
    state = MakemkvKeyState.VALID
    async for raw in proc.stdout:
        line_state = _probe_line_state(raw, state)
        if line_state is not None:
            state = line_state
            proc.kill()
    return state


async def _discard_stderr(proc: asyncio.subprocess.Process) -> None:
    """Drain the probe's stderr so makemkvcon never blocks on a full pipe."""
    assert proc.stderr is not None
    async for _ in proc.stderr:
        pass


def _probe_outcome(state: MakemkvKeyState, returncode: int | None) -> tuple[MakemkvKeyState, str | None]:
    """The probe's result from the state stdout reported and makemkvcon's exit code."""
    if state == MakemkvKeyState.VALID and returncode not in (0, None):
        return MakemkvKeyState.PROBE_FAILED, f"makemkvcon exited {returncode} with no key message"
    return state, _PROBE_DETAILS.get(state)


async def probe_makemkv_key(key: str | None) -> tuple[MakemkvKeyState, str | None]:
    """Disc-free makemkv key probe. Runs `makemkvcon -r --cache=1 info disc:9999`
    (no disc, no hardware) and classifies the startup MSG codes. NEVER raises —
    every failure maps to a state."""
    if _is_malformed_key(key):
        return MakemkvKeyState.FORMAT_INVALID, "configured key is not a MakeMKV serial (expected M-…/T-…)"

    cmd = ["makemkvcon", "-r", "--cache=1", "info", "disc:9999"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
    except FileNotFoundError:
        return MakemkvKeyState.PROBE_FAILED, "makemkvcon binary not found on PATH"
    except OSError as exc:
        return MakemkvKeyState.PROBE_FAILED, f"could not start makemkvcon: {exc}"

    try:
        state, _ = await asyncio.wait_for(
            asyncio.gather(_scan_probe_stdout(proc), _discard_stderr(proc)), timeout=PROBE_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return MakemkvKeyState.PROBE_FAILED, f"makemkvcon probe timed out after {PROBE_TIMEOUT_SECONDS:.0f}s"

    await proc.wait()

    return _probe_outcome(state, proc.returncode)
