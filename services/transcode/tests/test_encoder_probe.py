"""Encoder-capability probe: HandBrake --help text -> {vendor: [codecs]}."""

from __future__ import annotations

from arm_transcode.encoder_probe import parse_handbrake_encoders, probe_encoders

# Minimal shape of HandBrakeCLI --help's encoder enumeration. HandBrake lists a
# HW encoder token ONLY when its runtime library loads at probe time, so the
# enumeration is itself capability-accurate (verified against the real image:
# an N97 without --device passthrough shows no qsv tokens; NVENC needs --gpus).
_HELP_N97 = """
   --encoder <string>  Select video encoder:
                            x264 x265 qsv_h264 mpeg4
"""
_HELP_FULL_NVENC = """
   --encoder <string>  Select video encoder:
                            x264 nvenc_h264 nvenc_h265
"""


def test_parse_qsv_h264_only() -> None:
    # N97: qsv_h264 present, qsv_h265 absent -> qsv gets h264 only, no h265 over-claim.
    caps = parse_handbrake_encoders(_HELP_N97)
    assert caps == {"qsv": ["h264"]}


def test_parse_nvenc_h264_h265() -> None:
    caps = parse_handbrake_encoders(_HELP_FULL_NVENC)
    assert caps == {"nvenc": ["h264", "h265"]}


def test_parse_empty_help_is_empty() -> None:
    assert parse_handbrake_encoders("no encoders here") == {}


def test_probe_encoders_swallows_errors() -> None:
    def boom() -> str:
        raise OSError("HandBrakeCLI not found")

    assert probe_encoders(run_help=boom) == {}


def test_probe_encoders_uses_injected_help() -> None:
    caps = probe_encoders(run_help=lambda: _HELP_FULL_NVENC)
    assert caps == {"nvenc": ["h264", "h265"]}
