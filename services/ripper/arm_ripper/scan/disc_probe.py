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

from arm_ripper.config import settings
from arm_ripper.drive_poll import DriveState, read_drive_status
from arm_ripper.source import is_iso_source

logger = logging.getLogger("arm_ripper.scan.disc_probe")

# Bounds the wait for the optical device to re-settle after makemkvcon info
# released it. Polled on settings.POLL_INTERVAL_SECONDS granularity; the
# normal re-settle clears in one or two polls.
DEVICE_READY_TIMEOUT_SECONDS = 6.0


@dataclass(frozen=True)
class DiscProbe:
    crc64: str | None


async def await_device_ready(device_path: str) -> bool:
    """Wait until the optical device reports DISC_OK before fingerprinting.

    `makemkvcon info` opens and releases the device just before the probe runs;
    the kernel reports "no medium" during the brief re-settle, so pydvdid would
    race (ENOMEDIUM) and yield an empty fingerprint. Poll the same readiness
    ioctl `poll_loop` trusts (`read_drive_status`) until the medium is ready.

    Returns True once DISC_OK (probe is safe). Returns False on a genuine
    no-medium reading (NO_DISC / TRAY_OPEN) or if the readiness budget expires
    while the device stays NOT_READY / NO_INFO. ISO sources are always ready.
    Never raises — read_drive_status's OSError (e.g. ENOMEDIUM on the re-settling
    device) is caught here and treated as not-ready.
    """
    if is_iso_source(device_path):
        return True
    interval = settings.POLL_INTERVAL_SECONDS
    polls = max(1, int(DEVICE_READY_TIMEOUT_SECONDS / interval))
    for attempt in range(polls):
        try:
            state = read_drive_status(device_path)
        except OSError:
            state = DriveState.NO_INFO
        if state == DriveState.DISC_OK:
            return True
        if state in (DriveState.NO_DISC, DriveState.TRAY_OPEN):
            logger.info("disc probe: no medium (%s) device=%s", state.name, device_path)
            return False
        if attempt < polls - 1:
            await asyncio.sleep(interval)
    logger.info("disc probe: device not ready after %.0fs device=%s", DEVICE_READY_TIMEOUT_SECONDS, device_path)
    return False


async def probe_disc(device_path: str) -> DiscProbe:
    """Compute the disc's pydvdid CRC64, read off the device via PyCdlib.

    Needs only read access to the disc — no mount, no CAP_SYS_ADMIN — so a
    DVD always gets its 1337server fingerprint, even on discs the kernel
    won't mount (region locks, UDF quirks) and even after the ripper service
    drops root. pydvdid returns None for anything without a /VIDEO_TS tree
    (Blu-ray / CD), so this is a cheap no-op there.

    Probes only when the device reports ready (see await_device_ready); an
    unready device degrades to crc64=None without racing pydvdid. Never raises.
    """
    if not await await_device_ready(device_path):
        return DiscProbe(crc64=None)
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
