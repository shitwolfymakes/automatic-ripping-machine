"""Extract fallback for an ISO MakeMKV cannot open directly.

Some images crash makemkvcon's own image reader (seen with DVDFab UDF 2.50
Blu-ray backups: `makemkvcon info iso:` exits with SIGSEGV before listing a
title), yet MakeMKV reads the same disc fine from a folder. Mounting the image
would need CAP_SYS_ADMIN, loop devices and an AppArmor exception, and the
ripper runs unprivileged, so 7-Zip's UDF reader unpacks it instead, into
scratch space under /raw (the one large writable volume a ripper has). Once
extracted, `source.makemkv_source_url` answers `file:<folder>` for the image,
so the scan and the rip both read the folder and the disc keeps its titles.

One extraction per container (a source-mode ripper serves exactly one ISO),
removed by `discard_all` when the pipeline ends. The backend also removes
`/raw/.iso-extract/<drive_id>` when it retires the virtual drive, for a
container that was stopped before it could clean up.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
from pathlib import Path

logger = logging.getLogger("arm_ripper.iso_extract")

# Must match the backend's `iso_rips.EXTRACT_DIRNAME` under RAW_ROOT.
EXTRACT_ROOT = Path("/raw/.iso-extract")

# A disc folder MakeMKV can open carries one of these at its root.
_VIDEO_DIRS = ("BDMV", "VIDEO_TS")

# A 50 GB Blu-ray from a network share can take a while; this only stops a
# 7z that hangs for good.
_EXTRACT_TIMEOUT_SECONDS = 4 * 3600

# Image path -> the extracted disc folder MakeMKV should read instead.
_extracted: dict[str, Path] = {}


def extracted_dir(image_path: str) -> Path | None:
    return _extracted.get(image_path)


def _drive_dir() -> Path:
    # Imported here: arm_ripper.config builds its Settings from the environment
    # at import time, and source.py (which imports this module) must stay
    # importable without it.
    from arm_ripper.config import settings

    return EXTRACT_ROOT / settings.ARM_DRIVE_ID


def _has_space(image: Path, scratch: Path) -> bool:
    need = image.stat().st_size
    probe = scratch
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    free = shutil.disk_usage(probe).free
    if free < need:
        logger.error(
            "iso extract: not enough scratch space under %s for %s (need %d bytes, %d free)", scratch, image, need, free
        )
        return False
    return True


async def _run_7z(image: Path, dest: Path) -> int | None:
    exe = shutil.which("7z")
    if exe is None:
        logger.error("iso extract: 7z is not installed")
        return None
    proc = await asyncio.create_subprocess_exec(
        exe,
        "x",
        "-tudf",
        "-y",
        "-bd",
        f"-o{dest}",
        "--",
        str(image),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=_EXTRACT_TIMEOUT_SECONDS)
    except BaseException:
        # Timeout or the pipeline being cancelled: never leave 7z writing.
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.wait()
        raise
    if proc.returncode not in (0, 1):  # 1 is 7-Zip's "warning", the files are out
        logger.error("iso extract: 7z exited %s: %s", proc.returncode, stderr[-300:].decode(errors="replace"))
    return proc.returncode


async def extract(image_path: str) -> Path | None:
    """Unpack the image into scratch space and route MakeMKV to the result.

    Returns the disc folder (named after the image, which is what MakeMKV
    reports as the folder's title) or None when there is no room, 7z fails,
    or the image carries no BDMV / VIDEO_TS tree. Nothing is left behind on
    failure.
    """
    image = Path(image_path)
    base = _drive_dir()
    root = base / image.stem
    if not await asyncio.to_thread(_has_space, image, base):
        return None
    await asyncio.to_thread(shutil.rmtree, base, True)
    await asyncio.to_thread(root.mkdir, parents=True)
    logger.info("iso extract: unpacking %s into %s", image, root)
    try:
        rc = await _run_7z(image, root)
    except BaseException:
        await asyncio.to_thread(shutil.rmtree, base, True)
        raise
    if rc not in (0, 1) or not any((root / d).is_dir() for d in _VIDEO_DIRS):
        if rc in (0, 1):
            logger.warning("iso extract: %s has no BDMV or VIDEO_TS folder; not a video disc", image)
        await asyncio.to_thread(shutil.rmtree, base, True)
        return None
    _extracted[image_path] = root
    logger.info("iso extract: %s extracted; MakeMKV reads file:%s", image, root)
    return root


def discard_all() -> None:
    """Remove every extraction this process made and stop routing to it."""
    for root in _extracted.values():
        shutil.rmtree(root, ignore_errors=True)
        # The per-drive dir `extract` made around it, once empty; never
        # anything else that happens to be the folder's parent.
        with contextlib.suppress(OSError):
            root.parent.rmdir()
    _extracted.clear()
