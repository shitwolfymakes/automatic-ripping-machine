import asyncio
import logging

from arm_common import DiscType
from arm_common.schemas import ScanResult

logger = logging.getLogger("arm_ripper.scan.musicbrainz_disc")


async def scan_cd(device_path: str) -> ScanResult | None:
    """Compute a MusicBrainz Disc ID for an audio CD using libdiscid.

    Returns None if libdiscid is unavailable or the device contains no audio
    tracks (e.g. a DVD pretending to be a disc). All disc-id work is
    blocking C, so we run it in a thread.
    """
    try:
        import discid  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("python-discid not installed; CD identification skipped")
        return None

    def _read() -> tuple[str, int] | None:
        try:
            with discid.read(device_path) as disc:
                return disc.id, len(disc.tracks)
        except Exception as e:  # libdiscid raises a bare DiscError
            logger.info("discid read failed device=%s err=%s", device_path, e)
            return None

    result = await asyncio.to_thread(_read)
    if result is None:
        return None
    disc_id, track_count = result
    if track_count == 0:
        return None

    return ScanResult(
        disc_type=DiscType.CD,
        musicbrainz_disc_id=disc_id,
        raw={"track_count": track_count},
    )
