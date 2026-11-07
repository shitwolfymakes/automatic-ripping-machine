"""The makemkvcon robot-stream state machine.

Reads each output line, keeps per-title state and fires the rip callbacks.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from arm_ripper.rip.makemkv_robot import (
    PRGT_RE,
    QUOTED_ARG_RE,
    TITLE_FAIL_CODE,
    extract_title_index_from_msg5003,
    parse_diagnostic_msg,
    parse_msg_args,
    parse_prgc_save_position,
    parse_prgt_title,
    parse_progress_totals,
)

logger = logging.getLogger("arm_ripper.rip.makemkv")

OnTitleStart = Callable[[int], Awaitable[None]]
OnTitleProgress = Callable[[int, float], Awaitable[None]]
# Fired the instant title N's save phase is known to be complete:
# either when PRGC:5017,N+1 transitions us off title N (MakeMKV has
# moved to the next title — N's file is finalised) or, for the last
# title in the rip, when makemkvcon exits cleanly. The dispatcher uses
# this to PATCH each Track DONE with size + output_path as it finishes
# instead of waiting for the whole `mkv all` invocation to end.
OnTitleDone = Callable[[int], Awaitable[None]]
# Fired with the disc-overall PRGV `total/max` fraction whenever no
# per-title PRGT has identified the title currently being written.
# `mkv all` mode is opaque per-title (a single "Saving all titles to
# MKV files" PRGT and that's it), so this callback is the only signal
# the dashboard ever gets during the rip phase. See dispatcher's
# `_on_disc_progress` for attribution to a track id.
OnDiscProgress = Callable[[float], Awaitable[None]]


@dataclass(frozen=True)
class RipCallbacks:
    """The progress callbacks a makemkvcon run reports through; each is optional."""

    on_title_start: OnTitleStart | None = None
    on_title_progress: OnTitleProgress | None = None
    on_disc_progress: OnDiscProgress | None = None
    on_title_done: OnTitleDone | None = None


@dataclass
class _TitleState:
    """Per-title state reconstructed from the stream."""

    fail_reason: str | None = None
    started_emitted: bool = False
    done_emitted: bool = False


@dataclass
class ParserState:
    """Shared mutable state for the stream parser. Callbacks fire from
    inside the streamer task; the dispatcher resolves title_index →
    TrackView upstream of us."""

    titles: dict[int, _TitleState] = field(default_factory=dict)
    current_title: int | None = None
    diagnostics: list[str] = field(default_factory=list)
    # Flips True when MakeMKV emits PRGT:5024 "Saving all titles to MKV
    # files" (the save phase boundary). Pre-rip PRGV events have a
    # `total/max` channel that reaches ~70-80% during analyse/decrypt
    # but isn't *rip* progress; firing the disc-overall fallback for
    # those would publish a misleading 70-80% to the dashboard then
    # snap to 0% when the first PRGC:5017 fires, breaking the ETA
    # baseline (rips store sees a sustained negative pctDelta and
    # holds ETA null until per-title progress climbs back past the
    # pre-rip peak — ~hours for a long main feature).
    save_phase_started: bool = False
    # Set when MakeMKV emits MSG:5021 (the binary's hard-coded 60-day
    # beta kill-switch). The streamer kills the subprocess as soon as
    # this is seen so a 6-hour RIP_TIMEOUT_SECONDS doesn't run out.
    # See docs/user/MakeMKV-Ripper.md § Failure modes.
    binary_expired: bool = False


async def _call_safely(label: str, callback: Callable[..., Awaitable[None]], *args: Any) -> None:
    """Await `callback(*args)`; a raise is logged at debug as "<label> callback raised: <exc>" and swallowed."""
    try:
        await callback(*args)
    except Exception as exc:
        logger.debug("%s callback raised: %s", label, exc)


async def _emit_title_start(
    state: ParserState,
    title_idx: int,
    on_title_start: OnTitleStart | None,
) -> None:
    """Set current_title and fire on_title_start exactly once per title."""
    state.current_title = title_idx
    ts = state.titles.setdefault(title_idx, _TitleState())
    if ts.started_emitted:
        return
    ts.started_emitted = True
    if on_title_start is not None:
        await _call_safely("title start", on_title_start, title_idx)


async def _emit_title_done(
    state: ParserState,
    title_idx: int,
    on_title_done: OnTitleDone | None,
) -> None:
    """Fire on_title_done exactly once per title."""
    ts = state.titles.setdefault(title_idx, _TitleState())
    if ts.done_emitted:
        return
    ts.done_emitted = True
    if on_title_done is not None:
        await _call_safely("title done", on_title_done, title_idx)


class _LineParser:
    """Applies makemkvcon robot lines one at a time to the parser state, firing the rip callbacks."""

    def __init__(
        self,
        proc: asyncio.subprocess.Process,
        state: ParserState,
        callbacks: RipCallbacks,
        eligible: list[int],
        gate_disc_progress: bool,
    ) -> None:
        self._proc = proc
        self._state = state
        self._callbacks = callbacks
        self._eligible = eligible
        self._gate_disc_progress = gate_disc_progress

    async def feed(self, line: str) -> None:
        """Apply one non-blank robot line through the first handler that takes it.

        Order matters: MSG:5021 is checked before everything else, and a PRGT title line before a generic milestone.
        """
        for apply in (
            self._apply_expiry,
            self._apply_progress,
            self._apply_save_position,
            self._apply_title_line,
            self._apply_milestone,
            self._apply_msg,
        ):
            if await apply(line):
                return

    async def _apply_expiry(self, line: str) -> bool:
        """MSG:5021 (the binary's kill switch), the first time it appears: record it and kill makemkvcon."""
        # Hard-coded 60-day kill-switch in the makemkv-bin blob. Kill the
        # subprocess so the 6-hour RIP_TIMEOUT_SECONDS doesn't fire — the
        # caller checks state.binary_expired to surface a distinct error.
        # See docs/user/MakeMKV-Ripper.md § Failure modes.
        if not self._state.binary_expired and line.startswith("MSG:5021,"):
            self._state.binary_expired = True
            self._state.diagnostics.append(line)
            self._proc.kill()
            return True
        return False

    async def _apply_progress(self, line: str) -> bool:
        """PRGV: per-title progress once a title is current, else the disc-overall fallback."""
        # PRGV — two channels in one line:
        #   `current/max` advances per-operation (resets per title)
        #   `total/max`   advances disc-overall (monotonic *within
        #                 each makemkvcon phase*; pre-rip analyse can
        #                 itself reach 70-80% before the save phase
        #                 starts and resets it back to 0)
        # When PRGC:5017 has identified the current title, drive the
        # per-title callback with `current/max`. Otherwise — only
        # if we've entered the save phase — fall back to the
        # disc-overall callback so the dashboard bar still advances
        # in the brief window before the first PRGC:5017 (or for the
        # whole save phase on hypothetical MakeMKV builds that don't
        # emit PRGC:5017). Pre-rip PRGV is silently dropped to keep
        # the rips-store ETA baseline anchored at per-title 0%.
        totals = parse_progress_totals(line)
        if totals is not None:
            cur_frac, tot_frac = totals
            if self._state.current_title is not None and self._callbacks.on_title_progress is not None:
                await _call_safely(
                    "title progress", self._callbacks.on_title_progress, self._state.current_title, cur_frac
                )
            elif (
                self._state.save_phase_started or not self._gate_disc_progress
            ) and self._callbacks.on_disc_progress is not None:
                await _call_safely("disc progress", self._callbacks.on_disc_progress, tot_frac)
            return True
        return False

    async def _apply_save_position(self, line: str) -> bool:
        """PRGC:5017: map the output position to its source title and start it, ending the previous one."""
        # PRGC:5017 — primary per-title signal in `mkv all` mode. The
        # second field is the output position (0-based) which we map
        # back to a source title index via the eligible list.
        out_pos = parse_prgc_save_position(line)
        if out_pos is not None:
            if 0 <= out_pos < len(self._eligible):
                source_idx = self._eligible[out_pos]
                # Transition signal: the previous title (if any) is now
                # finalised on disk — MakeMKV has closed its file and
                # moved on. Fire on_title_done before the next start so
                # the dispatcher can PATCH N=DONE before N+1 goes
                # IN_PROGRESS, keeping the lifecycle ordering clean.
                if self._state.current_title is not None and self._state.current_title != source_idx:
                    await _emit_title_done(self._state, self._state.current_title, self._callbacks.on_title_done)
                await _emit_title_start(self._state, source_idx, self._callbacks.on_title_start)
            else:
                logger.warning(
                    "PRGC:5017 output position %d out of range (eligible has %d entries)",
                    out_pos,
                    len(self._eligible),
                )
            return True
        return False

    async def _apply_title_line(self, line: str) -> bool:
        """A PRGT "Saving title N" line: start that title."""
        # PRGT — defensive fallback for older MakeMKV / per-title mode
        # which sometimes emits "Saving title N" instead of (or in
        # addition to) PRGC:5017. Guarded by `started_emitted` so a
        # late PRGT doesn't reset progress on a title PRGC already
        # opened.
        title_idx = parse_prgt_title(line)
        if title_idx is not None:
            await _emit_title_start(self._state, title_idx, self._callbacks.on_title_start)
            return True
        return False

    async def _apply_milestone(self, line: str) -> bool:
        """Any other PRGT: log the milestone, noting the save phase start (5024)."""
        # Generic PRGT (other milestones) — log; also detect the save
        # phase boundary (PRGT:5024 "Saving all titles to MKV files")
        # which gates the disc-overall PRGV fallback.
        prgt = PRGT_RE.match(line.strip())
        if prgt:
            if prgt.group(1) == "5024":
                self._state.save_phase_started = True
            logger.info("makemkvcon milestone: %s", prgt.group(3))
            return True
        return False

    async def _apply_msg(self, line: str) -> bool:
        """A MSG line: keep diagnostics, capture a MSG:5003 title failure, and log it at debug."""
        if line.startswith("MSG:"):
            diag = parse_diagnostic_msg(line)
            if diag is not None:
                self._state.diagnostics.append(diag[1])
            parsed = parse_msg_args(line)
            if parsed is not None:
                code, args = parsed
                if code == TITLE_FAIL_CODE:
                    self._record_title_failure(line, args)
            logger.debug("makemkvcon: %s", line)
            return True
        return False

    def _record_title_failure(self, line: str, args: list[str]) -> None:
        """Store a MSG:5003 failure reason on its title, or warn when the title index can't be found."""
        fail_idx = extract_title_index_from_msg5003(args)
        rendered = next(iter(QUOTED_ARG_RE.finditer(line)), None)
        reason = rendered.group(1).replace('\\"', '"') if rendered else "save failed"
        if fail_idx is not None:
            ts = self._state.titles.setdefault(fail_idx, _TitleState())
            ts.fail_reason = reason
        else:
            # Unattributable fail — append to overall diagnostics
            # so the disc-level error captures it.
            logger.warning("MSG:5003 without parseable title index: %s", line)


async def stream_output(
    proc: asyncio.subprocess.Process,
    state: ParserState,
    callbacks: RipCallbacks,
    eligible_source_indexes: list[int] | None = None,
    gate_disc_progress: bool = True,
) -> None:
    assert proc.stdout is not None
    parser = _LineParser(proc, state, callbacks, eligible_source_indexes or [], gate_disc_progress)
    while True:
        raw = await proc.stdout.readline()
        if not raw:
            return
        line = raw.decode(errors="replace").rstrip()
        if not line:
            continue
        # Raw makemkvcon line → DEBUG service log, then per-job log via
        # the backend's tailer. ~30 k lines per BD rip; gated on
        # ARM_LOG_LEVEL=debug so it's free in INFO-mode operation.
        logger.debug("makemkv-raw: %s", line)
        await parser.feed(line)


async def finish_pending_titles(state: ParserState, on_title_done: OnTitleDone | None) -> None:
    """Emit on_title_done for every title that started but never got its done, in source-index order."""
    # Final title's on_title_done — the streamer fires done at PRGC
    # transitions, but the last title in the rip never gets a follow-up
    # PRGC:5017,N+1. Catch any started-but-not-yet-done title here so
    # the dispatcher PATCHes it DONE before rip_disc returns.
    for source_idx in sorted(state.titles):
        ts = state.titles[source_idx]
        if ts.started_emitted and not ts.done_emitted:
            await _emit_title_done(state, source_idx, on_title_done)
