import asyncio
import logging

from arm_common import DiscType
from arm_common.schemas import ScanResult

logger = logging.getLogger("arm_ripper.scan.data")


async def scan_data(device_path: str) -> ScanResult:
    """Last-resort fallback: read the volume label via blkid."""
    proc = await asyncio.create_subprocess_exec(
        "blkid",
        "-o",
        "value",
        "-s",
        "LABEL",
        device_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15.0)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return ScanResult(disc_type=DiscType.UNKNOWN)

    label = stdout.decode(errors="replace").strip() or None
    return ScanResult(disc_type=DiscType.DATA, volume_label=label)
