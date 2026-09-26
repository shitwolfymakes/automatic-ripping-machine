"""Unit tests for arm_transcode.device_probe (fake runner only; no real ffmpeg/HandBrake)."""

from __future__ import annotations

from pathlib import Path

import pytest

from arm_common import GpuVendor
from arm_common.encoders import get_encoder
from arm_transcode.device_probe import ProbeSetupError, probe_command, probe_device


class FakeRunner:
    def __init__(self, fail_for: set[str] = frozenset(), clip_rc: int = 0):
        self.fail_for, self.clip_rc, self.calls = fail_for, clip_rc, []

    def __call__(self, argv, timeout):
        self.calls.append(argv)
        out = Path(argv[-1])
        if argv[0] == "ffmpeg" and "lavfi" in argv:
            if self.clip_rc == 0:
                out.write_bytes(b"clip")
            return self.clip_rc, "clip"
        token = next((a for a in argv if a in self.fail_for), None)
        if token:
            return 1, f"{token} failed: no device"
        out.write_bytes(b"encoded")
        return 0, ""


def test_qsv_all_verified(tmp_path):
    r = probe_device(GpuVendor.QSV, "/dev/dri/renderD129", run=FakeRunner(), workdir=tmp_path)
    assert r == {"verified": ["h264", "h265", "av1"], "errors": {}}


def test_partial_verification(tmp_path):
    r = probe_device(GpuVendor.QSV, "/dev/dri/renderD129", run=FakeRunner(fail_for={"qsv_av1"}), workdir=tmp_path)
    assert r["verified"] == ["h264", "h265"]
    assert "qsv_av1" in r["errors"]


def test_vaapi_uses_ffmpeg(tmp_path):
    runner = FakeRunner()
    probe_device(GpuVendor.VAAPI, "/dev/dri/renderD128", run=runner, workdir=tmp_path)
    encode_calls = [c for c in runner.calls if "lavfi" not in c]
    assert all(c[0] == "ffmpeg" for c in encode_calls)
    assert any("hevc_vaapi" in c for c in encode_calls)


def test_empty_output_is_not_verified(tmp_path):
    class EmptyOut(FakeRunner):
        def __call__(self, argv, timeout):
            if "lavfi" in argv:
                return super().__call__(argv, timeout)
            return 0, ""  # exit 0 but no file written

    r = probe_device(GpuVendor.NVENC, "nvidia://0", run=EmptyOut(), workdir=tmp_path)
    assert r["verified"] == [] and set(r["errors"]) == {"nvenc_h264", "nvenc_h265", "nvenc_av1"}


def test_clip_failure_raises(tmp_path):
    with pytest.raises(ProbeSetupError):
        probe_device(GpuVendor.QSV, "/dev/dri/renderD129", run=FakeRunner(clip_rc=1), workdir=tmp_path)


def test_handbrake_test_command_shape(tmp_path):
    cmd = probe_command(get_encoder("nvenc_h265"), tmp_path / "c.mkv", tmp_path / "o.mkv", "nvidia://0")
    assert cmd[0] == "HandBrakeCLI" and cmd[cmd.index("--encoder") + 1] == "nvenc_h265"
