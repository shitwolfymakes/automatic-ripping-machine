"""Transcoder entry point — single-task, ephemeral.

Run order:
1. Load env (`TranscoderConfig`).
2. Open the WS connection (subscribe `transcoder.commands.{task_id}` for cancel).
3. POST /register, POST /claim. Refuse if claim returns anything other than IN_PROGRESS.
4. Pick the encoder by `transcode_preset.tool`:
   - HANDBRAKE → `handbrake.transcode_handbrake`
   - ABCDE → `ffmpeg_audio.transcode_audio`
   - NONE → `passthrough.transcode_none` (no atomic-rename needed)
5. Wrap the output write in `atomic.atomic_output` so partial files land
   as `*.arm-inprogress` and only get renamed on success.
6. PATCH /complete with size + duration metadata.
7. On exception or cancel: PATCH /fail with the error string.

Container exits when the run() coroutine returns.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

from arm_common import configure_service_logging, with_log_context
from arm_common.schemas import (
    HardwareCaps,
    TranscodePresetView,
    WSEnvelope,
)
from arm_common.enums import TranscodeTool

from arm_transcode.api_client import BackendClient
from arm_transcode.atomic import atomic_output
from arm_transcode.config import TranscoderConfig
from arm_transcode.ffmpeg_audio import transcode_audio
from arm_transcode.handbrake import transcode_handbrake
from arm_transcode.heartbeat import HeartbeatPump, ProgressState
from arm_transcode.passthrough import transcode_none
from arm_transcode.ws_client import WSClient


logger = logging.getLogger("arm_transcode.main")


class CancelRequested(Exception):
    pass


def _detect_hw_caps() -> HardwareCaps:
    """Diagnostic-only: reports the GPU vendor the dispatcher assigned us.

    The Backend's `gpu_probe` is the authoritative inventory source — this
    function exists so the `register` payload reflects what the *spawned
    container* actually sees (useful for log triage when device passthrough
    fails). The Backend ignores these flags for dispatch decisions.
    """
    vendor = os.environ.get("ARM_GPU_VENDOR", "").lower()
    return HardwareCaps(
        cpu_count=os.cpu_count() or 1,
        has_vaapi=(vendor == "vaapi"),
        has_nvenc=(vendor == "nvenc"),
        has_qsv=(vendor == "qsv"),
    )


async def _run_encoder(
    *,
    tool: TranscodeTool,
    preset: TranscodePresetView | None,
    raw_input: Path,
    final_output: Path,
    duration_seconds: int | None,
    state: ProgressState,
    cancel_event: asyncio.Event,
) -> int:
    """Dispatch on `tool`. Returns the size of the file we wrote."""

    async def _on_progress(pct: int, eta: int | None, current: str | None) -> None:
        state.pct = pct
        state.eta_seconds = eta
        state.current_pass = current
        if cancel_event.is_set():
            raise CancelRequested("task.cancel received")

    if tool == TranscodeTool.NONE:
        size = transcode_none(raw_input, final_output)
        state.pct = 100
        return size

    if preset is None or preset.preset_ref is None:
        raise RuntimeError(f"transcode tool={tool.value} requires a preset_ref")

    if tool == TranscodeTool.HANDBRAKE:
        with atomic_output(final_output) as tmp:
            size = await transcode_handbrake(
                input_path=raw_input,
                output_path=tmp,
                preset_ref=preset.preset_ref,
                extra_args=preset.extra_args,
                progress_callback=_on_progress,
            )
        state.pct = 100
        return size

    if tool == TranscodeTool.ABCDE:
        # The ripper's abcde stage produced .wav files; we re-encode to
        # `preset.container.value` (flac, mp3) here.
        target = preset.preset_ref or preset.container.value
        with atomic_output(final_output) as tmp:
            size = await transcode_audio(
                input_path=raw_input,
                output_path=tmp,
                preset_ref=target,
                duration_seconds=duration_seconds,
                progress_callback=_on_progress,
            )
        state.pct = 100
        return size

    raise RuntimeError(f"unknown transcode tool={tool.value}")


async def run() -> int:
    cfg = TranscoderConfig()
    configure_service_logging(cfg.service_name, level=cfg.log_level)
    logger.info("transcoder starting task_id=%s host=%s", cfg.task_id, cfg.hostname)

    api = BackendClient(
        base_url=cfg.backend_url,
        service_token=cfg.service_token,
        hostname=cfg.hostname,
    )

    cancel_event = asyncio.Event()

    async def _on_cancel(env: WSEnvelope) -> None:
        if env.event_type == "task.cancel":
            logger.warning("task.cancel received over WS; signalling encoder")
            cancel_event.set()

    rc = 1
    try:
        async with WSClient(
            url=cfg.ws_url,
            service_token=cfg.service_token,
            hostname=cfg.hostname,
            task_id=cfg.task_id,
        ) as ws:
            await ws.subscribe(f"transcoder.commands.{cfg.task_id}", _on_cancel)
            await ws.wait_until_connected(timeout=10.0)

            registered = await api.register(task_id=cfg.task_id, hw_caps=_detect_hw_caps())
            # Phase 12 — once register lands we have job_id / track_id /
            # session_application_id; everything below logs with full context.
            # `job_id` lives on `source_track`, not on the task row.
            with with_log_context(
                job_id=registered.source_track.job_id,
                track_id=registered.task.source_track_id,
                session_application_id=registered.task.session_application_id,
            ):
                await api.claim(cfg.task_id)

                raw_input = Path(registered.raw_input_path)
                final_output = Path(registered.media_root) / (registered.task.output_path or "")
                preset = registered.transcode_preset
                tool = preset.tool if preset is not None else TranscodeTool.NONE
                duration = registered.source_track.duration_seconds

                state = ProgressState()
                try:
                    async with HeartbeatPump(api=api, ws=ws, task_id=cfg.task_id, state=state):
                        size = await _run_encoder(
                            tool=tool,
                            preset=preset,
                            raw_input=raw_input,
                            final_output=final_output,
                            duration_seconds=duration,
                            state=state,
                            cancel_event=cancel_event,
                        )
                except CancelRequested:
                    await api.fail(cfg.task_id, last_error="cancelled by user")
                    logger.info("task cancelled cleanly")
                    rc = 0
                except Exception as exc:
                    logger.exception("encoder failed: %s", exc)
                    await api.fail(cfg.task_id, last_error=str(exc)[:500])
                    rc = 1
                else:
                    relative = final_output.relative_to(registered.media_root).as_posix()
                    await api.complete(
                        cfg.task_id,
                        output_path=relative,
                        size_bytes=size,
                        duration_seconds=duration,
                    )
                    logger.info("task complete output=%s size=%d", relative, size)
                    rc = 0
    finally:
        await api.close()

    return rc


def main() -> int:
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
