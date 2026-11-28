import logging

from arm_common import DiscType, IsoPreparePhase
from arm_common.schemas import ScanResult

from arm_ripper import iso_extract, prepare
from arm_ripper.scan.bd_structure import BdStructure, scan_structure
from arm_ripper.scan.data import scan_data
from arm_ripper.scan.disc_probe import probe_disc
from arm_ripper.scan.makemkv import MakemkvScanFailed, ScanError, disc_fingerprints, scan_disc as scan_makemkv
from arm_ripper.scan.musicbrainz_disc import scan_cd
from arm_ripper.source import is_iso_source

logger = logging.getLogger("arm_ripper.scan")

__all__ = ["MakemkvScanFailed", "ScanError", "scan"]


async def _scan_extracted(device_path: str, min_title_length_seconds: int) -> ScanResult | None:
    """MakeMKV listed no titles from the image itself: unpack it (`iso_extract`)
    and scan the disc folder instead. None, with the extraction removed, when
    the image can't be unpacked or the folder has no titles either."""
    if await iso_extract.extract(device_path) is None:
        return None
    await prepare.report(IsoPreparePhase.SCANNING)
    try:
        result: ScanResult | None = await scan_makemkv(device_path, min_title_length_seconds)
    except ScanError as e:
        logger.warning("makemkv scan of the extracted image failed device=%s err=%s", device_path, e)
        result = None
    if result is None or not result.titles:
        logger.warning("extracted image %s has no titles either; dropping the extraction", device_path)
        await iso_extract.discard_all()
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


async def _scan_structure_first(device_path: str, structure: BdStructure, min_title_length_seconds: int) -> ScanResult:
    """A Blu-ray scan from the disc's structure alone: the playlists and clips, the disc probe's fingerprints and
    BDMT name, and the volume label. No MakeMKV titles: `makemkvcon info` runs afterwards (arm_ripper.titles_read),
    down to `min_title_length_seconds`, which the scan records as the minimum it lists titles with.
    """
    probe = await probe_disc(device_path, bluray=True)
    label = (await scan_data(device_path)).volume_label
    logger.info(
        "scan complete device=%s via structure disc_type=bluray volume=%s playlists=%d",
        device_path,
        label,
        len(structure.playlists),
    )
    return ScanResult(
        disc_type=DiscType.BLURAY,
        volume_label=label,
        fingerprints=disc_fingerprints(probe),
        bd_meta=probe.bd_meta,
        playlists=structure.playlists,
        clips=structure.clips,
        min_title_length_seconds=min_title_length_seconds,
    )


async def scan(device_path: str, min_title_length_seconds: int) -> ScanResult:
    """Heuristic disc scan: a Blu-ray's structure first, then MakeMKV (listing titles down to
    `min_title_length_seconds`), then MusicBrainz disc-id, then data.

    An ISO ripper reports this as its "preparing" phase (`prepare`, a no-op
    for a physical drive) until the scan is done and identify takes over."""
    await prepare.report(IsoPreparePhase.SCANNING)
    try:
        return await _scan(device_path, min_title_length_seconds)
    finally:
        await prepare.finish()


async def _makemkv_or_failure(device_path: str, min_title_length_seconds: int) -> ScanResult | MakemkvScanFailed | None:
    """MakeMKV's scan; its typed failure when it ran and failed (the caller decides what that means), None when
    it could not run at all."""
    try:
        return await scan_makemkv(device_path, min_title_length_seconds)
    except MakemkvScanFailed as e:
        logger.info("makemkv scan failed device=%s reason=%s err=%s", device_path, e.reason.value, e)
        return e
    except ScanError as e:
        logger.info("makemkv scan failed device=%s err=%s", device_path, e)
        return None


async def _fallback(device_path: str, mkv_result: ScanResult | MakemkvScanFailed | None) -> ScanResult:
    """What a disc that is neither MakeMKV-readable nor an audio CD is.

    A MakeMKV failure on a video disc (undecryptable, unopenable, timed out, expired) is re-raised: such a disc
    is never a data disc, so it must not reach blkid or the data-copy rip. Only a scan that ran and found
    nothing (or could not run) falls back to the volume label.
    """
    if isinstance(mkv_result, MakemkvScanFailed):
        raise mkv_result

    data = await scan_data(device_path)
    if mkv_result is not None:
        # makemkv ran but found nothing rippable — promote to DATA via blkid for label.
        if data.volume_label:
            return data
        return ScanResult(disc_type=DiscType.UNKNOWN, volume_label=mkv_result.volume_label)

    logger.info(
        "scan complete device=%s disc_type=%s volume=%s",
        device_path,
        data.disc_type.value,
        data.volume_label,
    )
    return data


async def _scan(device_path: str, min_title_length_seconds: int) -> ScanResult:
    structure = await scan_structure(device_path)
    if structure.playlists:
        return await _scan_structure_first(device_path, structure, min_title_length_seconds)

    result = await _makemkv_or_failure(device_path, min_title_length_seconds)

    if isinstance(result, ScanResult) and result.titles:
        if result.disc_type == DiscType.BLURAY:
            logger.info("scan: no playlists read; blu-ray titles from makemkv structure_source=makemkv")
        logger.info(
            "scan complete device=%s disc_type=%s volume=%s titles=%d",
            device_path,
            result.disc_type.value,
            result.volume_label,
            len(result.titles),
        )
        return result

    if is_iso_source(device_path):
        rescued = await _scan_extracted(device_path, min_title_length_seconds)
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

    return await _fallback(device_path, result)
