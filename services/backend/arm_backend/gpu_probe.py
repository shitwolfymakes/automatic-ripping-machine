"""Backend GPU inventory — populates the `gpus` table at lifespan startup.

The backend no longer probes hardware. GPU detection happens **host-side at
install time** (`install.sh` / `devtools/setup-dev.sh` enumerate `/dev/dri`
render nodes and `nvidia-smi`), and the result is handed to the backend as a
JSON descriptor in the `ARM_GPUS` env var. This keeps the backend image
GPU-free (no `nvidia-smi`, no `/dev/dri` mount, no NVIDIA runtime) — the only
container that needs GPU access is the ephemeral transcoder, and the dispatcher
injects that per-task.

`ARM_GPUS` is a JSON array of objects matching `ProbedGpu`:

    [{"vendor": "qsv",   "device_path": "/dev/dri/renderD128", "encoder_kinds": ["h264", "h265"]},
     {"vendor": "nvenc", "device_path": "nvidia://0",          "encoder_kinds": ["h264", "h265"]}]

`encoder_kinds` is optional per entry and defaults to `["h264", "h265"]`.
Parsing degrades to an empty list on any malformed input — a misconfigured
descriptor yields "no GPU" (CPU transcoding) rather than a crash.
"""

from __future__ import annotations

import json
import logging
from typing import NamedTuple

from arm_common.enums import GpuVendor

logger = logging.getLogger("arm_backend.gpu_probe")

# All three vendors' modern silicon supports h264 + h265 universally;
# AV1 and VP9 require silicon-generation gating that Phase 7b skips.
_DEFAULT_ENCODER_KINDS: list[str] = ["h264", "h265"]


class ProbedGpu(NamedTuple):
    vendor: GpuVendor
    device_path: str
    encoder_kinds: list[str]


def load_configured_gpus(raw: str | None) -> list[ProbedGpu]:
    """Parse the install-provided `ARM_GPUS` JSON descriptor.

    Returns every well-formed GPU entry. Malformed top-level JSON yields `[]`;
    individual malformed entries are skipped with a warning. Never raises.
    """
    if not raw or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError) as exc:
        logger.warning("ARM_GPUS is not valid JSON, treating as no-GPU: %s", exc)
        return []
    if not isinstance(parsed, list):
        logger.warning("ARM_GPUS must be a JSON array, got %s — treating as no-GPU", type(parsed).__name__)
        return []

    out: list[ProbedGpu] = []
    for entry in parsed:
        gpu = _parse_entry(entry)
        if gpu is not None:
            out.append(gpu)
    logger.info("gpu inventory: %d device(s) configured via ARM_GPUS", len(out))
    return out


def _parse_entry(entry: object) -> ProbedGpu | None:
    if not isinstance(entry, dict):
        logger.warning("ARM_GPUS entry is not an object, skipping: %r", entry)
        return None
    raw_vendor = entry.get("vendor")
    if not isinstance(raw_vendor, str):
        logger.warning("ARM_GPUS entry has non-string vendor %r, skipping", raw_vendor)
        return None
    try:
        vendor = GpuVendor(raw_vendor)
    except ValueError:
        logger.warning("ARM_GPUS entry has unknown vendor %r, skipping", raw_vendor)
        return None
    device_path = entry.get("device_path")
    if not isinstance(device_path, str) or not device_path:
        logger.warning("ARM_GPUS entry (vendor=%s) missing device_path, skipping", vendor.value)
        return None
    encoder_kinds = entry.get("encoder_kinds")
    if not (isinstance(encoder_kinds, list) and all(isinstance(k, str) for k in encoder_kinds) and encoder_kinds):
        encoder_kinds = list(_DEFAULT_ENCODER_KINDS)
    return ProbedGpu(vendor=vendor, device_path=device_path, encoder_kinds=encoder_kinds)
