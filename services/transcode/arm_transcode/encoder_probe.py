"""Probe which HardWare encoders HandBrakeCLI in THIS image can actually run.

Runs at install time (via `python -m arm_transcode.main --probe-encoders`) so
`detect_gpus` can set ARM_GPUS[].encoder_kinds to real capability instead of a
hardcoded ["h264","h265"] — the source of the N97 QSV h265 over-claim (rc=3).

Token names come from a local (vendor, codec) -> HandBrake `--encoder` token
mapping derived from the shared catalog (`arm_common.encoders.ENCODERS`); a
token is "supported" when it appears as a whole word in `HandBrakeCLI --help`'s
encoder enumeration. This module is a temporary bridge — a later task removes
it once the catalog's own probe-based eligibility replaces it.
"""

from __future__ import annotations

import logging
import re
import subprocess
from collections.abc import Callable

from arm_common.encoders import ENCODERS

logger = logging.getLogger("arm_transcode.encoder_probe")

# Codec display order in each vendor's list (matches the VideoCodec enum order).
_CODEC_ORDER = ("h264", "h265", "av1")

# Local copy of the catalog's (vendor, codec) -> HandBrake `--encoder` token
# mapping, restricted to the GPU/handbrake specs. Task 4 deletes this module.
_HW_ENCODER_TABLE: dict[tuple[str, str], str] = {
    (s.vendor.value, s.codec): s.engine_encoder
    for s in ENCODERS.values()
    if s.kind == "gpu"
    and s.engine == "handbrake"
    and s.vendor is not None
    and s.codec is not None
    and s.engine_encoder is not None
}


def parse_handbrake_encoders(help_text: str) -> dict[str, list[str]]:
    """Map HandBrakeCLI --help text -> {vendor: [codec, ...]} for supported HW tokens."""
    present: set[str] = set()
    for (vendor, codec), token in _HW_ENCODER_TABLE.items():
        if re.search(rf"(?<![\w-]){re.escape(token)}(?![\w-])", help_text):
            present.add(f"{vendor}:{codec}")
    caps: dict[str, list[str]] = {}
    for vendor, codec in _HW_ENCODER_TABLE:
        if f"{vendor}:{codec}" in present:
            caps.setdefault(vendor, [])
    for vendor in caps:
        caps[vendor] = [c for c in _CODEC_ORDER if f"{vendor}:{c}" in present]
    return caps


def _run_handbrake_help() -> str:
    proc = subprocess.run(
        ["HandBrakeCLI", "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    # HandBrake prints --help to stderr on some builds; concatenate both.
    return f"{proc.stdout}\n{proc.stderr}"


def probe_encoders(run_help: Callable[[], str] | None = None) -> dict[str, list[str]]:
    """Return {vendor: [codecs]} HandBrake supports, or {} on any error."""
    runner = run_help or _run_handbrake_help
    try:
        return parse_handbrake_encoders(runner())
    except Exception as exc:  # best-effort: any failure -> empty -> caller falls back
        logger.warning("encoder probe failed: %s", exc)
        return {}
