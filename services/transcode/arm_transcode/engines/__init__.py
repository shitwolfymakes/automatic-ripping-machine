"""Engine seam: which encoder the dispatcher asked for, and how each engine
runs it. The catalog (arm_common.encoders) decides the engine."""

from __future__ import annotations

import os

from arm_common import GpuVendor
from arm_common.encoders import EncoderSpec, get_encoder, gpu_encoder_for


def selected_encoder() -> EncoderSpec | None:
    encoder_id = os.environ.get("ARM_TRANSCODE_ENCODER")
    if encoder_id:
        spec = get_encoder(encoder_id)
        return None if spec.kind == "preset" else spec
    # Legacy contract (one release): an older backend sends only vendor + codec.
    vendor, codec = os.environ.get("ARM_GPU_VENDOR"), os.environ.get("ARM_GPU_CODEC")
    if not vendor or not codec:
        return None
    try:
        legacy_spec = gpu_encoder_for(GpuVendor(vendor), codec)
    except ValueError:
        return None
    return legacy_spec if legacy_spec is not None and legacy_spec.engine == "handbrake" else None
