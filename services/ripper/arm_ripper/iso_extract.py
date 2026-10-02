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
import re
import shutil
from pathlib import Path

from arm_common import IsoPreparePhase
from arm_ripper import prepare

logger = logging.getLogger("arm_ripper.iso_extract")

# Must match the backend's `iso_rips.EXTRACT_DIRNAME` under RAW_ROOT.
EXTRACT_ROOT = Path("/raw/.iso-extract")

# A disc folder MakeMKV can open carries one of these at its root.
_VIDEO_DIRS = ("BDMV", "VIDEO_TS")

# A 50 GB Blu-ray from a network share can take a while; this only stops a
# 7z that hangs for good.
_EXTRACT_TIMEOUT_SECONDS = 4 * 3600

# 7-Zip's per-file failure lines, e.g. "ERROR: Data Error : CERTIFICATE/id.bdmv".
_FILE_ERROR = re.compile(r"^ERROR: [^:\n]+ : (.+)$", re.MULTILINE)

# One 7-Zip progress segment (`-bsp1`, segments separated by backspaces):
# " 75% 3 - BDMV/STREAM/00002.m2ts" or just " 12%".
_PROGRESS = re.compile(r"^\s*(\d{1,3})%(?:\s+\d+)?(?:\s+-\s+(.+?))?\s*$")

# Image path -> the extracted disc folder MakeMKV should read instead.
_extracted: dict[str, Path] = {}


def extracted_dir(image_path: str) -> Path | None:
    return _extracted.get(image_path)


def parse_progress(text: str) -> tuple[int, str | None] | None:
    """The latest (percent, current file) in 7-Zip's `-bsp1` output, or None."""
    for segment in reversed(re.split(r"[\b\r\n]+", text)):
        m = _PROGRESS.match(segment)
        if m:
            return int(m.group(1)), m.group(2)
    return None


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


async def _run_7z(image: Path, dest: Path) -> bool:
    # Debian 12's `7zip` package (the ripper image) ships only `7zz`; p7zip
    # and newer Debian install `7z`.
    exe = shutil.which("7z") or shutil.which("7zz")
    if exe is None:
        logger.error("iso extract: 7-Zip (7z / 7zz) is not installed")
        return False
    proc = await asyncio.create_subprocess_exec(
        exe,
        "x",
        "-tudf",
        "-y",
        "-bsp1",  # progress to stdout, read below for the "preparing" report
        "-bso0",  # no file listing on stdout
        f"-o{dest}",
        "--",
        str(image),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stdout is not None and proc.stderr is not None
    stdout, stderr_stream = proc.stdout, proc.stderr

    async def _progress() -> None:
        await prepare.report(IsoPreparePhase.EXTRACTING, 0, None)
        tail = ""
        while chunk := await stdout.read(4096):
            tail = (tail + chunk.decode(errors="replace"))[-1024:]
            parsed = parse_progress(tail)
            if parsed is not None:
                await prepare.report(IsoPreparePhase.EXTRACTING, *parsed)

    try:
        _, stderr = await asyncio.wait_for(
            asyncio.gather(_progress(), stderr_stream.read()), timeout=_EXTRACT_TIMEOUT_SECONDS
        )
        await proc.wait()
    except BaseException:
        # Timeout or the pipeline being cancelled: never leave 7z writing.
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.wait()
        raise
    return _usable(image, proc.returncode, stderr.decode(errors="replace"))


def _usable(image: Path, rc: int | None, stderr: str) -> bool:
    """Whether 7z's result can be read as a disc folder.

    0 is clean and 1 is 7-Zip's warning (the files are out). 2 is an error,
    but DVDFab backups routinely carry unreadable CERTIFICATE / PS3_UPDATE /
    PS3_VPRM files that MakeMKV never reads; when every failed file is outside
    the BDMV / VIDEO_TS tree the disc is still usable. Any other failure (one
    in the video tree, or one 7z can't attribute to a file) is fatal.
    """
    if rc in (0, 1):
        return True
    damaged = _FILE_ERROR.findall(stderr)
    if rc == 2 and damaged and not any(p.split("/", 1)[0].upper() in _VIDEO_DIRS for p in damaged):
        logger.warning(
            "iso extract: %s: %d unreadable file(s) outside the video tree, ignored: %s",
            image,
            len(damaged),
            ", ".join(damaged),
        )
        return True
    logger.error("iso extract: 7z exited %s: %s", rc, stderr[-300:])
    return False


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
        ok = await _run_7z(image, root)
    except BaseException:
        await asyncio.to_thread(shutil.rmtree, base, True)
        raise
    if not ok or not any((root / d).is_dir() for d in _VIDEO_DIRS):
        if ok:
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
