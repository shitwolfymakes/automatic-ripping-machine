import asyncio
import logging

from arm_common import DiscType
from arm_common.schemas import ScanResult
from arm_ripper.source import is_iso_source

logger = logging.getLogger("arm_ripper.scan.data")


# How much of an image to read when sniffing for a video disc layout. The UDF
# directory tree of a Blu-ray or DVD image sits near the start of the image
# (the metadata partition of a UDF 2.5 BD-R backup lands within the first few
# MB), so 64 MB is plenty and reads in well under a second from local disk.
_SNIFF_BYTES = 64 * 1024 * 1024

# Directory names that only a video disc carries, in both encodings UDF uses
# for file identifiers (8-bit compressed and UTF-16BE) plus plain ISO 9660.
_VIDEO_SIGNATURES: tuple[tuple[str, DiscType], ...] = (("BDMV", DiscType.BLURAY), ("VIDEO_TS", DiscType.DVD))


def sniff_video_image(path: str) -> DiscType | None:
    """Classify an image MakeMKV could not open by the directory names it carries.

    A Blu-ray or DVD image that makemkvcon crashes on (seen with a DVDFab
    UDF 2.50 backup: full BDMV tree, makemkvcon exits with SIGSEGV) must not
    be filed as a data disc: that hides the title search on the job page and
    routes it to the data-copy session. Returns BLURAY, DVD, or None when no
    video-disc directory name appears in the first 64 MB.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(_SNIFF_BYTES)
    except OSError:
        return None
    for name, kind in _VIDEO_SIGNATURES:
        if name.encode("ascii") in head or name.encode("utf-16-be") in head:
            return kind
    return None


async def scan_data(device_path: str) -> ScanResult:
    """Last-resort fallback: read the volume label via blkid.

    For an ISO source the image is also sniffed for a Blu-ray/DVD directory
    layout, so an image MakeMKV cannot open still becomes a video job (with no
    titles) rather than a data disc.
    """
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
    if is_iso_source(device_path):
        kind = await asyncio.to_thread(sniff_video_image, device_path)
        if kind is not None:
            logger.info(
                "image %s carries a %s layout; classifying as %s with no titles", device_path, kind.value, kind.value
            )
            return ScanResult(disc_type=kind, volume_label=label)
    return ScanResult(disc_type=DiscType.DATA, volume_label=label)
