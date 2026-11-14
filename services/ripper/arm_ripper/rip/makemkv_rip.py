"""Single-invocation MakeMKV rip.

`rip_disc` shells out to `makemkvcon mkv ... all <outdir>` exactly once
per disc. The drive stays open for the entire rip, so
the between-titles SCSI NOT_READY / USB-autosuspend gap that plagued
the per-title implementation simply doesn't exist anymore.

Per-title attribution is reconstructed from the robot stream:
  - PRGC:5017 ("Saving to MKV file") lines fire once at the start of
    every title save; the second field is the *output position* (0-based)
    that matches the `_tNN.mkv` filename suffix and indexes into
    `eligible_source_indexes` to recover the source title index. This
    is the primary per-title milestone in `mkv all` mode (confirmed
    empirically against MakeMKV 1.18.3 — the older PRGT "Saving title
    #N" milestone never fires in this mode).
  - PRGV gives [0..1] fractional progress; `current/max` is per-title
    (drives `on_title_progress`), `total/max` is disc-overall (used as
    a fallback `on_disc_progress` for the brief window before the first
    PRGC:5017 arrives).
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
from dataclasses import dataclass
from pathlib import Path

from arm_ripper.rip.hashing import sha256_file
from arm_ripper.rip.makemkv_process import run_makemkvcon
from arm_ripper.rip.makemkv_stream import (
    OnDiscProgress,
    OnTitleDone,
    OnTitleProgress,
    OnTitleStart,
    ParserState,
    RipCallbacks,
    finish_pending_titles,
)
from arm_ripper.rip.result import RipResult
from arm_ripper.source import makemkv_source_url

logger = logging.getLogger("arm_ripper.rip.makemkv")

OUTPUT_FILE_RE = re.compile(r"_t(\d+)\.mkv$", re.IGNORECASE)


def output_files_in_rip_order(output_dir: Path) -> list[Path]:
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
        m = OUTPUT_FILE_RE.search(f.name)
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


def _mkv_all_command(device_path: str, output_dir: Path, minlength_seconds: int) -> list[str]:
    """The single `makemkvcon mkv … all` argv that rips every title of the disc in one invocation."""
    return [
        "makemkvcon",
        "mkv",
        "--robot",
        "--progress=-stdout",
        f"--minlength={minlength_seconds}",
        makemkv_source_url(device_path),
        "all",
        str(output_dir),
    ]


async def _attribute_outputs(output_dir: Path, eligible: list[int], hash_outputs: bool) -> dict[int, RipResult]:
    """Pair each eligible source index with the output file in its rip position.

    Files past the eligible list stay unclaimed.
    """
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
    output_files = output_files_in_rip_order(output_dir)

    for source_idx, file_path in zip(eligible, output_files):
        size = file_path.stat().st_size
        digest = await sha256_file(file_path) if hash_outputs else None
        titles_out[source_idx] = RipResult(
            ok=True,
            output_path=file_path,
            size_bytes=size,
            sha256=digest,
        )
    return titles_out


def _failed_titles(state: ParserState, eligible: list[int], ripped: dict[int, RipResult]) -> dict[int, RipResult]:
    """Failures for titles without a file.

    A captured MSG:5003 reason comes first, then a generic "produced no .mkv" for each eligible title left over.
    """
    failed: dict[int, RipResult] = {}
    # If MSG:5003 captured a per-title failure reason and we didn't
    # produce a file for it (because the eligible list and files
    # ran out at different points), surface that reason via a
    # FAILED entry. Cheap belt-and-braces — most of the time
    # state.titles is empty in `mkv all` mode.
    for title_idx, ts in state.titles.items():
        if title_idx in ripped:
            continue
        if ts.fail_reason:
            failed[title_idx] = RipResult(ok=False, error=ts.fail_reason)

    # Eligible source indexes that didn't get a file *and* don't have
    # a captured failure reason are surfaced as a generic "produced no
    # .mkv" failure so the dispatcher can mark the track FAILED rather
    # than silently dropping it.
    for source_idx in eligible:
        if source_idx in ripped or source_idx in failed:
            continue
        failed[source_idx] = RipResult(
            ok=False,
            error="makemkvcon exited 0 but produced no .mkv for this title",
        )
    return failed


async def rip_disc(
    device_path: str,
    output_dir: Path,
    *,
    minlength_seconds: int = 120,
    eligible_source_indexes: list[int] | None = None,
    on_title_start: OnTitleStart | None = None,
    on_title_progress: OnTitleProgress | None = None,
    on_disc_progress: OnDiscProgress | None = None,
    on_title_done: OnTitleDone | None = None,
    hash_outputs: bool = True,
    stop: asyncio.Event | None = None,
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

    `stop`, when set mid-rip, kills makemkvcon and returns STOPPED_ERROR as
    the overall error (see run_makemkvcon).

    `hash_outputs=False` leaves `sha256` unset on every result: the
    dispatcher hashes each title itself as soon as it is written, so the
    pass overlaps the rip instead of re-reading every file after it.

    Returns a `RipDiscResult` whose `titles` dict maps source title
    index to a RipResult. The dispatcher cross-references this with
    the user's track selection: titles in the dict with ok=True got
    their files; titles absent (despite being eligible) didn't render
    and are FAILED.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    cmd = _mkv_all_command(device_path, output_dir, minlength_seconds)
    logger.info(
        "makemkvcon mkv all device=%s outdir=%s minlength=%ds",
        device_path,
        output_dir,
        minlength_seconds,
    )

    state = ParserState()
    error = await run_makemkvcon(
        cmd,
        state,
        callbacks=RipCallbacks(
            on_title_start=on_title_start,
            on_title_progress=on_title_progress,
            on_disc_progress=on_disc_progress,
            on_title_done=on_title_done,
        ),
        eligible_source_indexes=eligible_source_indexes,
        stop=stop,
    )
    if error is not None:
        return RipDiscResult(overall_error=error, titles={})

    await finish_pending_titles(state, on_title_done)

    eligible = eligible_source_indexes or []
    titles_out = await _attribute_outputs(output_dir, eligible, hash_outputs)

    titles_out.update(_failed_titles(state, eligible, titles_out))

    return RipDiscResult(overall_error=None, titles=titles_out)
