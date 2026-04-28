import logging

from arm_common import DiscType
from arm_common.schemas import ScanResult

from arm_ripper.scan.data import scan_data
from arm_ripper.scan.makemkv import ScanError, scan_disc as scan_makemkv
from arm_ripper.scan.musicbrainz_disc import scan_cd

logger = logging.getLogger("arm_ripper.scan")

__all__ = ["ScanError", "scan"]


async def scan(device_path: str) -> ScanResult:
    """Heuristic disc scan: MakeMKV first, fall back to MusicBrainz disc-id, then data."""
    try:
        result = await scan_makemkv(device_path)
    except ScanError as e:
        logger.info("makemkv scan failed device=%s err=%s", device_path, e)
        result = None

    if result is not None and result.titles:
        logger.info(
            "scan complete device=%s disc_type=%s volume=%s titles=%d",
            device_path,
            result.disc_type.value,
            result.volume_label,
            len(result.titles),
        )
        return result

    cd = await scan_cd(device_path)
    if cd is not None:
        logger.info(
            "scan complete device=%s disc_type=cd disc_id=%s tracks=%s",
            device_path,
            cd.musicbrainz_disc_id,
            cd.raw.get("track_count"),
        )
        return cd

    if result is not None:
        # makemkv ran but found nothing rippable — promote to DATA via blkid for label.
        data = await scan_data(device_path)
        if data.volume_label:
            return data
        return ScanResult(disc_type=DiscType.UNKNOWN, volume_label=result.volume_label)

    data = await scan_data(device_path)
    logger.info(
        "scan complete device=%s disc_type=%s volume=%s",
        device_path,
        data.disc_type.value,
        data.volume_label,
    )
    return data
