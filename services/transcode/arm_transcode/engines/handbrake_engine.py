"""HandBrake engine: turns a selected `EncoderSpec` into the `--encoder`
args `transcode_handbrake` appends after `--preset`."""

from __future__ import annotations

from arm_common.encoders import EncoderSpec


def encoder_args(spec: EncoderSpec | None) -> list[str]:
    if spec is None or spec.kind == "preset" or spec.engine != "handbrake" or not spec.engine_encoder:
        return []
    return ["--encoder", spec.engine_encoder]
