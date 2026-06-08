"""HandBrakeCLI wrapper.

`HandBrakeCLI -i <input> -o <output> --preset "<preset_ref>"` emits
text-mode progress as one line per tick:

    Encoding: task 1 of 1, 12.34 % (45.67 fps, avg 23.45 fps, ETA 00h12m34s)

We parse each line as it streams in and surface % + ETA to the caller's
`progress_callback`. Text mode beats `--json` here because HandBrake's
JSON output pretty-prints every block over a dozen lines, which both
floods the per-job log and defeats simple regex extraction (the
non-greedy `\\{.*?\\}` regex stops at the first inner `}` instead of the
outer one — `json.loads` then fails on truncated input and progress
silently never advances). Text mode is naturally one-liner per tick.

Phase 7b: when `ARM_GPU_VENDOR` and `ARM_GPU_CODEC` are set in the env
(populated by the Backend dispatcher on spawn), `_hw_encoder_args()`
appends `--encoder <vendor>_<codec>` *after* `--preset` so HandBrake's
preset-driven encoder is overridden. `extra_args` from the user-defined
preset still appends last (escape hatch).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
from pathlib import Path
from typing import Awaitable, Callable

logger = logging.getLogger("arm_transcode.handbrake")

ProgressCallback = Callable[[int, int | None, str | None], Awaitable[None]]

# How many trailing stderr lines to attach to the rc!=0 error. HandBrake prints
# the verbose title/audio dump *before* the decisive failure line (e.g. the
# NVENC `Driver does not support the required nvenc API version` message), so a
# short tail silently drops the one line that explains the failure. The full
# stderr is always tee'd to the per-job log at DEBUG; this is just the inline
# excerpt carried in the exception → `transcode_tasks.last_error`.
_STDERR_TAIL_LINES = 1000


# `Encoding: task 2 of 3, 47.30 % (45.67 fps, avg 23.45 fps, ETA 00h12m34s)`
# `Encoding: task 1 of 1, 0.00 %`           ← no ETA yet (HandBrake hasn't
#                                              estimated frame rate)
# Anchored on `task N of M,` so we don't accidentally match `Scanning title 1
# of 1, 70.00 %` (which is title-scan progress, not encode progress).
_PROGRESS_LINE_RE = re.compile(
    r"task\s+(?P<pass>\d+)\s+of\s+(?P<pass_total>\d+),\s+(?P<pct>\d+(?:\.\d+)?)\s*%"
    r"(?:.*?ETA\s+(?P<h>\d+)h(?P<m>\d+)m(?P<s>\d+)s)?",
    re.IGNORECASE,
)


# Vendor + codec → HandBrake `--encoder` ID. These match the HW encoder IDs in
# our source-built HandBrakeCLI (services/transcode/Dockerfile, built with
# --enable-qsv/nvenc/vce). NOTE: HandBrake has no generic "vaapi" encoder — AMD
# is exposed as `vce_*`. The GPU probe tags AMD render nodes with the `vaapi`
# vendor (GpuVendor.VAAPI), so we bridge that vendor token to HandBrake's `vce_*`
# IDs here. AV1 is intentionally absent — Phase 7b's matrix is h264 + h265 only.
_HW_ENCODER_TABLE: dict[tuple[str, str], str] = {
    ("vaapi", "h264"): "vce_h264",
    ("vaapi", "h265"): "vce_h265",
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
    """Run HandBrakeCLI; stream text progress; return final file size in bytes.

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
        tail = "\n".join(stderr_buf[-_STDERR_TAIL_LINES:])
        raise RuntimeError(f"HandBrakeCLI exited rc={rc}\nstderr tail:\n{tail}")

    return output_path.stat().st_size


async def _drain_stderr(stream: asyncio.StreamReader, buf: list[str]) -> None:
    """Read stderr line-by-line. Buffer the tail for the rc!=0 error
    message and tee each line through the logger at DEBUG so the per-job
    log captures the full stderr — same shape as the MakeMKV
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
    """Read stdout, split on the carriage return + newline HandBrake uses
    as the progress separator, log each logical line at DEBUG, and fire
    `cb` on every `task N of M, P %` match.

    HandBrake's text mode rewrites the progress line in-place using `\\r`:

        Encoding: task 1 of 1, 0.87 %\\rEncoding: task 1 of 1, 1.81 %\\r…

    `StreamReader.readline()` only honours `\\n`, so a naive readline loop
    blocks until the trailing newline (effectively until the encode
    finishes) and then handles ~hundreds of progress updates as a single
    giant line — the regex `search()` finds only the first match (0 %)
    and the UI bar never advances. Reading bounded chunks and re-
    splitting on `\\r\\n` keeps both pathways working: progress updates
    fire one-by-one, and `\\n`-terminated lines (HandBrake's startup
    banner, JSON Title Set, the audio-encoder lines) still look like
    discrete entries in the log.
    """
    last_emitted = -1
    pending = ""
    while True:
        chunk = await stream.read(4096)
        if not chunk:
            # Process any trailing bit before exiting (rare — usually the
            # final progress line is followed by `\n` so it's already drained).
            if pending:
                await _process_progress_line(pending, cb, last_emitted)
            break
        pending += chunk.decode(errors="replace")
        # Treat both `\r` and `\n` as line breaks. HandBrake uses `\r` between
        # progress updates and `\n` for everything else.
        parts = re.split(r"[\r\n]", pending)
        # The final segment may be incomplete — keep it in `pending` until the
        # next chunk delivers its terminator.
        pending = parts[-1]
        for line in parts[:-1]:
            new_emitted = await _process_progress_line(line, cb, last_emitted)
            if new_emitted >= 0:
                last_emitted = new_emitted


async def _process_progress_line(line: str, cb: ProgressCallback, last_emitted: int) -> int:
    """Log one logical line, fire `cb` if it's a new progress %, return the
    pct that was emitted (or `last_emitted` unchanged when the line wasn't
    a new tick). Returning the pct lets the caller chain the dedupe state
    without globals.
    """
    if not line:
        return last_emitted
    logger.debug("handbrake-stdout: %s", line)
    match = _PROGRESS_LINE_RE.search(line)
    if match is None:
        return last_emitted
    pct = int(round(float(match.group("pct"))))
    if pct == last_emitted:
        return last_emitted
    eta = _parse_eta(match)
    # `current_pass` ships as `"N/M"` so the UI can render the HandBrake
    # internal pass count (e.g. `1/1` for a single-pass encode, `1/2`/`2/2`
    # for a two-pass encode) without having to know the schema's history.
    current_pass = f"{match.group('pass')}/{match.group('pass_total')}"
    try:
        await cb(pct, eta, current_pass)
    except Exception as exc:  # noqa: BLE001
        logger.debug("progress_callback raised: %s", exc)
    return pct


def _parse_eta(match: re.Match[str]) -> int | None:
    """Convert the regex match's `h/m/s` groups to total seconds, or None
    if HandBrake hasn't surfaced an ETA yet (early ticks lack the fps/ETA tail).
    """
    if match.group("h") is None:
        return None
    return int(match.group("h")) * 3600 + int(match.group("m")) * 60 + int(match.group("s"))
