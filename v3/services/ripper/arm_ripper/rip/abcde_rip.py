import asyncio
import logging
import re
from pathlib import Path
from tempfile import NamedTemporaryFile

from arm_ripper.rip.hashing import sha256_file
from arm_ripper.rip.makemkv_rip import RipResult

logger = logging.getLogger("arm_ripper.rip.abcde")

CD_RIP_TIMEOUT_SECONDS = 90 * 60  # 90 min: worst-case scratched disc, ~60min audio

_TRACK_DONE_RE = re.compile(r"Track\s+(\d+)\s*:\s*Reading.*?\bdone\b", re.IGNORECASE)


def _abcde_config(output_dir: Path) -> str:
    """Force WAV output, no CDDB, predictable filenames."""
    return (
        f'OUTPUTTYPE="wav"\n'
        f'OUTPUTDIR="{output_dir}"\n'
        f"OUTPUTFORMAT='track_${{TRACKNUM}}'\n"
        f'ACTIONS="read,move"\n'
        f'PADTRACKS="y"\n'
        f'CDDBMETHOD="none"\n'
        f'EJECT=""\n'
    )


async def rip_cd(
    device_path: str,
    output_dir: Path,
    track_indexes: list[int],
) -> dict[int, RipResult]:
    """Rip a whole audio CD via abcde and map outputs back to track indexes.

    abcde rips the entire disc in one pass; we generate one RipResult per
    track in `track_indexes`, mapping each to the `track_NN.wav` file abcde
    produces.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    with NamedTemporaryFile("w", suffix=".abcde.conf", delete=False) as conf:
        conf.write(_abcde_config(output_dir))
        conf_path = Path(conf.name)

    cmd = ["abcde", "-d", device_path, "-c", str(conf_path), "-N", "-n", "-j", "1"]
    logger.info("abcde rip device=%s output_dir=%s", device_path, output_dir)

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        conf_path.unlink(missing_ok=True)
        return {idx: RipResult(ok=False, error=f"abcde not on PATH: {e}") for idx in track_indexes}

    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=CD_RIP_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        conf_path.unlink(missing_ok=True)
        return {
            idx: RipResult(ok=False, error=f"abcde timed out after {CD_RIP_TIMEOUT_SECONDS}s") for idx in track_indexes
        }
    finally:
        # Cancel-safe: if the parent task was cancelled (abandon flow),
        # abcde is still running and writing to the raw dir. Kill it
        # before letting CancelledError propagate.
        if proc.returncode is None:
            proc.kill()
            try:
                await proc.wait()
            except BaseException:
                pass
        conf_path.unlink(missing_ok=True)

    stdout = stdout_b.decode(errors="replace")
    stderr = stderr_b.decode(errors="replace")

    if proc.returncode != 0:
        msg = (stderr.strip() or stdout.strip())[:400] or f"exit={proc.returncode}"
        return {idx: RipResult(ok=False, error=f"abcde failed: {msg}") for idx in track_indexes}

    for line in stdout.splitlines():
        m = _TRACK_DONE_RE.search(line)
        if m:
            logger.info("abcde finished track %s", m.group(1))

    results: dict[int, RipResult] = {}
    for idx in track_indexes:
        wav_path = output_dir / f"track_{idx:02d}.wav"
        if not wav_path.exists():
            results[idx] = RipResult(ok=False, error=f"abcde did not produce {wav_path.name}")
            continue
        size = wav_path.stat().st_size
        digest = await sha256_file(wav_path)
        results[idx] = RipResult(
            ok=True,
            output_path=wav_path,
            size_bytes=size,
            sha256=digest,
        )
    return results
