"""HandBrakeCLI wrapper.

`HandBrakeCLI -i <input> -o <output> --preset "<preset_ref>" --json` emits
two-section JSON output: a `JSON Title Set` block (info), then `Progress`
records every ~1 s. We parse `Progress` records to surface % + ETA to the
caller's `progress_callback`. CPU-only Phase 7 — `--encoder` flags are
preset-driven; HW-accel-specific encoders land with Phase 7b.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from pathlib import Path
from typing import Any, Awaitable, Callable

logger = logging.getLogger("arm_transcode.handbrake")

ProgressCallback = Callable[[int, int | None, str | None], Awaitable[None]]


_PROGRESS_BLOCK_RE = re.compile(r"Progress:\s*(\{.*?\})", re.DOTALL)


async def transcode_handbrake(
    *,
    input_path: Path,
    output_path: Path,
    preset_ref: str,
    extra_args: str | None,
    progress_callback: ProgressCallback,
) -> int:
    """Run HandBrakeCLI; stream JSON progress; return final file size in bytes.

    Raises `RuntimeError` on non-zero exit. The caller is responsible for
    catching and dispatching to `BackendClient.fail`.
    """
    cmd: list[str] = [
        "HandBrakeCLI",
        "-i",
        str(input_path),
        "-o",
        str(output_path),
        "--preset",
        preset_ref,
        "--json",
    ]
    if extra_args:
        cmd.extend(extra_args.split())

    logger.info("HandBrakeCLI launching: %s", " ".join(cmd))
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stdout is not None
    assert proc.stderr is not None

    stderr_buf: list[str] = []
    stderr_task = asyncio.create_task(_drain_stderr(proc.stderr, stderr_buf))

    try:
        await _consume_progress(proc.stdout, progress_callback)
        rc = await proc.wait()
    finally:
        with contextlib.suppress(asyncio.CancelledError):
            await stderr_task

    if rc != 0:
        tail = "\n".join(stderr_buf[-30:])
        raise RuntimeError(f"HandBrakeCLI exited rc={rc}\nstderr tail:\n{tail}")

    return output_path.stat().st_size


async def _drain_stderr(stream: asyncio.StreamReader, buf: list[str]) -> None:
    while True:
        line = await stream.readline()
        if not line:
            break
        buf.append(line.decode(errors="replace").rstrip())


async def _consume_progress(stream: asyncio.StreamReader, cb: ProgressCallback) -> None:
    """Buffer stdout, hunt for `Progress:` JSON blocks, fire `cb` on each."""
    pending = ""
    last_emitted = -1
    while True:
        chunk = await stream.read(4096)
        if not chunk:
            break
        pending += chunk.decode(errors="replace")
        for match in _PROGRESS_BLOCK_RE.finditer(pending):
            try:
                obj: dict[str, Any] = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
            pct, eta, current_pass = _extract_progress(obj)
            if pct is not None and pct != last_emitted:
                last_emitted = pct
                try:
                    await cb(pct, eta, current_pass)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("progress_callback raised: %s", exc)
        # Trim what we've fully matched to keep the buffer bounded.
        last_match_end = 0
        for match in _PROGRESS_BLOCK_RE.finditer(pending):
            last_match_end = match.end()
        if last_match_end:
            pending = pending[last_match_end:]


def _extract_progress(obj: dict[str, Any]) -> tuple[int | None, int | None, str | None]:
    """HandBrake JSON progress record carries `Working` or `WorkDone` blocks.

    `Working` example fields: `Progress` (0..1 float), `ETASeconds` (int),
    `PassID`, `Pass` (1..N), `PassCount`. We surface a 0..100 int.
    """
    working = obj.get("Working") or {}
    if not working:
        return (None, None, None)
    progress_frac = working.get("Progress")
    if isinstance(progress_frac, (int, float)):
        pct = int(round(float(progress_frac) * 100))
    else:
        pct = None
    eta = working.get("ETASeconds")
    if not isinstance(eta, int):
        eta = None
    pass_id = working.get("PassID")
    current_pass = str(pass_id) if pass_id is not None else None
    return (pct, eta, current_pass)
