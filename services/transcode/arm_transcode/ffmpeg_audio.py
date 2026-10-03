"""ffmpeg-based audio re-encoder.

The ripper produces `track_NN.wav` files for CDs. The transcode tasks
attached to a music session re-encode each WAV into the target container
(`flac` / `mp3`). `preset_ref` selects the codec — we map the small set
of seeded values to ffmpeg flags rather than letting users pass arbitrary
encoder strings.

Progress is parsed from `-progress pipe:1`, which ffmpeg emits as
`key=value` lines roughly every second. `out_time_us` (microseconds) +
the source's `duration_seconds` → percent.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from arm_transcode.ffmpeg_progress import ProgressCallback, consume_progress, drain_stderr

logger = logging.getLogger("arm_transcode.ffmpeg_audio")


# `-f <muxer>` is mandatory: the atomic-rename flow writes the output as
# `<final>.arm-inprogress`, and ffmpeg infers the container from the
# filename extension. Without `-f`, ffmpeg sees `.arm-inprogress` and
# bails with "Unable to find a suitable output format" before encoding
# anything. Same shape as ffmpeg_video.py.
_CODEC_FLAGS: dict[str, list[str]] = {
    "flac": ["-c:a", "flac", "-compression_level", "8", "-f", "flac"],
    "mp3": ["-c:a", "libmp3lame", "-q:a", "0", "-f", "mp3"],
}


async def transcode_audio(
    *,
    input_path: Path,
    output_path: Path,
    preset_ref: str,
    duration_seconds: int | None,
    progress_callback: ProgressCallback,
) -> int:
    """Run ffmpeg to re-encode `input_path` → `output_path`.

    Returns the final file size in bytes; raises `RuntimeError` on non-zero exit.
    """
    flags = _CODEC_FLAGS.get(preset_ref.lower())
    if flags is None:
        raise RuntimeError(f"unsupported audio preset_ref={preset_ref!r}")

    cmd: list[str] = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-y",
        "-i",
        str(input_path),
        *flags,
        str(output_path),
    ]
    logger.info("ffmpeg launching: %s", " ".join(cmd))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stdout is not None
    assert proc.stderr is not None

    stderr_buf: list[str] = []
    stderr_task = asyncio.create_task(drain_stderr(proc.stderr, stderr_buf))

    try:
        await consume_progress(proc.stdout, duration_seconds, progress_callback)
        rc = await proc.wait()
    finally:
        with contextlib.suppress(asyncio.CancelledError):
            await stderr_task

    if rc != 0:
        tail = "\n".join(stderr_buf[-30:])
        raise RuntimeError(f"ffmpeg exited rc={rc}\nstderr tail:\n{tail}")

    return output_path.stat().st_size
