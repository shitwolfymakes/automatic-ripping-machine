"""AMD (Mesa VAAPI) encode path. No preset settings model: container from the
preset, fixed defaults below, and preset.extra_args for tuning (spec section 2)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from arm_common import ContainerFormat
from arm_common.encoders import EncoderSpec
from arm_transcode.ffmpeg_progress import ProgressCallback, consume_progress, drain_stderr

logger = logging.getLogger("arm_transcode.engines.ffmpeg_vaapi")

FFMPEG_MUXER: dict[ContainerFormat, str] = {ContainerFormat.MKV: "matroska", ContainerFormat.MP4: "mp4"}
DEFAULT_QP = "22"


def build_command(
    *,
    input_path: Path,
    output_path: Path,
    spec: EncoderSpec,
    device: str,
    container: ContainerFormat,
    extra_args: str | None,
) -> list[str]:
    muxer = FFMPEG_MUXER.get(container)
    if muxer is None:
        raise ValueError(f"ffmpeg_vaapi does not support container {container.value}")
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-nostats",
        "-loglevel",
        "error",
        "-progress",
        "pipe:1",
        "-y",
        "-vaapi_device",
        device,
        "-i",
        str(input_path),
        "-map",
        "0",
        "-vf",
        "format=nv12,hwupload",
        "-c:v",
        str(spec.engine_encoder),
        "-rc_mode",
        "CQP",
        "-qp",
        DEFAULT_QP,
        "-c:a",
        "copy",
        "-c:s",
        "copy",
        "-f",
        muxer,
    ]
    if extra_args:
        cmd.extend(extra_args.split())
    cmd.append(str(output_path))
    return cmd


async def transcode_ffmpeg_vaapi(
    *,
    input_path: Path,
    output_path: Path,
    spec: EncoderSpec,
    device: str,
    container: ContainerFormat,
    extra_args: str | None,
    duration_seconds: int | None,
    progress_callback: ProgressCallback,
) -> int:
    cmd = build_command(
        input_path=input_path,
        output_path=output_path,
        spec=spec,
        device=device,
        container=container,
        extra_args=extra_args,
    )
    logger.info("ffmpeg_vaapi start encoder=%s device=%s", spec.engine_encoder, device)
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stderr_buf: list[str] = []
    assert proc.stdout is not None and proc.stderr is not None
    await asyncio.gather(
        consume_progress(proc.stdout, duration_seconds, progress_callback),
        drain_stderr(proc.stderr, stderr_buf),
    )
    rc = await proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg_vaapi exited {rc}: {' | '.join(stderr_buf[-30:])}")
    return output_path.stat().st_size
