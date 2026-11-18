"""Transcoder entry point — single-task, ephemeral.

Run order:
1. Load env (`TranscoderConfig`).
2. Open the WS connection (subscribe `transcoder.commands.{task_id}` for cancel).
3. POST /register, POST /claim. Refuse if claim returns anything other than IN_PROGRESS.
4. Pick the encoder by `transcode_preset.tool`:
   - HANDBRAKE → `handbrake.transcode_handbrake`
   - ABCDE → `ffmpeg_audio.transcode_audio`
   - NONE → `arm_common.fileops.transcode_none` (no atomic-rename needed)
5. Wrap the output write in `arm_common.fileops.atomic_output` so partial
   files land as `*.arm-inprogress` and only get renamed on success.
6. PATCH /complete with size + duration metadata.
7. On exception or cancel: PATCH /fail with the error string.

Container exits when the run() coroutine returns.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import ssl
import sys
import tempfile
from pathlib import Path

from arm_common import configure_service_logging, with_log_context
from arm_common.encoders import EncoderSpec
from arm_common.schemas.handbrake import HandbrakeSettings
from arm_common.schemas import (
    HardwareCaps,
    RegisterTranscoderResponse,
    TranscodePresetView,
    WSEnvelope,
)
from arm_common.enums import GpuVendor, TranscodeTool
from arm_common.fileops import atomic_output, transcode_none

from arm_transcode.api_client import BackendClient
from arm_transcode.config import TranscoderConfig
from arm_transcode.device_probe import ProbeSetupError, probe_device
from arm_transcode.engines import selected_encoder
from arm_transcode.engines.ffmpeg_vaapi import transcode_ffmpeg_vaapi
from arm_transcode.engines.handbrake_engine import encoder_args as handbrake_encoder_args
from arm_transcode.ffmpeg_audio import transcode_audio
from arm_transcode.handbrake import ProgressCallback, transcode_handbrake
from arm_transcode.handbrake_preset_file import materialise_for_encode, settings_of, write_preset_file
from arm_transcode.heartbeat import HeartbeatPump, ProgressState
from arm_transcode.schema_file import dump_schema
from arm_transcode.ws_client import EnvelopeHandler, WSClient


logger = logging.getLogger("arm_transcode.main")

# Upper bound on the error string we PATCH to `transcode_tasks.last_error`.
# `last_error` is an unbounded TEXT column, but a pathological multi-MB stderr
# shouldn't bloat the row / WS frame. Generous enough to hold handbrake.py's
# 1000-line stderr tail (~80 KB) intact; see `_clip_error`.
_MAX_ERROR_CHARS = 100_000


def _clip_error(msg: str) -> str:
    """Bound an error string for `last_error`, keeping the *tail*.

    Encoder failures (HandBrake/ffmpeg) print the decisive line last, so we
    truncate from the front, not the back — the historical `str(exc)[:500]`
    kept the front and dropped exactly the line that explained the failure.
    """
    if len(msg) <= _MAX_ERROR_CHARS:
        return msg
    return "…(truncated)…\n" + msg[-_MAX_ERROR_CHARS:]


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


def _progress_recorder(state: ProgressState, cancel_event: asyncio.Event) -> ProgressCallback:
    """Build a progress callback that records each tick on `state` and raises CancelRequested once cancelled."""

    async def _on_progress(
        pct: int, eta: int | None, current: str | None, fps: float | None, avg_fps: float | None
    ) -> None:
        state.pct = pct
        state.eta_seconds = eta
        state.current_pass = current
        state.fps = fps
        state.avg_fps = avg_fps
        if cancel_event.is_set():
            raise CancelRequested("task.cancel received")

    return _on_progress


def _require_gpu_device() -> str:
    """Return the GPU device path from ARM_GPU_DEVICE; raise RuntimeError when it is unset or empty."""
    device = os.environ.get("ARM_GPU_DEVICE")
    if not device:
        raise RuntimeError("ffmpeg_vaapi encoder requires ARM_GPU_DEVICE")
    return device


async def _encode_ffmpeg_vaapi(
    *,
    preset: TranscodePresetView,
    spec: EncoderSpec,
    raw_input: Path,
    final_output: Path,
    duration_seconds: int | None,
    progress_callback: ProgressCallback,
) -> int:
    """Run the ffmpeg VAAPI engine into an atomic output and return the size written."""
    device = _require_gpu_device()
    with atomic_output(final_output) as tmp:
        return await transcode_ffmpeg_vaapi(
            input_path=raw_input,
            output_path=tmp,
            spec=spec,
            device=device,
            container=preset.container,
            extra_args=preset.extra_args,
            duration_seconds=duration_seconds,
            progress_callback=progress_callback,
        )


async def _encode_handbrake_builtin(
    *,
    preset: TranscodePresetView,
    spec: EncoderSpec | None,
    raw_input: Path,
    final_output: Path,
    progress_callback: ProgressCallback,
) -> int:
    """Today's run for a preset without settings: `--preset <preset_ref> --encoder X` (M11)."""
    with atomic_output(final_output) as tmp:
        return await transcode_handbrake(
            input_path=raw_input,
            output_path=tmp,
            preset_ref=preset.preset_ref,
            extra_args=preset.extra_args,
            encoder_args=handbrake_encoder_args(spec),
            progress_callback=progress_callback,
        )


async def _encode_handbrake_settings(
    *,
    preset: TranscodePresetView,
    settings: HandbrakeSettings,
    spec: EncoderSpec | None,
    raw_input: Path,
    final_output: Path,
    progress_callback: ProgressCallback,
) -> int:
    """Run HandBrakeCLI from the preset's materialised settings, validated before launch (M5)."""
    materialised = materialise_for_encode(preset, settings, spec)
    # The transcoder has no per-task work directory; this one lives for the encode.
    with tempfile.TemporaryDirectory(prefix="arm-hb-") as work_dir:
        preset_file = write_preset_file(Path(work_dir), materialised.preset_file)
        with atomic_output(final_output) as tmp:
            return await transcode_handbrake(
                input_path=raw_input,
                output_path=tmp,
                preset_ref=preset.preset_ref,
                extra_args=preset.extra_args,
                encoder_args=materialised.flags,
                preset_file=preset_file,
                progress_callback=progress_callback,
            )


async def _encode_handbrake(
    *,
    preset: TranscodePresetView,
    spec: EncoderSpec | None,
    raw_input: Path,
    final_output: Path,
    progress_callback: ProgressCallback,
) -> int:
    """Run HandBrakeCLI into an atomic output and return the size written."""
    settings = settings_of(preset)
    if settings is None:
        return await _encode_handbrake_builtin(
            preset=preset,
            spec=spec,
            raw_input=raw_input,
            final_output=final_output,
            progress_callback=progress_callback,
        )
    return await _encode_handbrake_settings(
        preset=preset,
        settings=settings,
        spec=spec,
        raw_input=raw_input,
        final_output=final_output,
        progress_callback=progress_callback,
    )


async def _encode_audio(
    *,
    preset: TranscodePresetView,
    raw_input: Path,
    final_output: Path,
    duration_seconds: int | None,
    progress_callback: ProgressCallback,
) -> int:
    """Run the ffmpeg audio engine into an atomic output and return the size written."""
    # The ripper's abcde stage produced .wav files; we re-encode to
    # `preset.container.value` (flac, mp3) here.
    target = preset.preset_ref or preset.container.value
    with atomic_output(final_output) as tmp:
        return await transcode_audio(
            input_path=raw_input,
            output_path=tmp,
            preset_ref=target,
            duration_seconds=duration_seconds,
            progress_callback=progress_callback,
        )


def _lacks_base(tool: TranscodeTool, preset: TranscodePresetView) -> bool:
    """True when the preset has no `preset_ref` and needs one: every preset except HandBrake with settings."""
    settings_run = tool == TranscodeTool.HANDBRAKE and settings_of(preset) is not None
    return preset.preset_ref is None and not settings_run


async def _encode(
    *,
    tool: TranscodeTool,
    preset: TranscodePresetView | None,
    raw_input: Path,
    final_output: Path,
    duration_seconds: int | None,
    progress_callback: ProgressCallback,
) -> int:
    """Run the engine `tool` selects and return the size it wrote."""
    if tool == TranscodeTool.NONE:
        return transcode_none(raw_input, final_output)

    spec = selected_encoder()
    if tool == TranscodeTool.HANDBRAKE and spec is not None and spec.engine == "ffmpeg_vaapi":
        # `tool` only equals HANDBRAKE when `preset` produced it (see `run()`
        # below), so `preset` is never None on this branch.
        assert preset is not None
        return await _encode_ffmpeg_vaapi(
            preset=preset,
            spec=spec,
            raw_input=raw_input,
            final_output=final_output,
            duration_seconds=duration_seconds,
            progress_callback=progress_callback,
        )

    if preset is None or _lacks_base(tool, preset):
        raise RuntimeError(f"transcode tool={tool.value} requires a preset_ref")

    if tool == TranscodeTool.HANDBRAKE:
        return await _encode_handbrake(
            preset=preset,
            spec=spec,
            raw_input=raw_input,
            final_output=final_output,
            progress_callback=progress_callback,
        )

    if tool == TranscodeTool.ABCDE:
        return await _encode_audio(
            preset=preset,
            raw_input=raw_input,
            final_output=final_output,
            duration_seconds=duration_seconds,
            progress_callback=progress_callback,
        )

    raise RuntimeError(f"unknown transcode tool={tool.value}")


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
    """Encode with the engine for `tool`, recording progress on `state`; returns the size written."""
    size = await _encode(
        tool=tool,
        preset=preset,
        raw_input=raw_input,
        final_output=final_output,
        duration_seconds=duration_seconds,
        progress_callback=_progress_recorder(state, cancel_event),
    )
    state.pct = 100
    return size


def _cancel_listener(cancel_event: asyncio.Event) -> EnvelopeHandler:
    """Build a WS handler that sets `cancel_event` on a task.cancel envelope and ignores the rest."""

    async def _on_cancel(env: WSEnvelope) -> None:
        if env.event_type == "task.cancel":
            logger.warning("task.cancel received over WS; signalling encoder")
            cancel_event.set()

    return _on_cancel


def _backend_ssl_context() -> ssl.SSLContext:
    """Build the TLS context for the Backend's wss:// endpoint from the system trust store.

    The Backend serves wss:// with a cert chained to the install CA. The entrypoint already merges that CA into the
    system trust store, at the same /etc/ssl/certs/ca-certificates.crt path api_client.py uses for the HTTP client.
    `websockets` refuses to connect over wss:// without an explicit ssl context, so build one from the system store.
    """
    return ssl.create_default_context()


async def _report_complete(
    *, api: BackendClient, task_id: str, media_root: str, final_output: Path, size: int, duration: int | None
) -> None:
    """Tell the Backend the task completed, with the output path relative to media_root."""
    relative = final_output.relative_to(media_root).as_posix()
    await api.complete(
        task_id,
        output_path=relative,
        size_bytes=size,
        duration_seconds=duration,
    )
    logger.info("task complete output=%s size=%d", relative, size)


async def _encode_and_report(
    *,
    api: BackendClient,
    ws: WSClient,
    task_id: str,
    registered: RegisterTranscoderResponse,
    cancel_event: asyncio.Event,
) -> int:
    """Encode the registered task under a heartbeat, report the outcome to the Backend, and return the exit code."""
    raw_input = Path(registered.raw_input_path)
    final_output = Path(registered.media_root) / (registered.task.output_path or "")
    preset = registered.transcode_preset
    tool = preset.tool if preset is not None else TranscodeTool.NONE
    duration = registered.source_track.duration_seconds

    state = ProgressState()
    try:
        async with HeartbeatPump(api=api, ws=ws, task_id=task_id, state=state):
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
        await api.fail(task_id, last_error="cancelled by user")
        logger.info("task cancelled cleanly")
        return 0
    except Exception as exc:
        logger.exception("encoder failed: %s", exc)
        await api.fail(task_id, last_error=_clip_error(str(exc)))
        return 1
    else:
        await _report_complete(
            api=api,
            task_id=task_id,
            media_root=registered.media_root,
            final_output=final_output,
            size=size,
            duration=duration,
        )
        return 0


async def _run_task(*, cfg: TranscoderConfig, api: BackendClient, ssl_ctx: ssl.SSLContext) -> int:
    """Open the WS session, register and claim the task, then encode it under its log context; return the exit code."""
    cancel_event = asyncio.Event()
    async with WSClient(
        url=cfg.ws_url,
        service_token=cfg.service_token,
        hostname=cfg.hostname,
        task_id=cfg.task_id,
        ssl_context=ssl_ctx,
    ) as ws:
        await ws.subscribe(f"transcoder.commands.{cfg.task_id}", _cancel_listener(cancel_event))
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

            return await _encode_and_report(
                api=api, ws=ws, task_id=cfg.task_id, registered=registered, cancel_event=cancel_event
            )


async def run() -> int:
    cfg = TranscoderConfig()
    configure_service_logging(cfg.service_name, level=cfg.log_level)
    logger.info("transcoder starting task_id=%s host=%s", cfg.task_id, cfg.hostname)

    api = BackendClient(
        base_url=cfg.backend_url,
        service_token=cfg.service_token,
        hostname=cfg.hostname,
    )

    ssl_ctx = _backend_ssl_context()

    try:
        return await _run_task(cfg=cfg, api=api, ssl_ctx=ssl_ctx)
    finally:
        await api.close()


def main() -> int:
    if "--dump-schema" in sys.argv[1:]:
        return dump_schema()
    if "--probe-encoders" in sys.argv[1:]:
        # Deprecated compatibility mode. The install-time HandBrakeCLI --help
        # scrape this used to run is gone; an installer or drill script that
        # still invokes this flag gets an empty result rather than a crash.
        # The backend now treats install-time encoder lists as hints only and
        # probes each GPU device for real via --probe-device, so an empty
        # {} here is a truthful "nothing probed", not an over-claim.
        print("--probe-encoders is deprecated; the backend probes each GPU with --probe-device", file=sys.stderr)
        print(json.dumps({}, separators=(",", ":")))
        return 0
    if "--probe-device" in sys.argv[1:]:
        vendor, device = os.environ.get("ARM_GPU_VENDOR"), os.environ.get("ARM_GPU_DEVICE")
        if not vendor or not device:
            print("--probe-device needs ARM_GPU_VENDOR and ARM_GPU_DEVICE", file=sys.stderr)
            return 2
        try:
            gpu_vendor = GpuVendor(vendor)
        except ValueError:
            valid = ", ".join(v.value for v in GpuVendor)
            print(f"--probe-device: unknown ARM_GPU_VENDOR={vendor!r} (valid: {valid})", file=sys.stderr)
            return 2
        try:
            result = probe_device(gpu_vendor, device)
        except ProbeSetupError as exc:
            print(str(exc), file=sys.stderr)
            return 3
        print(json.dumps(result, separators=(",", ":")))
        return 0
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
