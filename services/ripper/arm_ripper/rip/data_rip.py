import asyncio
import contextlib
import logging
import os
from functools import partial
from pathlib import Path

from arm_ripper.rip.hashing import sha256_file
from arm_ripper.rip.poller import Poller
from arm_ripper.rip.result import RipResult
from arm_ripper.rip.track_callbacks import OnByteProgress
from arm_ripper.rip.subprocess_cleanup import kill_if_running
from arm_ripper.source import is_iso_source

logger = logging.getLogger("arm_ripper.rip.data")

DATA_RIP_TIMEOUT_SECONDS = 4 * 60 * 60

# How often the copy reports the bytes written so far while dd runs.
PROGRESS_INTERVAL_SECONDS = 2.0


def source_size(device_path: str) -> int | None:
    """Size in bytes of an image file or a block device, or None when unknown."""
    try:
        with open(device_path, "rb") as fh:
            size = fh.seek(0, os.SEEK_END)
    except OSError:
        return None
    return size or None


async def _report_size(output_path: Path, total: int | None, on_progress: OnByteProgress) -> None:
    """Report the bytes the copy has written so far."""
    await on_progress(output_path.stat().st_size, total)


def _start_reporter(output_path: Path, total: int | None, on_progress: OnByteProgress | None) -> Poller | None:
    """Start reporting the copy's size every PROGRESS_INTERVAL_SECONDS; None when nobody listens."""
    if on_progress is None:
        return None
    poller = Poller(PROGRESS_INTERVAL_SECONDS, partial(_report_size, output_path, total, on_progress))
    poller.start()
    return poller


def _dd_command(device_path: str, output_path: Path) -> list[str]:
    """The dd argv: 4 MB blocks for an image file; 2 KB blocks with noerror,sync for a disc."""
    if is_iso_source(device_path):
        return ["dd", f"if={device_path}", f"of={output_path}", "bs=4M"]
    return ["dd", f"if={device_path}", f"of={output_path}", "bs=2048", "conv=noerror,sync"]


async def _wait_for_dd(proc: asyncio.subprocess.Process, reporter: Poller | None) -> RipResult | None:
    """Wait for dd to exit; return the timeout failure, or None if it exits in time.

    Either way, the progress reporter is stopped and dd is reaped before this returns.
    """
    try:
        await asyncio.wait_for(proc.wait(), timeout=DATA_RIP_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return RipResult(ok=False, error=f"dd timed out after {DATA_RIP_TIMEOUT_SECONDS}s")
    finally:
        if reporter is not None:
            await reporter.stop()
        await kill_if_running(proc)
    return None


async def _dd_failure(proc: asyncio.subprocess.Process) -> RipResult | None:
    """The failure for a dd that exited non-zero, keeping the end of its stderr; None when it exited 0."""
    if proc.returncode == 0:
        return None
    stderr = b""
    if proc.stderr is not None:
        stderr = await proc.stderr.read()
    msg = stderr.decode(errors="replace").strip()[-400:] or f"exit={proc.returncode}"
    return RipResult(ok=False, error=f"dd failed: {msg}")


def _empty_output_failure(output_path: Path) -> RipResult | None:
    """The failure for a dd that exited 0 without writing anything; None when the image has bytes."""
    if not output_path.exists() or output_path.stat().st_size == 0:
        return RipResult(ok=False, error="dd exited 0 but produced empty output")
    return None


async def rip_data(device_path: str, output_dir: Path, on_progress: OnByteProgress | None = None) -> RipResult:
    """Pull a raw image from the disc, or copy an ISO image, via dd.

    A physical disc keeps 2 KB blocks so `conv=noerror,sync` pads exactly one
    unreadable sector. An image file has no bad sectors to pad and is copied
    in 4 MB blocks (2 KB blocks made a 20 GB copy over NFS take hours).
    `on_progress` receives the bytes written so far every couple of seconds
    and once more when the copy completes.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "dump.iso"

    cmd = _dd_command(device_path, output_path)
    total = await asyncio.to_thread(source_size, device_path)
    logger.info("dd if=%s of=%s size=%s", device_path, output_path, total)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        return RipResult(ok=False, error=f"dd not on PATH: {e}")

    reporter = _start_reporter(output_path, total, on_progress)
    timed_out = await _wait_for_dd(proc, reporter)
    if timed_out is not None:
        return timed_out

    failed = await _dd_failure(proc)
    if failed is not None:
        return failed

    empty = _empty_output_failure(output_path)
    if empty is not None:
        return empty

    size = output_path.stat().st_size
    if on_progress is not None:
        with contextlib.suppress(Exception):
            await on_progress(size, total or size)
    digest = await sha256_file(output_path)
    return RipResult(ok=True, output_path=output_path, size_bytes=size, sha256=digest)
