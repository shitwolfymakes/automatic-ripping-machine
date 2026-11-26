"""Choosing the GPU a transcode task runs on (the claim decisions over a preset's encoder and the gpus rows)
and releasing it again."""

from __future__ import annotations

from collections.abc import Callable, Mapping
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
    gpu_encoder_for,
    gpu_encoders_for_vendor,
    vendor_supports_container,
)
from arm_common.handbrake_schema.effective import UnknownBasePreset
from arm_common.handbrake_schema.reach import reachable_families
from arm_common.handbrake_schema.types import HandbrakeSchema
from arm_common.handbrake_schema.validate import validate_family
from arm_common.schemas import HandbrakeSettings, SettingIssue


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


def has_handbrake_settings(preset: TranscodePreset) -> bool:
    """Whether the preset carries any HandBrake setting (an empty dict or empty blocks count as none)."""
    if not preset.handbrake_settings:
        return False
    return not HandbrakeSettings.model_validate(preset.handbrake_settings).is_empty()


def invalid_families(schema: HandbrakeSchema | None, preset: TranscodePreset) -> dict[str, list[SettingIssue]]:
    """The preset's reachable families its settings make invalid, in claim order, with their issues.
    Empty with no schema loaded or no settings. Raises UnknownBasePreset for a bad `preset_ref`."""
    if schema is None or not has_handbrake_settings(preset):
        return {}
    settings = HandbrakeSettings.model_validate(preset.handbrake_settings)
    issues = {
        family: validate_family(schema, family=family, preset_ref=preset.preset_ref, settings=settings)
        for family in reachable_families(schema, preset.encoder, preset.preset_ref)
    }
    return {family: found for family, found in issues.items() if found}


def invalid_families_or_failure(
    schema: HandbrakeSchema | None, preset: TranscodePreset
) -> dict[str, list[SettingIssue]] | GpuAssignment:
    """`invalid_families`, or a failed assignment when the preset's base preset is unknown (no family
    can be valid then)."""
    try:
        return invalid_families(schema, preset)
    except UnknownBasePreset as error:
        return GpuAssignment(gpu=None, encoder=None, action="fail", reason=str(error))


def invalid_settings_reason(invalid: Mapping[str, list[SettingIssue]]) -> str:
    """The failure reason naming every invalid family and each of its issues."""
    per_family = "; ".join(f"{family}: {issue_messages(issues)}" for family, issues in invalid.items())
    return f"no valid encoder for this preset: {per_family}"


def issue_messages(issues: list[SettingIssue]) -> str:
    return "; ".join(issue.message for issue in issues)


def assignment_when_only_family_invalid(
    decided: GpuAssignment | EncoderSpec, invalid: Mapping[str, list[SettingIssue]]
) -> GpuAssignment | None:
    """A failed assignment when a single-family preset (`preset`, `cpu_*` or a pinned GPU encoder) has
    that family invalid; None for `any_*` (the device lookup reroutes) or when nothing is invalid."""
    encoder = decided.encoder if isinstance(decided, GpuAssignment) else decided
    if not invalid or (encoder is not None and encoder.kind == "any"):
        return None
    return GpuAssignment(gpu=None, encoder=encoder, action="fail", reason=invalid_settings_reason(invalid))


def _runs_ffmpeg_engine(gpu: Gpu) -> bool:
    return any(spec.engine == "ffmpeg_vaapi" for spec in gpu_encoders_for_vendor(gpu.vendor))


def exclude_ffmpeg_engine(gpus: list[Gpu], preset: TranscodePreset) -> list[Gpu]:
    """Drop devices whose encoder runs the ffmpeg VAAPI engine when the preset has HandBrake settings,
    which that engine cannot apply (M4)."""
    if not has_handbrake_settings(preset):
        return gpus
    return [g for g in gpus if not _runs_ffmpeg_engine(g)]


def exclude_invalid_families(gpus: list[Gpu], codec: str, invalid: Mapping[str, list[SettingIssue]]) -> list[Gpu]:
    """Drop devices whose encoder for `codec` is a family the claim-time check found invalid (R1)."""
    return [g for g in gpus if _family_for(g, codec) not in invalid]


def _family_for(gpu: Gpu, codec: str) -> str | None:
    spec = gpu_encoder_for(gpu.vendor, codec)
    return spec.engine_encoder if spec is not None else None


def cpu_fallback(codec: str, invalid: Mapping[str, list[SettingIssue]]) -> GpuAssignment:
    """Spawn on the codec's CPU encoder, or fail with every invalid family when that one is invalid too."""
    cpu = cpu_encoder_for(codec)
    if cpu.engine_encoder in invalid:
        return GpuAssignment(gpu=None, encoder=cpu, action="fail", reason=invalid_settings_reason(invalid))
    return GpuAssignment(gpu=None, encoder=cpu, action="spawn")


def assignment_with_no_candidate(
    spec: EncoderSpec,
    codec: str,
    eligible: list[Gpu],
    gpus: list[Gpu],
    awaiting_probe: Callable[[Gpu], bool],
    invalid: Mapping[str, list[SettingIssue]] | None = None,
) -> GpuAssignment:
    """What to do when no eligible device can be claimed right now: wait for
    a mid-probe device or a pending probe, fall back to CPU for `any_*`
    (unless the preset's settings make the CPU family invalid too), or
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
        return cpu_fallback(codec, invalid or {})
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
