"""Choosing the GPU a transcode task runs on (the claim decisions over a preset's encoder and the gpus rows)
and releasing it again."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_common import Gpu, GpuStatus, TranscodePreset
from arm_common.encoders import (
    VENDOR_RANK,
    EncoderSpec,
    cpu_encoder_for,
    get_encoder,
    gpu_could_serve,
    vendor_supports_container,
)


class GpuAssignment(NamedTuple):
    """Outcome of `TranscodeDispatcher._claim_gpu_for_task`.

    `gpu` is the claimed device, or None for a CPU spawn. `encoder` is the
    RESOLVED catalog encoder the worker runs: for an `any_<codec>` preset it
    is the claimed vendor's GPU encoder or the `cpu_<codec>` fallback; it is
    None for the `preset` encoder (HandBrake's own). `action="queue"` leaves
    the task queued for a later tick (every eligible device busy or being
    probed, or a device still awaiting its first probe); `action="fail"`
    means the task can never run as configured and `reason` says why.
    """

    gpu: Gpu | None
    encoder: EncoderSpec | None
    action: Literal["spawn", "queue", "fail"]
    reason: str | None = None


async def release_gpu_for_task(db: AsyncSession, task_id: str) -> None:
    """Flip every GPU row claimed by this task back to AVAILABLE.

    Called from the transcoder router on complete/fail and from the
    stale-claim sweep. Idempotent — a no-op if no GPU was claimed.
    Caller is responsible for committing.
    """
    gpus = (await db.execute(select(Gpu).where(col(Gpu.claimed_by_task_id) == task_id))).scalars().all()
    for gpu in gpus:
        gpu.status = GpuStatus.AVAILABLE
        gpu.claimed_by_task_id = None


WAITING_FOR_PROBE_REASON = "waiting for GPU probe"


def assignment_before_device_lookup(preset: TranscodePreset | None) -> GpuAssignment | EncoderSpec:
    """The final assignment when `preset` needs no device lookup (no preset,
    an unknown encoder, a `preset` or `cpu_*` encoder, or a container the
    encoder's vendor cannot write); otherwise the GPU-capable encoder spec
    to look a device up for."""
    if preset is None:
        return GpuAssignment(gpu=None, encoder=None, action="spawn")
    try:
        spec = get_encoder(preset.encoder)
    except ValueError:
        return GpuAssignment(
            gpu=None,
            encoder=None,
            action="fail",
            reason=f"preset {preset.id} has unknown encoder {preset.encoder!r}",
        )
    if spec.kind == "preset":
        return GpuAssignment(gpu=None, encoder=None, action="spawn")
    if spec.kind == "cpu":
        return GpuAssignment(gpu=None, encoder=spec, action="spawn")
    if spec.vendor is not None and not vendor_supports_container(spec.vendor, preset.container):
        # A preset saved before the API refused this pairing.
        return GpuAssignment(
            gpu=None,
            encoder=spec,
            action="fail",
            reason=f"encoder {spec.id} cannot write {preset.container.value}; edit the preset to use mkv or mp4",
        )
    return spec


def assignment_with_no_candidate(
    spec: EncoderSpec,
    codec: str,
    eligible: list[Gpu],
    gpus: list[Gpu],
    awaiting_probe: Callable[[Gpu], bool],
) -> GpuAssignment:
    """What to do when no eligible device can be claimed right now: wait for
    a mid-probe device or a pending probe, fall back to CPU for `any_*`, or
    fail."""
    if eligible:
        # Every eligible device is mid-probe; it is only absent for
        # this tick, so wait rather than fail or fall back to CPU.
        return GpuAssignment(gpu=None, encoder=spec, action="queue")
    if any(gpu_could_serve(g, spec) and awaiting_probe(g) for g in gpus):
        # A never-probed device that could serve this encoder has a
        # probe scheduled or running; its result decides the device.
        return GpuAssignment(gpu=None, encoder=spec, action="queue", reason=WAITING_FOR_PROBE_REASON)
    if spec.kind == "any":
        return GpuAssignment(gpu=None, encoder=cpu_encoder_for(codec), action="spawn")
    return GpuAssignment(
        gpu=None,
        encoder=spec,
        action="fail",
        reason=f"no enabled device has verified {spec.id}; re-probe or enable it in Settings > GPUs",
    )


def pick_free_gpu(candidates: list[Gpu]) -> Gpu | None:
    """The best-ranked available device among `candidates`, or None."""
    # Deterministic pick instead of row order: vendor rank, then device
    # path, so a mixed-vendor host always prefers the same silicon.
    free = sorted(
        (g for g in candidates if g.status == GpuStatus.AVAILABLE),
        key=lambda g: (VENDOR_RANK.get(g.vendor, 99), g.device_path),
    )
    return free[0] if free else None
