import logging

from arm_common import DiscType, IsoPreparePhase
from arm_common.schemas import ScanResult

from arm_ripper import iso_extract, prepare
from arm_ripper.scan.data import scan_data
from arm_ripper.scan.makemkv import ScanError, scan_disc as scan_makemkv
from arm_ripper.scan.musicbrainz_disc import scan_cd
from arm_ripper.source import is_iso_source

logger = logging.getLogger("arm_ripper.scan")

__all__ = ["ScanError", "scan"]


async def _scan_extracted(device_path: str) -> ScanResult | None:
    """MakeMKV listed no titles from the image itself: unpack it (`iso_extract`)
    and scan the disc folder instead. None, with the extraction removed, when
    the image can't be unpacked or the folder has no titles either."""
    if await iso_extract.extract(device_path) is None:
        return None
    await prepare.report(IsoPreparePhase.SCANNING)
    try:
        result: ScanResult | None = await scan_makemkv(device_path)
    except ScanError as e:
        logger.warning("makemkv scan of the extracted image failed device=%s err=%s", device_path, e)
        result = None
    if result is None or not result.titles:
        logger.warning("extracted image %s has no titles either; dropping the extraction", device_path)
        iso_extract.discard_all()
        return None
    # MakeMKV names a folder source after the folder; the image's own volume
    # label is what a directly-read ISO (or the disc) would have reported.
    label = (await scan_data(device_path)).volume_label
    if label:
        result = result.model_copy(update={"volume_label": label})
    logger.info(
        "scan complete device=%s via extracted folder disc_type=%s volume=%s titles=%d",
        device_path,
        result.disc_type.value,
        result.volume_label,
        len(result.titles),
    )
    return result


async def scan(device_path: str) -> ScanResult:
    """Heuristic disc scan: MakeMKV first, fall back to MusicBrainz disc-id, then data.

    An ISO ripper reports this as its "preparing" phase (`prepare`, a no-op
    for a physical drive) until the scan is done and identify takes over."""
    await prepare.report(IsoPreparePhase.SCANNING)
    try:
        return await _scan(device_path)
    finally:
        await prepare.finish()


async def _scan(device_path: str) -> ScanResult:
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

    if is_iso_source(device_path):
        rescued = await _scan_extracted(device_path)
        if rescued is not None:
            return rescued

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
