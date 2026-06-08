"""Full branch coverage for gpu_probe: _probe_dri vendor mapping + the
unreadable-vendor OSError path, and _probe_nvidia's FileNotFound /
timeout / non-zero-rc / line-parse paths.
"""

from __future__ import annotations

import os
import subprocess

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from arm_backend import gpu_probe  # noqa: E402
from arm_backend.gpu_probe import _probe_dri, _probe_nvidia, probe_gpus  # noqa: E402
from arm_common.enums import GpuVendor  # noqa: E402


def _make_dri(tmp: Path, nodes: dict[str, str | None]) -> tuple[Path, Path]:
    """Build a fake /dev/dri + /sys/class/drm. `nodes` maps renderD name ->
    vendor id string, or None to omit the vendor file (triggers OSError)."""
    dri = tmp / "dri"
    sysroot = tmp / "drm"
    dri.mkdir()
    for name, vendor in nodes.items():
        (dri / name).write_text("")
        devdir = sysroot / name / "device"
        devdir.mkdir(parents=True)
        if vendor is not None:
            (devdir / "vendor").write_text(vendor + "\n")
    return dri, sysroot


def test_probe_dri_missing_root_returns_empty(tmp_path: Path) -> None:
    assert _probe_dri(tmp_path / "nope", tmp_path / "sys") == []


def test_probe_dri_maps_intel_and_amd_and_skips_other(tmp_path: Path) -> None:
    dri, sysroot = _make_dri(
        tmp_path,
        {"renderD128": "0x8086", "renderD129": "0x1002", "renderD130": "0x10de"},
    )
    out = _probe_dri(dri, sysroot)
    vendors = {g.device_path: g.vendor for g in out}
    assert vendors[str(dri / "renderD128")] == GpuVendor.QSV
    assert vendors[str(dri / "renderD129")] == GpuVendor.VAAPI
    assert not any("renderD130" in g.device_path for g in out)  # nvidia mesa skipped


def test_probe_dri_unreadable_vendor_is_skipped(tmp_path: Path) -> None:
    dri, sysroot = _make_dri(tmp_path, {"renderD128": None})  # no vendor file → OSError
    assert _probe_dri(dri, sysroot) == []


class _CompletedProcess:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_probe_nvidia_not_present(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*_a: object, **_k: object) -> None:
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", _raise)
    assert _probe_nvidia() == []


def test_probe_nvidia_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*_a: object, **_k: object) -> None:
        raise subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=5)

    monkeypatch.setattr(subprocess, "run", _raise)
    assert _probe_nvidia() == []


def test_probe_nvidia_nonzero_rc(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _CompletedProcess(9, stderr="no devices"))
    assert _probe_nvidia() == []


def test_probe_nvidia_parses_lines_and_skips_noise(monkeypatch: pytest.MonkeyPatch) -> None:
    stdout = "GPU 0: NVIDIA RTX (UUID: x)\nnot-a-gpu-line\nGPU 1: NVIDIA A40 (UUID: y)\n"
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _CompletedProcess(0, stdout=stdout))
    out = _probe_nvidia()
    assert [g.device_path for g in out] == ["nvidia://0", "nvidia://1"]
    assert all(g.vendor == GpuVendor.NVENC for g in out)


def test_probe_gpus_combines(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    dri, sysroot = _make_dri(tmp_path, {"renderD128": "0x8086"})
    monkeypatch.setattr(gpu_probe, "_probe_dri", lambda: _probe_dri(dri, sysroot))
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _CompletedProcess(0, stdout="GPU 0: X\n"))
    out = probe_gpus()
    assert {g.vendor for g in out} == {GpuVendor.QSV, GpuVendor.NVENC}
