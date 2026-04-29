import asyncio
import logging
from pathlib import Path

from arm_ripper.rip.hashing import sha256_file
from arm_ripper.rip.makemkv_rip import RipResult

logger = logging.getLogger("arm_ripper.rip.data")

DATA_RIP_TIMEOUT_SECONDS = 4 * 60 * 60


async def rip_data(device_path: str, output_dir: Path) -> RipResult:
    """Pull a raw image from the disc via dd."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "dump.iso"

    cmd = [
        "dd",
        f"if={device_path}",
        f"of={output_path}",
        "bs=2048",
        "conv=noerror,sync",
    ]
    logger.info("dd if=%s of=%s", device_path, output_path)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        return RipResult(ok=False, error=f"dd not on PATH: {e}")

    try:
        await asyncio.wait_for(proc.wait(), timeout=DATA_RIP_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return RipResult(ok=False, error=f"dd timed out after {DATA_RIP_TIMEOUT_SECONDS}s")

    if proc.returncode != 0:
        stderr = b""
        if proc.stderr is not None:
            stderr = await proc.stderr.read()
        msg = stderr.decode(errors="replace").strip()[:400] or f"exit={proc.returncode}"
        return RipResult(ok=False, error=f"dd failed: {msg}")

    if not output_path.exists() or output_path.stat().st_size == 0:
        return RipResult(ok=False, error="dd exited 0 but produced empty output")

    size = output_path.stat().st_size
    digest = await sha256_file(output_path)
    return RipResult(ok=True, output_path=output_path, size_bytes=size, sha256=digest)
