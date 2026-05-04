"""Mount-based disc probe: classifies the disc by filesystem layout and,
for DVDs, computes the pydvdid CRC64 fingerprint in the same mount cycle.

The directory layout is the authoritative signal:
  - `BDMV/index.bdmv`    → Blu-ray
  - `VIDEO_TS/VIDEO_TS.IFO` → DVD-Video

This replaces the duration/size heuristic that used to live in `makemkv.py`,
which misclassified DVD-9s with long main features as Blu-rays (a DVD title
can easily exceed the 4.7GB single-layer threshold).

Mount/umount needs CAP_SYS_ADMIN — added to the ripper container in
docker-compose.yml. Mount is ro, lives only for the duration of the probe,
and is cleaned up on every exit path.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

from arm_common import DiscType

logger = logging.getLogger("arm_ripper.scan.disc_probe")

_MOUNT_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class DiscProbe:
    disc_type: DiscType | None
    crc64: str | None


async def probe_disc(device_path: str) -> DiscProbe:
    """Mount `device_path` ro and inspect the filesystem layout.

    Returns DiscProbe(disc_type=DVD|BLURAY|None, crc64=...) — `disc_type`
    is None when the mount fails or neither layout marker is present;
    callers can fall back to a duration-based heuristic.

    Never raises — every failure path is logged and degrades to None
    fields so the scan flow can continue without a fingerprint.
    """
    async with _temp_mount(device_path) as mount_dir:
        if mount_dir is None:
            return DiscProbe(disc_type=None, crc64=None)

        disc_type = _classify_from_layout(mount_dir)
        crc64 = None
        if disc_type == DiscType.DVD:
            crc64 = await asyncio.to_thread(_compute_crc, mount_dir)
            if crc64:
                logger.info("dvd crc64 device=%s value=%s", device_path, crc64)
        return DiscProbe(disc_type=disc_type, crc64=crc64)


def _classify_from_layout(mount_dir: Path) -> DiscType | None:
    """Inspect the mounted root for the canonical disc-format markers.

    BDMV/index.bdmv is the BD-Video index file; VIDEO_TS/VIDEO_TS.IFO is the
    DVD-Video master IFO. Both are required for playback so they're a
    reliable signal that's far better than guessing from title sizes.
    """
    if (mount_dir / "BDMV" / "index.bdmv").is_file():
        return DiscType.BLURAY
    if (mount_dir / "VIDEO_TS" / "VIDEO_TS.IFO").is_file():
        return DiscType.DVD
    # Some authoring tools lower-case BDMV; cheap second look.
    if (mount_dir / "bdmv" / "index.bdmv").is_file():
        return DiscType.BLURAY
    if (mount_dir / "video_ts" / "VIDEO_TS.IFO").is_file():
        return DiscType.DVD
    return None


def _compute_crc(mount_dir: Path) -> str | None:
    try:
        # pydvdid_m has no type stubs / py.typed marker — that's fine,
        # we use it through a single str() call.
        import pydvdid_m  # type: ignore[import-untyped]
    except ImportError as e:
        logger.info("pydvdid_m not available, skipping crc64: %s", e)
        return None
    compute = getattr(pydvdid_m, "compute", None)
    if compute is None:
        return None
    try:
        crc = compute(str(mount_dir))
    except Exception as e:  # noqa: BLE001 — pydvdid raises a few flavors
        logger.info("pydvdid compute failed mount=%s: %s", mount_dir, e)
        return None
    return str(crc) if crc is not None else None


@asynccontextmanager
async def _temp_mount(device_path: str) -> AsyncIterator[Path | None]:
    """Mount `device_path` read-only on a tmpdir; yield the path or None
    on failure. Always umount + cleanup the tmpdir on exit.
    """
    mount_dir = Path(tempfile.mkdtemp(prefix="arm-disc-probe-"))
    mounted = False
    try:
        rc, stderr = await _run("mount", "-o", "ro", device_path, str(mount_dir))
        if rc != 0:
            logger.info("mount %s failed (rc=%s): %s", device_path, rc, stderr)
            yield None
            return
        mounted = True
        yield mount_dir
    finally:
        if mounted:
            # Best-effort umount; ignore failures (e.g. EBUSY from a stray
            # fd — the next mount will retry on a fresh tmpdir anyway).
            await _run("umount", str(mount_dir), log_failure=False)
        shutil.rmtree(mount_dir, ignore_errors=True)


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
