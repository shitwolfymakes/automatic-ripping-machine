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
_MSG_RE = re.compile(r'^MSG:(\d+),\d+,\d+,"((?:[^"\\]|\\.)*)"')

# MakeMKV codes worth surfacing when a rip fails. makemkvcon often exits 0
# even when no .mkv is produced; the real cause is in these MSG lines.
#  1002 — LIBMKV_TRACE Exception (e.g. "Error while reading input")
#  3032 — drive/disc region mismatch (informational, but explains BD failures)
#  5003 — Failed to save title N to file ...
#  5037 — Copy complete. X titles saved, Y failed (final summary)
# Reference: https://github.com/automatic-ripping-machine/automatic-ripping-machine/wiki/MakeMKV-Codes
_DIAGNOSTIC_MSG_CODES = frozenset({1002, 3032, 5003, 5037})


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


def parse_diagnostic_msg(line: str) -> tuple[int, str] | None:
    """If `line` is a MSG: line whose code is in _DIAGNOSTIC_MSG_CODES,
    return (code, rendered_text). Otherwise None.
    """
    m = _MSG_RE.match(line.strip())
    if not m:
        return None
    code = int(m.group(1))
    if code not in _DIAGNOSTIC_MSG_CODES:
        return None
    # MakeMKV escapes embedded quotes as \"; turn them back for readability.
    text = m.group(2).replace('\\"', '"')
    return code, text


async def _stream_output(
    proc: asyncio.subprocess.Process,
    on_progress: ProgressCallback | None,
    diagnostics: list[str],
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
            diag = parse_diagnostic_msg(line)
            if diag is not None:
                diagnostics.append(diag[1])
            logger.debug("makemkvcon: %s", line)


def _compose_error(prefix: str, diagnostics: list[str]) -> str:
    """Stitch the diagnostic MakeMKV messages onto the failure summary so
    `track.last_error` carries the actual cause (e.g. "Error while reading
    input", "Failed to save title 2 to file ...") instead of just the
    generic exit-code wrapper.
    """
    if not diagnostics:
        return prefix
    # De-dup adjacent identical lines (e.g. MSG:3032 emitted twice on
    # region-locked BDs) but preserve order — first-mentioned cause first.
    seen: list[str] = []
    for d in diagnostics:
        if not seen or seen[-1] != d:
            seen.append(d)
    return f"{prefix}: {'; '.join(seen)}"


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

    diagnostics: list[str] = []
    streamer = asyncio.create_task(_stream_output(proc, on_progress, diagnostics))
    try:
        await asyncio.wait_for(proc.wait(), timeout=RIP_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        streamer.cancel()
        return RipResult(
            ok=False,
            error=_compose_error(f"makemkvcon timed out after {RIP_TIMEOUT_SECONDS}s", diagnostics),
        )
    finally:
        # Cancel-safe cleanup: if the parent task was cancelled (abandon
        # flow), the subprocess is still running and holding fds on the raw
        # dir. Kill it before letting CancelledError propagate so rmtree
        # can finish clean.
        if proc.returncode is None:
            proc.kill()
            try:
                await proc.wait()
            except BaseException:
                pass
        streamer.cancel()

    if proc.returncode != 0:
        stderr = b""
        if proc.stderr is not None:
            stderr = await proc.stderr.read()
        msg = stderr.decode(errors="replace").strip()[:400] or f"exit={proc.returncode}"
        return RipResult(ok=False, error=_compose_error(f"makemkvcon failed: {msg}", diagnostics))

    output_file = _find_output_file(output_dir, title_index)
    if output_file is None:
        # makemkvcon often exits 0 even when the title couldn't be saved
        # (e.g. region-locked BD with the workaround failing, scratched
        # disc raising MSG:1002). The diagnostics list carries the actual
        # MakeMKV-side reason.
        return RipResult(
            ok=False,
            error=_compose_error("makemkvcon exited 0 but produced no .mkv", diagnostics),
        )

    size = output_file.stat().st_size
    digest = await sha256_file(output_file)
    return RipResult(
        ok=True,
        output_path=output_file,
        size_bytes=size,
        duration_seconds=expected_duration_seconds,
        sha256=digest,
    )
