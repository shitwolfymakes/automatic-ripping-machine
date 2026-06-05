"""Disc probe: computes the pydvdid CRC64 fingerprint straight off the device.

The CRC64 is read via PyCdlib (pydvdid) and needs only read access to the
disc — no mount, no CAP_SYS_ADMIN. A DVD's CRC64 feeds the 1337server lookup
that runs before OMDb/TMDB. pydvdid returns None for anything without a
/VIDEO_TS tree, so it's a cheap no-op on Blu-ray / CD, and it reads ISO
sources (ARM_MANUAL_TRIGGER_ISO) directly with no loop-mount.

Disc-type classification is handled upstream by MakeMKV's CINFO:1 (see
makemkv.scan_disc), so the probe no longer mounts the disc — which is why the
ripper service needs neither CAP_SYS_ADMIN nor an AppArmor exception.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

logger = logging.getLogger("arm_ripper.scan.disc_probe")


@dataclass(frozen=True)
class DiscProbe:
    crc64: str | None


async def probe_disc(device_path: str) -> DiscProbe:
    """Compute the disc's pydvdid CRC64, read off the device via PyCdlib.

    Needs only read access to the disc — no mount, no CAP_SYS_ADMIN — so a
    DVD always gets its 1337server fingerprint, even on discs the kernel
    won't mount (region locks, UDF quirks) and even after the ripper service
    drops root. pydvdid returns None for anything without a /VIDEO_TS tree
    (Blu-ray / CD), so this is a cheap no-op there.

    Never raises — failures are logged and degrade to crc64=None.
    """
    crc64 = await asyncio.to_thread(_compute_crc, device_path)
    if crc64:
        logger.info("dvd crc64 device=%s value=%s", device_path, crc64)
    return DiscProbe(crc64=crc64)


def _compute_crc(device_path: str) -> str | None:
    """Compute the pydvdid CRC64 disc fingerprint from the disc's ISO 9660
    metadata, read straight off the device via PyCdlib.

    We read the device, not a mounted VIDEO_TS folder, on purpose. pydvdid
    hashes each VIDEO_TS file's creation time, size, and name; a mounted or
    extracted folder can carry rewritten timestamps, and the pydvdid_m fork
    refuses folder input unless a y/N prompt is answered interactively (it
    raises EOFError here, and `allow_folder_id=True` makes its __init__ return
    early without a checksum). Reading the device's ISO 9660 directory records
    yields the canonical, 1337server-compatible value — the same one upstream
    ARM v2 produced via `pydvdid.compute(mountpoint)`.

    Note: the dependency is the `pydvdid-m` fork, which exposes a `DvdId`
    class — there is no top-level `compute()` like the original `pydvdid`.
    """
    try:
        # pydvdid_m ships no type stubs / py.typed marker — fine, we touch it
        # through one str() call.
        from pydvdid_m import DvdId  # type: ignore[import-untyped]
    except ImportError as e:
        logger.info("pydvdid_m not available, skipping crc64: %s", e)
        return None
    try:
        crc = DvdId(device_path).checksum
    except Exception as e:  # noqa: BLE001 — pydvdid / pycdlib raise a few flavors
        logger.info("pydvdid compute failed device=%s: %s", device_path, e)
        return None
    if crc is None:
        return None
    # pydvdid-m's CRC64.__str__ formats as "<high8>|<low8>" (e.g.
    # "79df7b12|8b27d001"), but 1337server is keyed on ARM v2's original-pydvdid
    # form `format(crc, "016x")` — the identical bytes with no separator. Strip
    # the pipe so the stored fingerprint and the lookup both match the DB; a
    # piped value misses every disc on format alone.
    return str(crc).replace("|", "")
