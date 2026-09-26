"""Per-device encoder probe (spec section 4): a real 2-second test encode per
catalog encoder of the vendor. Verified = exit 0 AND a non-empty output file."""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from arm_common import GpuVendor
from arm_common.encoders import EncoderSpec, gpu_encoders_for_vendor

Runner = Callable[[list[str], float], tuple[int, str]]

CLIP_ARGS = ["-f", "lavfi", "-i", "testsrc2=duration=2:size=320x240:rate=24"]
ENCODE_TIMEOUT_S = 30.0


class ProbeSetupError(Exception):
    pass


def _default_run(argv: list[str], timeout: float) -> tuple[int, str]:
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout:.0f}s"
    except FileNotFoundError as exc:
        return 127, str(exc)
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-5:]
    return proc.returncode, " | ".join(tail)


def probe_command(spec: EncoderSpec, clip: Path, out: Path, device: str) -> list[str]:
    if spec.engine == "ffmpeg_vaapi":
        return [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-vaapi_device",
            device,
            "-i",
            str(clip),
            "-vf",
            "format=nv12,hwupload",
            "-c:v",
            str(spec.engine_encoder),
            "-f",
            "matroska",
            str(out),
        ]
    return ["HandBrakeCLI", "-i", str(clip), "--encoder", str(spec.engine_encoder), "-o", str(out)]


def probe_device(
    vendor: GpuVendor, device: str, *, run: Runner | None = None, workdir: Path | None = None
) -> dict[str, list[str] | dict[str, str]]:
    runner = run or _default_run
    with tempfile.TemporaryDirectory(dir=workdir) as tmp:
        tmpdir = Path(tmp)
        clip = tmpdir / "probe-clip.mkv"
        rc, out = runner(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *CLIP_ARGS, str(clip)], 30.0)
        if rc != 0 or not clip.exists() or clip.stat().st_size == 0:
            raise ProbeSetupError(f"could not generate the test clip: {out}")
        verified: list[str] = []
        errors: dict[str, str] = {}
        for spec in gpu_encoders_for_vendor(vendor):
            target = tmpdir / f"{spec.id}.mkv"
            rc, out = runner(probe_command(spec, clip, target, device), ENCODE_TIMEOUT_S)
            if rc == 0 and target.exists() and target.stat().st_size > 0:
                verified.append(str(spec.codec))
            else:
                errors[spec.id] = out or f"exit {rc}, no output"
        return {"verified": verified, "errors": errors}
