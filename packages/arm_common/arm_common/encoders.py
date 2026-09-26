"""Encoder catalog: the single source of truth for what a transcode preset can
ask for. The worker, dispatcher, API and UI all read this module; nothing else
may hard-code encoder ids or HandBrake/ffmpeg encoder names."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from arm_common.enums import GpuVendor, TranscodeTool

if TYPE_CHECKING:
    from arm_common.models import Gpu

Engine = Literal["handbrake", "ffmpeg_vaapi"]
Kind = Literal["preset", "cpu", "any", "gpu"]

PRESET_ENCODER_ID = "preset"


@dataclass(frozen=True)
class EncoderSpec:
    id: str
    engine: Engine
    engine_encoder: str | None
    kind: Kind
    vendor: GpuVendor | None
    codec: str | None
    label: str


_CODECS = ("h264", "h265", "av1")
_CODEC_LABEL = {"h264": "H.264", "h265": "H.265", "av1": "AV1"}
_CPU_ENGINE_ENCODER = {"h264": "x264", "h265": "x265", "av1": "svt_av1"}
_VAAPI_ENGINE_ENCODER = {"h264": "h264_vaapi", "h265": "hevc_vaapi", "av1": "av1_vaapi"}
_VENDOR_LABEL = {GpuVendor.QSV: "Intel QSV", GpuVendor.NVENC: "NVIDIA NVENC", GpuVendor.VAAPI: "AMD VAAPI"}

VENDOR_RANK: dict[GpuVendor, int] = {GpuVendor.NVENC: 0, GpuVendor.QSV: 1, GpuVendor.VAAPI: 2}


def _build() -> dict[str, EncoderSpec]:
    specs: list[EncoderSpec] = [
        EncoderSpec(PRESET_ENCODER_ID, "handbrake", None, "preset", None, None, "HandBrake preset's own encoder"),
    ]
    for c in _CODECS:
        specs.append(
            EncoderSpec(f"cpu_{c}", "handbrake", _CPU_ENGINE_ENCODER[c], "cpu", None, c, f"CPU {_CODEC_LABEL[c]}")
        )
    for c in _CODECS:
        specs.append(EncoderSpec(f"any_{c}", "handbrake", None, "any", None, c, f"Any GPU {_CODEC_LABEL[c]}"))
    for vendor, prefix in ((GpuVendor.QSV, "qsv"), (GpuVendor.NVENC, "nvenc")):
        for c in _CODECS:
            specs.append(
                EncoderSpec(
                    f"{prefix}_{c}",
                    "handbrake",
                    f"{prefix}_{c}",
                    "gpu",
                    vendor,
                    c,
                    f"{_VENDOR_LABEL[vendor]} {_CODEC_LABEL[c]}",
                )
            )
    for c in _CODECS:
        specs.append(
            EncoderSpec(
                f"vaapi_{c}",
                "ffmpeg_vaapi",
                _VAAPI_ENGINE_ENCODER[c],
                "gpu",
                GpuVendor.VAAPI,
                c,
                f"{_VENDOR_LABEL[GpuVendor.VAAPI]} {_CODEC_LABEL[c]}",
            )
        )
    return {s.id: s for s in specs}


ENCODERS: dict[str, EncoderSpec] = _build()


def get_encoder(encoder_id: str) -> EncoderSpec:
    try:
        return ENCODERS[encoder_id]
    except KeyError:
        raise ValueError(f"unknown encoder: {encoder_id!r}") from None


def encoder_allowed_for_tool(encoder_id: str, tool: TranscodeTool) -> bool:
    if encoder_id not in ENCODERS:
        return False
    if tool == TranscodeTool.HANDBRAKE:
        return True
    return encoder_id == PRESET_ENCODER_ID


def gpu_encoders_for_vendor(vendor: GpuVendor) -> list[EncoderSpec]:
    return [s for s in ENCODERS.values() if s.kind == "gpu" and s.vendor == vendor]


def cpu_encoder_for(codec: str) -> EncoderSpec:
    return get_encoder(f"cpu_{codec}")


def gpu_encoder_for(vendor: GpuVendor, codec: str) -> EncoderSpec | None:
    for s in gpu_encoders_for_vendor(vendor):
        if s.codec == codec:
            return s
    return None


def gpu_is_eligible(gpu: Gpu, codec: str) -> bool:
    """The one eligibility rule (spec section 4): enabled, probed, and the probe
    verified this codec."""
    return bool(gpu.enabled) and gpu.probed_at is not None and codec in (gpu.encoder_kinds or [])
