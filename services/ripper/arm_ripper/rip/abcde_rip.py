import asyncio
import contextlib
import logging
import os
import re
import signal
from collections.abc import Awaitable, Callable
from functools import partial
from pathlib import Path
from tempfile import NamedTemporaryFile

from arm_ripper.rip.abcde_output import (
    moved_tracks,
    read_workdir_file,
    track_errors,
    wav_bytes_written,
    wav_duration_seconds,
)
from arm_ripper.rip.hashing import sha256_file
from arm_ripper.rip.poller import Poller, start_byte_reporter, stop_all
from arm_ripper.rip.result import RipResult
from arm_ripper.rip.track_callbacks import OnByteProgress

logger = logging.getLogger("arm_ripper.rip.abcde")

_ABCDE_PROBLEM_LINE = re.compile(r"^\[(ERROR|WARNING)\]")

CD_RIP_TIMEOUT_SECONDS = 90 * 60  # 90 min: worst-case scratched disc, ~60min audio

# How often the rip reads abcde's status file for the tracks it has moved into place, and reports the WAV bytes
# written so far.
STATUS_POLL_SECONDS = 2.0


OnAbcdeTrackDone = Callable[[int, RipResult], Awaitable[None]]


def _kill_group(proc: asyncio.subprocess.Process) -> None:
    """SIGKILL abcde and everything it forked.

    abcde is a bash script that runs cdparanoia and the encoders as
    children. Killing bash alone orphans a cdparanoia that keeps the
    drive open (the abandon eject then fails EBUSY) and keeps writing
    into a raw dir that is about to be deleted. The group id is bash's
    pid because of `start_new_session=True`; a group that already
    emptied out is fine.
    """
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGKILL)
    with contextlib.suppress(ProcessLookupError):
        proc.kill()


def _abcde_config(output_dir: Path) -> str:
    """Force WAV output landing at `output_dir/trackNN.wav`, no lookup.

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
    empty without a lookup, producing a `-/-/01.wav`-style path.

    abcde does no metadata lookup (ARM does its own via MusicBrainz
    upstream). Line numbers below are from the abcde 2.9.3 script. The
    `move` action sets DOCDDB=y (line 4325), which
    runs the lookup phase (line 5098). That phase loops over
    `CDDBMETHOD`: the `musicbrainz` method queries the server without
    ever reading `CDDBAVAIL` (line 2676), while the `cddb` method skips
    its query when `CDDBAVAIL` is exactly lowercase `n` (lines 2731,
    2780). So the config sets `CDDBMETHOD="cddb"` and `CDDBAVAIL="n"`
    (an uppercase `N` never matched); abcde still needs a valid method
    keyword at startup.
    """
    return (
        f'OUTPUTTYPE="wav"\n'
        f'OUTPUTDIR="{output_dir}"\n'
        f"OUTPUTFORMAT='track${{TRACKNUM}}'\n"
        f'ACTIONS="read,move"\n'
        f'FORCE="y"\n'
        f'PADTRACKS="y"\n'
        f'CDDBAVAIL="n"\n'
        f'CDDBMETHOD="cddb"\n'
        f'EJECT=""\n'
    )


def _write_config(output_dir: Path) -> Path:
    """Write the abcde config for `output_dir` to a temporary file and return its path; the caller deletes it."""
    with NamedTemporaryFile("w", suffix=".abcde.conf", delete=False) as conf:
        conf.write(_abcde_config(output_dir))
        conf_path = Path(conf.name)
    return conf_path


async def _spawn_abcde(device_path: str, conf_path: Path, output_dir: Path) -> asyncio.subprocess.Process:
    """Start abcde on the disc with this config, in its own session and with `output_dir` as its working directory."""
    cmd = ["abcde", "-d", device_path, "-c", str(conf_path), "-N", "-n", "-j", "1"]
    # abcde creates a per-rip `abcde.XXXXX/` temp dir alongside its CWD
    # for staging WAVs before the `move` action. The ripper container's
    # default CWD (`/app/services/ripper`) is read-only for non-root
    # users, so without `cwd=` abcde fails with "Permission denied" on
    # the very first track. Running with `cwd=output_dir` puts the temp
    # dir inside the raw output tree, which is always writable.
    return await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(output_dir),
        start_new_session=True,
    )


class _CdTracks:
    """The track bookkeeping of one abcde rip: the result each requested track has so far."""

    def __init__(self, output_dir: Path, track_indexes: list[int], on_track_done: OnAbcdeTrackDone | None) -> None:
        self._output_dir = output_dir
        self._track_indexes = track_indexes
        self._on_track_done = on_track_done
        self.results: dict[int, RipResult] = {}

    async def finalize(self, idx: int) -> None:
        """Stat + hash the produced WAV; fire callback once."""
        if idx in self.results:
            return
        wav_path = self._output_dir / f"track{idx:02d}.wav"
        if not wav_path.exists():
            return
        try:
            size = wav_path.stat().st_size
        except OSError as exc:  # pragma: no cover — race window after exists() returned True
            logger.warning("stat failed track=%d path=%s err=%s", idx, wav_path, exc)
            return
        digest = await sha256_file(wav_path)
        result = RipResult(
            ok=True, output_path=wav_path, size_bytes=size, duration_seconds=wav_duration_seconds(size), sha256=digest
        )
        self.results[idx] = result
        if self._on_track_done is not None:
            await self._on_track_done(idx, result)

    async def fail_remaining(self, error: str, reasons_by_track: dict[int, str] | None = None) -> None:
        """Build + fire RipResult(ok=False) for every track not yet finalized: with the reason abcde recorded for
        that track when there is one, otherwise `error`."""
        reasons = reasons_by_track or {}
        for idx in self._track_indexes:
            if idx in self.results:
                continue
            reason = reasons.get(idx)
            result = RipResult(ok=False, error=f"abcde could not read the track: {reason}" if reason else error)
            self.results[idx] = result
            if self._on_track_done is not None:
                await self._on_track_done(idx, result)

    async def finalize_moved(self, moved: set[int]) -> None:
        """Finalize each requested track abcde has moved into place, in track order."""
        for idx in sorted(moved.intersection(self._track_indexes)):
            await self.finalize(idx)

    async def finalize_pending(self) -> None:
        """Give every requested track still without a result one more try at finalizing."""
        for idx in self._track_indexes:
            if idx not in self.results:
                await self.finalize(idx)


async def _finalize_moved_tracks(output_dir: Path, tracks: _CdTracks) -> None:
    """Read abcde's status file and finalize the tracks it has moved into the output dir."""
    status = await asyncio.to_thread(read_workdir_file, output_dir, "status")
    await tracks.finalize_moved(moved_tracks(status))


def _output_line(raw: bytes) -> str:
    """One line of abcde or cdparanoia output as text. A line redrawn with carriage returns (cdparanoia's progress
    meter) keeps only its last state."""
    return raw.decode(errors="replace").rstrip().rsplit("\r", 1)[-1]


def _log_output(line: str) -> None:
    """Log a line of abcde output at debug, or at warning when it is abcde's own `[ERROR]`/`[WARNING]` line."""
    if line:
        level = logging.WARNING if _ABCDE_PROBLEM_LINE.match(line) else logging.DEBUG
        logger.log(level, "abcde: %s", line)


async def _read_until_exit(proc: asyncio.subprocess.Process) -> int:
    """Log each line of abcde's stdout until it closes, then wait for abcde to exit and return its exit code."""
    assert proc.stdout is not None
    while raw := await proc.stdout.readline():
        _log_output(_output_line(raw))
    return await proc.wait()


async def _stop_abcde(proc: asyncio.subprocess.Process, stderr_task: asyncio.Task[None], conf_path: Path) -> None:
    """Clean up after one abcde run: kill and reap its process group if still running, let the stderr drain finish,
    and delete the config file.
    """
    if proc.returncode is None:
        _kill_group(proc)
        with contextlib.suppress(BaseException):
            await proc.wait()
    with contextlib.suppress(asyncio.CancelledError):
        await stderr_task
    conf_path.unlink(missing_ok=True)


def _exit_failure(rc: int, stderr_lines: list[str]) -> str:
    """The error for each track still without a result once abcde has exited: the end of abcde's stderr on a
    non-zero exit, otherwise a missing-WAV error.
    """
    if rc != 0:
        stderr = "\n".join(stderr_lines).strip()
        msg = stderr[-400:] if stderr else f"exit={rc}"
        return f"abcde failed: {msg}"
    # Successful exit but a particular WAV never landed — likely a per-track
    # read failure abcde gave up on quietly. Fail just that track.
    return "abcde did not produce the expected wav file"


async def rip_cd(
    device_path: str,
    output_dir: Path,
    track_indexes: list[int],
    on_track_done: OnAbcdeTrackDone | None = None,
    on_progress: OnByteProgress | None = None,
    expected_bytes: int | None = None,
) -> dict[int, RipResult]:
    """Rip a whole audio CD via abcde and map outputs back to track indexes.

    abcde rips the entire disc in one pass. While it runs, its status file
    is read every STATUS_POLL_SECONDS; as soon as it records a track's
    `trackNN.wav` as moved into `output_dir`, that track gets its
    `RipResult` (size + sha256) and `on_track_done` fires. The dispatcher
    plumbs that callback into the per-track WS lifecycle so the UI sees
    tracks tick from IN_PROGRESS to DONE one at a time, rather than the
    whole disc flipping together at the end. On the same interval,
    `on_progress` gets the WAV bytes written so far against
    `expected_bytes`.

    Returns a dict mapping every track index in `track_indexes` to its
    final RipResult — every requested track always gets exactly one entry,
    whether the rip succeeded, the file went missing, abcde failed, or
    `abcde` itself wasn't on PATH.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    conf_path = _write_config(output_dir)

    logger.debug("abcde rip device=%s output_dir=%s", device_path, output_dir)

    tracks = _CdTracks(output_dir, track_indexes, on_track_done)

    try:
        proc = await _spawn_abcde(device_path, conf_path, output_dir)
    except FileNotFoundError as e:
        conf_path.unlink(missing_ok=True)
        await tracks.fail_remaining(f"abcde not on PATH: {e}")
        return tracks.results

    stderr_buf: list[str] = []
    stderr_task = asyncio.create_task(_drain_stderr(proc.stderr, stderr_buf))

    finalizer = Poller(STATUS_POLL_SECONDS, partial(_finalize_moved_tracks, output_dir, tracks))
    finalizer.start()
    reporter = start_byte_reporter(
        STATUS_POLL_SECONDS, partial(wav_bytes_written, output_dir), expected_bytes, on_progress
    )

    rc: int
    timed_out = False
    try:
        rc = await asyncio.wait_for(_read_until_exit(proc), timeout=CD_RIP_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        timed_out = True
        rc = -1
    finally:
        # Cancel-safe: if the parent task was cancelled (abandon flow) or
        # we timed out above, abcde is still running and writing to the raw
        # dir. Kill it and its children before letting CancelledError
        # propagate / before returning a timeout result. The pollers stop
        # first, so a track being finalized reports before abcde is reaped.
        await stop_all(finalizer, reporter)
        await _stop_abcde(proc, stderr_task, conf_path)

    if timed_out:
        await tracks.fail_remaining(f"abcde timed out after {CD_RIP_TIMEOUT_SECONDS}s")
        return tracks.results

    # Post-exit sweep: tracks abcde moved into place after the last poll
    # get one more chance to finalize before the rest are failed.
    await tracks.finalize_pending()

    errors = await asyncio.to_thread(read_workdir_file, output_dir, "errors")
    await tracks.fail_remaining(_exit_failure(rc, stderr_buf), track_errors(errors))
    return tracks.results


async def _drain_stderr(stream: asyncio.StreamReader | None, buf: list[str]) -> None:
    """Log each line of abcde's stderr, and keep it in `buf` for the exit error."""
    if stream is None:  # pragma: no cover — PIPE is always set above
        return
    while raw := await stream.readline():
        line = _output_line(raw)
        _log_output(line)
        buf.append(line)
