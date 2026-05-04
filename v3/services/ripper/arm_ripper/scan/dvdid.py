"""DVD CRC64 fingerprint via pydvdid against a temporary mount.

The community-maintained 1337server lookup keys on this hash; computing it
in the scan flow lets the backend dispatcher prefer the crowd-sourced
match over fuzzy TMDB / OMDB title search.

Mount/umount needs CAP_SYS_ADMIN — added to the ripper container in
docker-compose.yml. The mount is read-only, lives only for the duration of
this call, and is cleaned up on every exit path.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger("arm_ripper.scan.dvdid")

_MOUNT_TIMEOUT_SECONDS = 30.0


async def compute_dvd_crc64(device_path: str) -> str | None:
    """Return the pydvdid CRC64 hex string for the disc in `device_path`,
    or None if anything goes wrong. Never raises — the fingerprint is
    advisory and a failed lookup just means the dispatcher falls through
    to TMDB/OMDB.
    """
    try:
        # Lazy import: keeps the ripper able to start in dev environments
        # where pydvdid_m isn't installed yet (e.g. older venvs after
        # pulling the new dep). pydvdid_m has no type stubs / py.typed
        # marker — that's fine, we use it through a single str() call.
        import pydvdid_m  # type: ignore[import-untyped]
    except ImportError as e:
        logger.info("pydvdid_m not available, skipping crc64: %s", e)
        return None

    mount_dir = Path(tempfile.mkdtemp(prefix="arm-dvd-mnt-"))
    try:
        rc, stderr = await _run("mount", "-o", "ro", device_path, str(mount_dir))
        if rc != 0:
            logger.info("mount %s failed (rc=%s): %s", device_path, rc, stderr)
            return None
        try:
            crc = await asyncio.to_thread(_compute_crc, mount_dir, pydvdid_m)
        except Exception as e:  # noqa: BLE001 — pydvdid raises a few flavors
            logger.info("pydvdid compute failed device=%s: %s", device_path, e)
            return None
        if crc:
            logger.info("dvd crc64 device=%s value=%s", device_path, crc)
        return crc
    finally:
        # Best-effort umount; ignore failures (e.g. EBUSY from a stray fd
        # — the next mount will retry on a fresh tmpdir anyway).
        await _run("umount", str(mount_dir), log_failure=False)
        shutil.rmtree(mount_dir, ignore_errors=True)


def _compute_crc(mount_dir: Path, pydvdid_m: object) -> str | None:
    # pydvdid_m.compute returns a CRC64 object whose __str__ is the hex
    # digest — same shape v2 stored in `job.crc_id`.
    compute = getattr(pydvdid_m, "compute", None)
    if compute is None:
        return None
    crc = compute(str(mount_dir))
    return str(crc) if crc is not None else None


async def _run(*argv: str, log_failure: bool = True) -> tuple[int | None, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (FileNotFoundError, OSError) as e:
        if log_failure:
            logger.info("%s errored: %s", argv[0], e)
        return None, str(e)
    try:
        _, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=_MOUNT_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return None, "timeout"
    return proc.returncode, stderr_b.decode(errors="replace").strip()
