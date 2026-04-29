import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from arm_ripper.rip.hashing import sha256_file

logger = logging.getLogger("arm_ripper.rip.makemkv")

RIP_TIMEOUT_SECONDS = 6 * 60 * 60  # 6 hours: worst-case BD

ProgressCallback = Callable[[float], Awaitable[None]]

_PRGV_RE = re.compile(r"^PRGV:(\d+),(\d+),(\d+)$")
_PRGT_RE = re.compile(r'^PRGT:(\d+),(\d+),"(.*)"$')


@dataclass
class RipResult:
    ok: bool
    output_path: Path | None = None
    size_bytes: int | None = None
    duration_seconds: int | None = None
    sha256: str | None = None
    error: str | None = None


def parse_progress_line(line: str) -> float | None:
    """Return the fractional progress [0, 1] from a PRGV line, or None."""
    m = _PRGV_RE.match(line.strip())
    if not m:
        return None
    _current, _total, max_ = (int(g) for g in m.groups())
    if max_ <= 0:
        return None
    return min(1.0, max(0.0, _current / max_))


async def _stream_output(
    proc: asyncio.subprocess.Process,
    on_progress: ProgressCallback | None,
) -> None:
    assert proc.stdout is not None
    while True:
        raw = await proc.stdout.readline()
        if not raw:
            return
        line = raw.decode(errors="replace").rstrip()
        if not line:
            continue

        progress = parse_progress_line(line)
        if progress is not None:
            if on_progress is not None:
                try:
                    await on_progress(progress)
                except Exception as exc:
                    logger.debug("progress callback raised: %s", exc)
            continue

        prgt = _PRGT_RE.match(line)
        if prgt:
            logger.info("makemkvcon milestone: %s", prgt.group(3))
            continue

        if line.startswith("MSG:"):
            logger.debug("makemkvcon: %s", line)


def _find_output_file(output_dir: Path, title_index: int) -> Path | None:
    """MakeMKV's mkv command writes `title_tNN.mkv` (zero-padded); fall back to the newest mkv."""
    expected = output_dir / f"title_t{title_index:02d}.mkv"
    if expected.exists():
        return expected
    candidates = sorted(output_dir.glob("*.mkv"), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


async def rip_title(
    device_path: str,
    title_index: int,
    output_dir: Path,
    expected_duration_seconds: int | None = None,
    on_progress: ProgressCallback | None = None,
) -> RipResult:
    """Rip a single MakeMKV title to `output_dir` via `makemkvcon mkv --robot`."""
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "makemkvcon",
        "mkv",
        "--robot",
        "--progress=-stdout",
        f"dev:{device_path}",
        str(title_index),
        str(output_dir),
    ]
    logger.info("makemkvcon mkv title=%d device=%s", title_index, device_path)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        return RipResult(ok=False, error=f"makemkvcon not on PATH: {e}")

    streamer = asyncio.create_task(_stream_output(proc, on_progress))
    try:
        await asyncio.wait_for(proc.wait(), timeout=RIP_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        streamer.cancel()
        return RipResult(ok=False, error=f"makemkvcon timed out after {RIP_TIMEOUT_SECONDS}s")
    finally:
        streamer.cancel()

    if proc.returncode != 0:
        stderr = b""
        if proc.stderr is not None:
            stderr = await proc.stderr.read()
        msg = stderr.decode(errors="replace").strip()[:400] or f"exit={proc.returncode}"
        return RipResult(ok=False, error=f"makemkvcon failed: {msg}")

    output_file = _find_output_file(output_dir, title_index)
    if output_file is None:
        return RipResult(ok=False, error="makemkvcon exited 0 but produced no .mkv")

    size = output_file.stat().st_size
    digest = await sha256_file(output_file)
    return RipResult(
        ok=True,
        output_path=output_file,
        size_bytes=size,
        duration_seconds=expected_duration_seconds,
        sha256=digest,
    )
