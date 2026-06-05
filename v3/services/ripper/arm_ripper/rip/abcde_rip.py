import asyncio
import contextlib
import logging
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from tempfile import NamedTemporaryFile

from arm_ripper.rip.hashing import sha256_file
from arm_ripper.rip.makemkv_rip import RipResult

logger = logging.getLogger("arm_ripper.rip.abcde")

CD_RIP_TIMEOUT_SECONDS = 90 * 60  # 90 min: worst-case scratched disc, ~60min audio

# abcde's per-track read-completion log line. The full line looks like
# `[wavencode] Track 01: Reading audio from sectors 12345-67890...done`
# but we only need the track number and the literal `done` confirmation.
_TRACK_DONE_RE = re.compile(r"Track\s+(\d+)\s*:\s*Reading.*?\bdone\b", re.IGNORECASE)


OnAbcdeTrackDone = Callable[[int, RipResult], Awaitable[None]]


def _abcde_config(output_dir: Path) -> str:
    """Force WAV output landing at `output_dir/trackNN.wav`, no CDDB.

    abcde's `read` action always stages WAVs as
    `${WAVOUTPUTDIR}/abcde.${CDDBDISCID}/trackNN.wav` regardless of
    config. The `move` action would relocate them to OUTPUTDIR — but
    inside abcde's do_move(), the WAV branch is gated on
    `DOCLEAN=y || FORCE=y`; with neither set, move silently skips for
    wav outputs and the rip "succeeds" with zero files in OUTPUTDIR.
    Setting `FORCE=y` makes do_move() actually run for wav.

    `OUTPUTFORMAT='track${TRACKNUM}'` keeps the post-move filename
    matching abcde's pre-move name (`trackNN.wav`), so `_finalize_track`
    only needs one shape to look for. Without an explicit OUTPUTFORMAT
    the move would try to substitute ARTISTFILE/ALBUMFILE which are
    empty under CDDBAVAIL=N, producing a `-/-/01.wav`-style path.

    `CDDBAVAIL=N` skips all metadata lookups (ARM does its own via
    MusicBrainz upstream). `CDDBMETHOD` still has to parse as a valid
    method even when lookups are disabled — abcde validates the keyword
    at startup before consulting `CDDBAVAIL`.
    """
    return (
        f'OUTPUTTYPE="wav"\n'
        f'OUTPUTDIR="{output_dir}"\n'
        f"OUTPUTFORMAT='track${{TRACKNUM}}'\n"
        f'ACTIONS="read,move"\n'
        f'FORCE="y"\n'
        f'PADTRACKS="y"\n'
        f'CDDBAVAIL="N"\n'
        f'CDDBMETHOD="musicbrainz"\n'
        f'EJECT=""\n'
    )


async def rip_cd(
    device_path: str,
    output_dir: Path,
    track_indexes: list[int],
    on_track_done: OnAbcdeTrackDone | None = None,
) -> dict[int, RipResult]:
    """Rip a whole audio CD via abcde and map outputs back to track indexes.

    abcde rips the entire disc in one pass; we stream its stdout so that as
    soon as each `trackNN.wav` file appears on disk we can build a per-track
    `RipResult` (size + sha256) and fire `on_track_done`. The dispatcher
    plumbs that callback into the per-track WS lifecycle so the UI sees
    tracks tick from IN_PROGRESS to DONE one at a time, rather than the
    whole disc flipping together at the end.

    Returns a dict mapping every track index in `track_indexes` to its
    final RipResult — every requested track always gets exactly one entry,
    whether the rip succeeded, the file went missing, abcde failed, or
    `abcde` itself wasn't on PATH.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    with NamedTemporaryFile("w", suffix=".abcde.conf", delete=False) as conf:
        conf.write(_abcde_config(output_dir))
        conf_path = Path(conf.name)

    cmd = ["abcde", "-d", device_path, "-c", str(conf_path), "-N", "-n", "-j", "1"]
    logger.info("abcde rip device=%s output_dir=%s", device_path, output_dir)

    results: dict[int, RipResult] = {}

    async def _finalize_track(idx: int) -> None:
        """Stat + hash the produced WAV; fire callback once."""
        if idx in results:
            return
        wav_path = output_dir / f"track{idx:02d}.wav"
        if not wav_path.exists():
            return
        try:
            size = wav_path.stat().st_size
        except OSError as exc:  # pragma: no cover — race window after exists() returned True
            logger.warning("stat failed track=%d path=%s err=%s", idx, wav_path, exc)
            return
        digest = await sha256_file(wav_path)
        result = RipResult(ok=True, output_path=wav_path, size_bytes=size, sha256=digest)
        results[idx] = result
        if on_track_done is not None:
            await on_track_done(idx, result)

    async def _fail_remaining(error: str) -> None:
        """Build + fire RipResult(ok=False) for every track not yet finalized."""
        for idx in track_indexes:
            if idx in results:
                continue
            result = RipResult(ok=False, error=error)
            results[idx] = result
            if on_track_done is not None:
                await on_track_done(idx, result)

    # abcde creates a per-rip `abcde.XXXXX/` temp dir alongside its CWD
    # for staging WAVs before the `move` action. The ripper container's
    # default CWD (`/app/services/ripper`) is read-only for non-root
    # users, so without `cwd=` abcde fails with "Permission denied" on
    # the very first track. Running with `cwd=output_dir` puts the temp
    # dir inside the raw output tree, which is always writable.
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(output_dir),
        )
    except FileNotFoundError as e:
        conf_path.unlink(missing_ok=True)
        await _fail_remaining(f"abcde not on PATH: {e}")
        return results

    stderr_buf: list[str] = []
    stderr_task = asyncio.create_task(_drain_stderr(proc.stderr, stderr_buf))

    seen_done_in_log: set[int] = set()

    async def _stream_and_wait() -> int:
        """Stream abcde's stdout line-by-line; sweep finished tracks per line."""
        assert proc.stdout is not None
        while True:
            line_b = await proc.stdout.readline()
            if not line_b:
                break
            line = line_b.decode(errors="replace").rstrip()
            m = _TRACK_DONE_RE.search(line)
            if m:
                seen_done_in_log.add(int(m.group(1)))
                logger.info("abcde finished track %s", m.group(1))
            # Sweep any track whose log signaled done but whose file
            # wasn't yet on disk when we last looked. The `move` action
            # runs after `read`; the WAV may land a few hundred ms after
            # the "Reading...done" line.
            for idx in list(seen_done_in_log):
                if idx not in results:
                    await _finalize_track(idx)
        return await proc.wait()

    rc: int
    timed_out = False
    try:
        rc = await asyncio.wait_for(_stream_and_wait(), timeout=CD_RIP_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        timed_out = True
        rc = -1
    finally:
        # Cancel-safe: if the parent task was cancelled (abandon flow) or
        # we timed out above, abcde is still running and writing to the raw
        # dir. Kill it before letting CancelledError propagate / before
        # returning a timeout result.
        if proc.returncode is None:
            proc.kill()
            with contextlib.suppress(BaseException):
                await proc.wait()
        with contextlib.suppress(asyncio.CancelledError):
            await stderr_task
        conf_path.unlink(missing_ok=True)

    if timed_out:
        await _fail_remaining(f"abcde timed out after {CD_RIP_TIMEOUT_SECONDS}s")
        return results

    # Post-wait sweep: tracks whose "Reading...done" appeared in the
    # final batch of output (or whose WAV landed only after the last
    # line was read) get one more chance to finalize before we fail
    # them.
    for idx in track_indexes:
        if idx not in results:
            await _finalize_track(idx)

    if rc != 0:
        stderr = "\n".join(stderr_buf).strip()
        msg = stderr[-400:] if stderr else f"exit={rc}"
        await _fail_remaining(f"abcde failed: {msg}")
        return results

    # Successful exit but a particular WAV never landed — likely a per-track
    # read failure abcde gave up on quietly. Fail just that track.
    await _fail_remaining("abcde did not produce the expected wav file")
    return results


async def _drain_stderr(stream: asyncio.StreamReader | None, buf: list[str]) -> None:
    if stream is None:  # pragma: no cover — PIPE is always set above
        return
    while True:
        line = await stream.readline()
        if not line:
            break
        buf.append(line.decode(errors="replace").rstrip())
