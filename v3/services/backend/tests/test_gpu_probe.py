"""Tests for the Backend startup GPU probe.

The probe walks `/dev/dri/renderD*` for VAAPI/QSV and shells out to
`nvidia-smi -L` for NVENC. Both paths are mocked end-to-end here so the
test passes on any CI host regardless of real GPU presence.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.gpu_probe import probe_gpus  # noqa: E402
from arm_common.enums import GpuVendor  # noqa: E402


def _fake_dri(tmp_path: Path, vendors: list[tuple[str, str]]) -> tuple[Path, Path]:
    """Build a minimal /dev/dri + /sys/class/drm tree under tmp_path.

    `vendors` is a list of `(render_node_basename, pci_vendor_id_lowercase)`,
    e.g. `[("renderD128", "0x8086"), ("renderD129", "0x1002")]`.
    """
    dri_root = tmp_path / "dri"
    dri_root.mkdir()
    sys_root = tmp_path / "sys-class-drm"
    sys_root.mkdir()
    for name, vendor_id in vendors:
        (dri_root / name).touch()
        node_dir = sys_root / name / "device"
        node_dir.mkdir(parents=True)
        (node_dir / "vendor").write_text(f"{vendor_id}\n")
    return dri_root, sys_root


def test_probe_empty_host_returns_empty(tmp_path: Path) -> None:
    """No /dev/dri, no nvidia-smi → []."""
    nonexistent_dri = tmp_path / "no-dri"
    nonexistent_sys = tmp_path / "no-sys"
    with (
        patch("arm_backend.gpu_probe._probe_dri", lambda: []),
        patch(
            "arm_backend.gpu_probe.subprocess.run",
            side_effect=FileNotFoundError("nvidia-smi"),
        ),
    ):
        result = probe_gpus()
    assert result == []
    # And the dri probe with a missing dri root yields []
    from arm_backend.gpu_probe import _probe_dri

    assert _probe_dri(dri_root=nonexistent_dri, sys_root=nonexistent_sys) == []


def test_probe_dri_vaapi_only(tmp_path: Path) -> None:
    """AMD render node → one VAAPI row with h264+h265."""
    dri_root, sys_root = _fake_dri(tmp_path, [("renderD128", "0x1002")])
    from arm_backend.gpu_probe import _probe_dri

    rows = _probe_dri(dri_root=dri_root, sys_root=sys_root)
    assert len(rows) == 1
    row = rows[0]
    assert row.vendor == GpuVendor.VAAPI
    assert row.device_path == str(dri_root / "renderD128")
    assert "h264" in row.encoder_kinds
    assert "h265" in row.encoder_kinds


def test_probe_dri_qsv_and_nvenc_mix(tmp_path: Path) -> None:
    """Intel iGPU + an NVIDIA card detected through both paths."""
    dri_root, sys_root = _fake_dri(
        tmp_path,
        [
            ("renderD128", "0x8086"),  # Intel iGPU → QSV
            ("renderD129", "0x10de"),  # NVIDIA via Mesa → skipped (NVENC handles it)
        ],
    )
    from arm_backend.gpu_probe import _probe_dri

    dri_rows = _probe_dri(dri_root=dri_root, sys_root=sys_root)
    assert len(dri_rows) == 1
    assert dri_rows[0].vendor == GpuVendor.QSV

    # Now stub nvidia-smi with a 2-GPU host.
    fake_proc = subprocess.CompletedProcess(
        args=["nvidia-smi", "-L"],
        returncode=0,
        stdout="GPU 0: NVIDIA GeForce RTX 4090 (UUID: GPU-1)\nGPU 1: NVIDIA GeForce RTX 4080 (UUID: GPU-2)\n",
        stderr="",
    )
    with (
        patch("arm_backend.gpu_probe._probe_dri", return_value=dri_rows),
        patch("arm_backend.gpu_probe.subprocess.run", return_value=fake_proc),
    ):
        all_rows = probe_gpus()
    assert len(all_rows) == 3  # 1 QSV + 2 NVENC
    nvenc_rows = [r for r in all_rows if r.vendor == GpuVendor.NVENC]
    assert len(nvenc_rows) == 2
    assert {r.device_path for r in nvenc_rows} == {"nvidia://0", "nvidia://1"}


def test_probe_nvidia_smi_missing() -> None:
    """No nvidia-smi binary → empty NVENC list, no exception."""
    from arm_backend.gpu_probe import _probe_nvidia

    with patch("arm_backend.gpu_probe.subprocess.run", side_effect=FileNotFoundError("nvidia-smi")):
        result = _probe_nvidia()
    assert result == []


def test_probe_nvidia_smi_nonzero_exit() -> None:
    """nvidia-smi present but no driver → empty NVENC list."""
    from arm_backend.gpu_probe import _probe_nvidia

    fake_proc = subprocess.CompletedProcess(
        args=["nvidia-smi", "-L"],
        returncode=9,
        stdout="",
        stderr="NVIDIA-SMI has failed because it couldn't communicate with the NVIDIA driver.\n",
    )
    with patch("arm_backend.gpu_probe.subprocess.run", return_value=fake_proc):
        result = _probe_nvidia()
    assert result == []
