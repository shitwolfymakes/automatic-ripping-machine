"""HandBrakeCLI wrapper.

`HandBrakeCLI -i <input> -o <output> --preset "<preset_ref>" --json` emits
two-section JSON output: a `JSON Title Set` block (info), then `Progress`
records every ~1 s. We parse `Progress` records to surface % + ETA to the
caller's `progress_callback`.

Phase 7b: when `ARM_GPU_VENDOR` and `ARM_GPU_CODEC` are set in the env
(populated by the Backend dispatcher on spawn), `_hw_encoder_args()`
appends `--encoder <vendor>_<codec>` *after* `--preset` so HandBrake's
preset-driven encoder is overridden. `extra_args` from the user-defined
preset still appends last (escape hatch).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Awaitable, Callable

logger = logging.getLogger("arm_transcode.handbrake")

ProgressCallback = Callable[[int, int | None, str | None], Awaitable[None]]


_PROGRESS_BLOCK_RE = re.compile(r"Progress:\s*(\{.*?\})", re.DOTALL)


# Vendor + codec → HandBrake `--encoder` ID. The names match HandBrakeCLI's
# canonical encoder list (`HandBrakeCLI --help | grep encoder`) on
# Debian Bookworm builds. AV1 is intentionally absent — Phase 7b's encoder
# matrix is h264 + h265 only; AV1 lands in a follow-up.
_HW_ENCODER_TABLE: dict[tuple[str, str], str] = {
    ("vaapi", "h264"): "vaapi_h264",
    ("vaapi", "h265"): "vaapi_h265",
    ("qsv", "h264"): "qsv_h264",
    ("qsv", "h265"): "qsv_h265",
    ("nvenc", "h264"): "nvenc_h264",
    ("nvenc", "h265"): "nvenc_h265",
}


def _hw_encoder_args() -> list[str]:
    """Return `["--encoder", "<vendor>_<codec>"]` if the dispatcher injected
    a GPU into the env, else `[]`. Unknown combinations also yield `[]` so
    HandBrake falls back to the preset's CPU encoder.
    """
    vendor = os.environ.get("ARM_GPU_VENDOR")
    codec = os.environ.get("ARM_GPU_CODEC")
    if not vendor or not codec:
        return []
    encoder = _HW_ENCODER_TABLE.get((vendor, codec))
    if encoder is None:
        logger.warning(
            "no HandBrake encoder mapping for vendor=%s codec=%s; falling back to preset",
            vendor,
            codec,
        )
        return []
    return ["--encoder", encoder]


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
    cmd.extend(_hw_encoder_args())
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
    """Read stderr line-by-line. Buffer the tail for the rc!=0 error
    message and tee each line through the logger at DEBUG so the
    per-job log captures the full stderr — same shape as the MakeMKV
    `makemkv-raw` log lines.
    """
    while True:
        raw = await stream.readline()
        if not raw:
            break
        line = raw.decode(errors="replace").rstrip()
        buf.append(line)
        logger.debug("handbrake-stderr: %s", line)


async def _consume_progress(stream: asyncio.StreamReader, cb: ProgressCallback) -> None:
    """Read stdout line-by-line, log each line at DEBUG (so the per-job
    log captures HandBrake's full stdout), and stitch lines into a
    rolling buffer to look for `Progress:` JSON blocks. `--json` mode
    pretty-prints over multiple lines so we can't parse a single line in
    isolation, but capping the buffer to the last few KB keeps memory
    bounded if the producer outruns the regex.
    """
    pending = ""
    last_emitted = -1
    max_pending = 65_536  # plenty for one JSON record; trims trailing noise
    while True:
        raw = await stream.readline()
        if not raw:
            break
        line = raw.decode(errors="replace").rstrip("\n\r")
        if line:
            logger.debug("handbrake-stdout: %s", line)
        pending += line + "\n"
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
        # Trim what we've fully matched, then bound the residual buffer.
        last_match_end = 0
        for match in _PROGRESS_BLOCK_RE.finditer(pending):
            last_match_end = match.end()
        if last_match_end:
            pending = pending[last_match_end:]
        if len(pending) > max_pending:
            pending = pending[-max_pending:]


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
