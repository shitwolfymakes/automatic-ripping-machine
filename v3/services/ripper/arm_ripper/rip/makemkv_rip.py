"""Single-invocation MakeMKV rip.

`rip_disc` shells out to `makemkvcon mkv ... all <outdir>` exactly once
per disc — the v2 pattern. The drive stays open for the entire rip, so
the between-titles SCSI NOT_READY / USB-autosuspend gap that plagued
the per-title implementation simply doesn't exist anymore.

Per-title attribution is reconstructed from the robot stream:
  - PRGT lines whose text starts with "Saving title N" tell us which
    title is currently being written → fire `on_title_start`.
  - PRGV gives [0..1] fractional progress for the current operation →
    fire `on_title_progress(current_title, fraction)`.
  - MSG:5003 lines tell us a title failed (with reason). We capture the
    title index from the args.
  - Post-exit, we walk `output_dir` for `title_tNN.mkv` files: a file
    that exists for an attempted title means success; an attempted
    title with no file means failure (reason from MSG:5003 if any,
    otherwise "no .mkv produced").

Tracks that were *not* attempted by makemkvcon (below `--minlength`)
never appear in the result map; the dispatcher decides what to do
with them (typically: mark FAILED with "skipped: below minlength").
"""

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from arm_ripper.rip.hashing import sha256_file

logger = logging.getLogger("arm_ripper.rip.makemkv")

RIP_TIMEOUT_SECONDS = 6 * 60 * 60  # 6 hours: worst-case BD

OnTitleStart = Callable[[int], Awaitable[None]]
OnTitleProgress = Callable[[int, float], Awaitable[None]]

_PRGV_RE = re.compile(r"^PRGV:(\d+),(\d+),(\d+)$")
_PRGT_RE = re.compile(r'^PRGT:(\d+),(\d+),"(.*)"$')
_MSG_HEADER_RE = re.compile(r"^MSG:(\d+),(\d+),(\d+),")
_QUOTED_ARG_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
# PRGT text for the "now saving title N" milestone. Empirically
# emitted by MakeMKV at the start of every per-title save in `mkv all`
# mode; format is "Saving title #N to MKV file" or "Saving title N
# to MKV file" depending on version. The `#?` makes both work.
_PRGT_SAVING_TITLE_RE = re.compile(r"\btitle\s+#?(\d+)\b", re.IGNORECASE)

# MakeMKV codes worth surfacing in disc-level error text.
#  1002 — LIBMKV_TRACE Exception (e.g. "Error while reading input")
#  3032 — drive/disc region mismatch
#  5003 — Failed to save title N to file ... (per-title)
#  5037 — Copy complete. X titles saved, Y failed (final summary)
# Reference: https://github.com/automatic-ripping-machine/automatic-ripping-machine/wiki/MakeMKV-Codes
_DIAGNOSTIC_MSG_CODES = frozenset({1002, 3032, 5003, 5037})

# MSG codes we recognise for per-title outcomes. 5003 carries the
# failure reason; we don't need a success code because file existence
# in the output dir is the source of truth for "title saved ok".
_TITLE_FAIL_CODE = 5003


@dataclass
class RipResult:
    ok: bool
    output_path: Path | None = None
    size_bytes: int | None = None
    duration_seconds: int | None = None
    sha256: str | None = None
    error: str | None = None


@dataclass
class _TitleState:
    """Per-title state reconstructed from the stream."""

    fail_reason: str | None = None
    started_emitted: bool = False


@dataclass
class _ParserState:
    """Shared mutable state for the stream parser. Callbacks fire from
    inside the streamer task; the dispatcher resolves title_index →
    TrackView upstream of us."""

    titles: dict[int, _TitleState] = field(default_factory=dict)
    current_title: int | None = None
    diagnostics: list[str] = field(default_factory=list)


def parse_progress_line(line: str) -> float | None:
    """Return the fractional progress [0, 1] from a PRGV line, or None."""
    m = _PRGV_RE.match(line.strip())
    if not m:
        return None
    _current, _total, max_ = (int(g) for g in m.groups())
    if max_ <= 0:
        return None
    return min(1.0, max(0.0, _current / max_))


def parse_msg_args(line: str) -> tuple[int, list[str]] | None:
    """Parse a MSG: line into (code, args). args is the list of trailing
    quoted strings *after* the rendered text and format string — i.e.
    the substitution arguments. Returns None if the line isn't a MSG.
    """
    header = _MSG_HEADER_RE.match(line.strip())
    if not header:
        return None
    code = int(header.group(1))
    quoted = [m.group(1) for m in _QUOTED_ARG_RE.finditer(line)]
    # args[0] = rendered text, args[1] = format string, args[2:] = substitution values.
    args = [a.replace('\\"', '"') for a in quoted[2:]]
    return code, args


def parse_diagnostic_msg(line: str) -> tuple[int, str] | None:
    """If `line` is a MSG: line whose code is in _DIAGNOSTIC_MSG_CODES,
    return (code, rendered_text). Otherwise None.

    Used by `_compose_error` to surface MakeMKV-side reasons when the
    overall rip exits non-zero (or exits 0 but produces no files).
    """
    header = _MSG_HEADER_RE.match(line.strip())
    if not header:
        return None
    code = int(header.group(1))
    if code not in _DIAGNOSTIC_MSG_CODES:
        return None
    quoted = _QUOTED_ARG_RE.search(line)
    if quoted is None:
        return None
    text = quoted.group(1).replace('\\"', '"')
    return code, text


def parse_prgt_title(line: str) -> int | None:
    """If `line` is a PRGT whose text announces "Saving title N to
    MKV file", return N. Otherwise None.

    PRGT is MakeMKV's "current operation text" channel. When MakeMKV
    starts writing a title in `mkv all` mode it emits a PRGT like
    `PRGT:5018,0,"Saving title #2 to MKV file"`. We use that as the
    transition signal for current-title state.
    """
    m = _PRGT_RE.match(line.strip())
    if not m:
        return None
    text = m.group(3)
    # Filter on "saving" to avoid matching e.g. "Reading information for title 3".
    if "saving" not in text.lower():
        return None
    title_match = _PRGT_SAVING_TITLE_RE.search(text)
    if not title_match:
        return None
    return int(title_match.group(1))


def _extract_title_index_from_msg5003(args: list[str]) -> int | None:
    """MSG:5003 args vary slightly across MakeMKV versions but always
    include the title index as one of the integer-string arguments.
    Heuristic: take the first arg that parses cleanly as an int."""
    for a in args:
        try:
            return int(a)
        except ValueError:
            continue
    return None


async def _stream_output(
    proc: asyncio.subprocess.Process,
    state: _ParserState,
    on_title_start: OnTitleStart | None,
    on_title_progress: OnTitleProgress | None,
) -> None:
    assert proc.stdout is not None
    while True:
        raw = await proc.stdout.readline()
        if not raw:
            return
        line = raw.decode(errors="replace").rstrip()
        if not line:
            continue

        # PRGV — fractional progress for the current operation. We
        # attribute it to `current_title` (set by the most recent
        # "Saving title N" PRGT). Pre-rip operations (analysing /
        # hashing) emit PRGV too; we skip those by gating on
        # current_title being set.
        progress = parse_progress_line(line)
        if progress is not None:
            if state.current_title is not None and on_title_progress is not None:
                try:
                    await on_title_progress(state.current_title, progress)
                except Exception as exc:
                    logger.debug("title progress callback raised: %s", exc)
            continue

        # PRGT — milestone text. Watch for "Saving title N" to update
        # current_title and fire on_title_start exactly once per title.
        title_idx = parse_prgt_title(line)
        if title_idx is not None:
            state.current_title = title_idx
            ts = state.titles.setdefault(title_idx, _TitleState())
            if not ts.started_emitted:
                ts.started_emitted = True
                if on_title_start is not None:
                    try:
                        await on_title_start(title_idx)
                    except Exception as exc:
                        logger.debug("title start callback raised: %s", exc)
            continue

        # Generic PRGT (other milestones) — log only.
        prgt = _PRGT_RE.match(line.strip())
        if prgt:
            logger.info("makemkvcon milestone: %s", prgt.group(3))
            continue

        if line.startswith("MSG:"):
            diag = parse_diagnostic_msg(line)
            if diag is not None:
                state.diagnostics.append(diag[1])
            parsed = parse_msg_args(line)
            if parsed is not None:
                code, args = parsed
                if code == _TITLE_FAIL_CODE:
                    fail_idx = _extract_title_index_from_msg5003(args)
                    rendered = next(iter(_QUOTED_ARG_RE.finditer(line)), None)
                    reason = rendered.group(1).replace('\\"', '"') if rendered else "save failed"
                    if fail_idx is not None:
                        ts = state.titles.setdefault(fail_idx, _TitleState())
                        ts.fail_reason = reason
                    else:
                        # Unattributable fail — append to overall diagnostics
                        # so the disc-level error captures it.
                        logger.warning("MSG:5003 without parseable title index: %s", line)
            logger.debug("makemkvcon: %s", line)


def _compose_error(prefix: str, diagnostics: list[str]) -> str:
    """Stitch the diagnostic MakeMKV messages onto the failure summary so
    the dispatcher can surface the actual cause (e.g. "Error while reading
    input", "Failed to save title 2 to file ...") instead of just the
    generic exit-code wrapper."""
    if not diagnostics:
        return prefix
    seen: list[str] = []
    for d in diagnostics:
        if not seen or seen[-1] != d:
            seen.append(d)
    return f"{prefix}: {'; '.join(seen)}"


_OUTPUT_FILE_RE = re.compile(r"_t(\d+)\.mkv$", re.IGNORECASE)


def _output_files_in_rip_order(output_dir: Path) -> list[Path]:
    """Return the `.mkv` files MakeMKV produced, sorted by their `_tNN`
    suffix (the per-rip output index, ascending).

    MakeMKV in `mkv ... all <outdir>` mode writes files named
    `<volume_label>_tNN.mkv` (or `<custom_template>_tNN.mkv` if the
    user has tweaked their MakeMKV profile). The suffix `NN` is the
    *position in the eligible-rip output*, not the source title index.
    Example: a Blu-ray with source titles {0, 1, 2, ...} where only
    titles 0 and 2 met `--minlength` produces `<label>_t00.mkv`
    (= source 0) and `<label>_t01.mkv` (= source 2).

    Files without a parseable `_tNN.mkv` suffix (legacy strays, partial
    writes from a crashed earlier run, etc.) are skipped.
    """
    pairs: list[tuple[int, Path]] = []
    for f in output_dir.glob("*.mkv"):
        m = _OUTPUT_FILE_RE.search(f.name)
        if not m:
            continue
        pairs.append((int(m.group(1)), f))
    pairs.sort(key=lambda p: p[0])
    return [p for _, p in pairs]


@dataclass
class RipDiscResult:
    """Outcome of one `rip_disc` invocation.

    `overall_error` is set when makemkvcon itself failed (non-zero exit,
    timeout, exec error). When `overall_error` is None the rip ran to
    completion; per-title outcomes live in `titles` and the dispatcher
    looks them up to attribute success/failure to track records.
    """

    overall_error: str | None
    titles: dict[int, RipResult]


async def rip_disc(
    device_path: str,
    output_dir: Path,
    *,
    minlength_seconds: int = 120,
    eligible_source_indexes: list[int] | None = None,
    on_title_start: OnTitleStart | None = None,
    on_title_progress: OnTitleProgress | None = None,
) -> RipDiscResult:
    """Rip every title with duration ≥ `minlength_seconds` from the disc
    in `device_path` to `output_dir`. Single makemkvcon invocation; the
    drive stays open for the duration of the rip.

    `eligible_source_indexes` is the list of *source* title indexes
    the dispatcher expects MakeMKV to rip — i.e. those whose duration
    is ≥ `minlength_seconds`, sorted ascending. Required for correct
    attribution because MakeMKV's `mkv all` output filenames carry an
    output-position suffix (`_t00`, `_t01`, ...) rather than the
    source title index, and the robot stream emits no per-title MSG /
    PRGT we can rely on (empirically silent on MakeMKV 1.17.5+ in
    `mkv all` mode). We pair `eligible_source_indexes[i]` with the
    file whose suffix is `_t{i:02d}` to get back to source-index
    keys. Pass `None` (or `[]`) only if the caller will handle
    attribution itself; the result will have an empty `titles` dict.

    Returns a `RipDiscResult` whose `titles` dict maps source title
    index to a RipResult. The dispatcher cross-references this with
    the user's track selection: titles in the dict with ok=True got
    their files; titles absent (despite being eligible) didn't render
    and are FAILED.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "makemkvcon",
        "mkv",
        "--robot",
        "--progress=-stdout",
        f"--minlength={minlength_seconds}",
        f"dev:{device_path}",
        "all",
        str(output_dir),
    ]
    logger.info(
        "makemkvcon mkv all device=%s outdir=%s minlength=%ds",
        device_path,
        output_dir,
        minlength_seconds,
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as e:
        return RipDiscResult(overall_error=f"makemkvcon not on PATH: {e}", titles={})

    state = _ParserState()
    streamer = asyncio.create_task(_stream_output(proc, state, on_title_start, on_title_progress))
    try:
        await asyncio.wait_for(proc.wait(), timeout=RIP_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        streamer.cancel()
        return RipDiscResult(
            overall_error=_compose_error(
                f"makemkvcon timed out after {RIP_TIMEOUT_SECONDS}s",
                state.diagnostics,
            ),
            titles={},
        )
    finally:
        # Cancel-safe cleanup: parent abandon → CancelledError. Kill the
        # subprocess so /raw can be wiped without orphan fds.
        if proc.returncode is None:
            proc.kill()
            try:
                await proc.wait()
            except BaseException:
                pass
        streamer.cancel()

    # Drain the streamer so all PRGV / PRGT / MSG lines after EOF are processed
    # before we read state.titles below.
    try:
        await streamer
    except asyncio.CancelledError:
        pass

    if proc.returncode != 0:
        stderr = b""
        if proc.stderr is not None:
            stderr = await proc.stderr.read()
        msg = stderr.decode(errors="replace").strip()[:400] or f"exit={proc.returncode}"
        return RipDiscResult(
            overall_error=_compose_error(f"makemkvcon failed: {msg}", state.diagnostics),
            titles={},
        )

    # Attribute output files to source title indexes.
    #
    # MakeMKV's `mkv all` mode is opaque per-title — the stream emits
    # only overall PRGT/MSG (5014 start, 5005/5036 summary). We get
    # back to per-title outcomes by pairing the eligible-source list
    # we were given with the output files in rip order. Files past
    # the eligible list are stragglers (e.g. user lowered minlength
    # mid-disc, MakeMKV picked up extras we didn't expect) and we
    # simply don't claim them — they remain on disk for inspection.
    titles_out: dict[int, RipResult] = {}
    output_files = _output_files_in_rip_order(output_dir)
    eligible = eligible_source_indexes or []

    for source_idx, file_path in zip(eligible, output_files):
        size = file_path.stat().st_size
        digest = await sha256_file(file_path)
        titles_out[source_idx] = RipResult(
            ok=True,
            output_path=file_path,
            size_bytes=size,
            sha256=digest,
        )

    # If MSG:5003 captured a per-title failure reason and we didn't
    # produce a file for it (because the eligible list and files
    # ran out at different points), surface that reason via a
    # FAILED entry. Cheap belt-and-braces — most of the time
    # state.titles is empty in `mkv all` mode.
    for title_idx, ts in state.titles.items():
        if title_idx in titles_out:
            continue
        if ts.fail_reason:
            titles_out[title_idx] = RipResult(ok=False, error=ts.fail_reason)

    # Eligible source indexes that didn't get a file *and* don't have
    # a captured failure reason are surfaced as a generic "produced no
    # .mkv" failure so the dispatcher can mark the track FAILED rather
    # than silently dropping it.
    for source_idx in eligible:
        if source_idx in titles_out:
            continue
        titles_out[source_idx] = RipResult(
            ok=False,
            error="makemkvcon exited 0 but produced no .mkv for this title",
        )

    return RipDiscResult(overall_error=None, titles=titles_out)
