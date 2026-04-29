"""Backend GPU probe — populates the `gpus` table at lifespan startup.

Two probe paths:

- `_probe_dri()` lists `/dev/dri/renderD*` and reads the kernel-exposed PCI
  vendor at `/sys/class/drm/<name>/device/vendor`. Intel (0x8086) → QSV,
  AMD (0x1002) → VAAPI. NVIDIA's Mesa renderD* nodes are skipped — the
  NVENC path covers NVIDIA hardware authoritatively.

- `_probe_nvidia()` shells out to `nvidia-smi -L`; one row per detected
  GPU, `device_path="nvidia://{idx}"`. `FileNotFoundError` (no nvidia-smi
  in the image) and non-zero exit (no driver / no GPU) both yield `[]`.

Encoder kinds are hard-coded per vendor for Phase 7b: VAAPI/QSV/NVENC all
advertise `["h264", "h265"]`. AV1 lands in a follow-up — `encoder_kinds`
is `text[]` so the table absorbs the change without a migration.
"""

from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path
from typing import NamedTuple

from arm_common.enums import GpuVendor

logger = logging.getLogger("arm_backend.gpu_probe")

# All three vendors' modern silicon supports h264 + h265 universally;
# AV1 and VP9 require silicon-generation gating that Phase 7b skips.
_DEFAULT_ENCODER_KINDS: list[str] = ["h264", "h265"]

_PCI_VENDOR_INTEL = "0x8086"
_PCI_VENDOR_AMD = "0x1002"

_NVIDIA_SMI_LINE_RE = re.compile(r"^GPU\s+(\d+):", re.IGNORECASE)


class ProbedGpu(NamedTuple):
    vendor: GpuVendor
    device_path: str
    encoder_kinds: list[str]


def probe_gpus() -> list[ProbedGpu]:
    """Return every GPU detected on the host. Errors degrade to empty results — never raise."""
    found: list[ProbedGpu] = []
    found.extend(_probe_dri())
    found.extend(_probe_nvidia())
    logger.info("gpu probe: %d device(s) detected", len(found))
    return found


def _probe_dri(dri_root: Path = Path("/dev/dri"), sys_root: Path = Path("/sys/class/drm")) -> list[ProbedGpu]:
    if not dri_root.exists():
        return []
    out: list[ProbedGpu] = []
    for render_node in sorted(dri_root.glob("renderD*")):
        vendor_path = sys_root / render_node.name / "device" / "vendor"
        try:
            vendor_id = vendor_path.read_text().strip().lower()
        except OSError as exc:
            logger.warning("gpu probe: could not read %s: %s", vendor_path, exc)
            continue
        if vendor_id == _PCI_VENDOR_INTEL:
            out.append(
                ProbedGpu(
                    vendor=GpuVendor.QSV, device_path=str(render_node), encoder_kinds=list(_DEFAULT_ENCODER_KINDS)
                )
            )
        elif vendor_id == _PCI_VENDOR_AMD:
            out.append(
                ProbedGpu(
                    vendor=GpuVendor.VAAPI, device_path=str(render_node), encoder_kinds=list(_DEFAULT_ENCODER_KINDS)
                )
            )
        else:
            # NVIDIA renderD* may exist via Mesa nouveau; we ignore it because
            # the NVENC path (proprietary driver) is the authoritative source.
            logger.debug("gpu probe: skipping non-Intel/AMD render node %s (vendor=%s)", render_node, vendor_id)
    return out


def _probe_nvidia() -> list[ProbedGpu]:
    try:
        result = subprocess.run(
            ["nvidia-smi", "-L"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError:
        logger.info("gpu probe: nvidia-smi not present, skipping NVENC")
        return []
    except subprocess.TimeoutExpired:
        logger.warning("gpu probe: nvidia-smi timed out")
        return []
    if result.returncode != 0:
        logger.warning("gpu probe: nvidia-smi rc=%d stderr=%s", result.returncode, result.stderr.strip()[:200])
        return []
    out: list[ProbedGpu] = []
    for line in result.stdout.splitlines():
        match = _NVIDIA_SMI_LINE_RE.match(line.strip())
        if match is None:
            continue
        idx = int(match.group(1))
        out.append(
            ProbedGpu(
                vendor=GpuVendor.NVENC,
                device_path=f"nvidia://{idx}",
                encoder_kinds=list(_DEFAULT_ENCODER_KINDS),
            )
        )
    return out
