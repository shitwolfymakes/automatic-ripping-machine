"""The stager: copies ripped tracks from /raw into staging, one at a time (#708, D4).

A `TrackStager` worker runs in the backend. It claims a PENDING `track_stages`
row whose track finished ripping, places the file (a hard link when raw and
staging share a mount, else a resumable checkpointed copy), records the SHA-256
of the bytes it read from raw, and commits STAGED. Every disk write is behind a
checkpoint the database has seen, so a crash resumes instead of restarting.

Layout, top to bottom: pure decisions, the claim, the blocking placement, the
progress publisher, one run (`_StageRun`), the worker loop, the startup sweep.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.config import Settings, staging_root
from arm_backend.staging import emit_stage_event
from arm_common import StageStatus, Track, TrackStage, TrackStatus
from arm_common.fileops import (
    INPROGRESS_SUFFIX,
    CopyCancelled,
    LinkUnavailable,
    PlaceResult,
    SourceChanged,
    SourceStamp,
    copy_file_resumable,
    hash_file,
    inprogress_path,
    is_placed,
    place_by_link,
)

if TYPE_CHECKING:
    from arm_backend.ws.hub import WSHub

logger = logging.getLogger("arm_backend.stager")

# How long an idle worker waits for a wake before it looks for work again.
IDLE_POLL_SECONDS = 5.0
# How often a running copy's progress is published and its stall checked.
PROGRESS_INTERVAL_SECONDS = 2.0
SOURCE_MISSING = "raw source missing"
_ERROR_CHARS = 300

DbFactory = Callable[[], AsyncSession]


# --- Pure decisions ---------------------------------------------------------------------------


def is_stalled(last_advance: float, now: float, threshold: float) -> bool:
    """True when no byte has moved for more than `threshold` seconds."""
    return now - last_advance > threshold


def status_after_failure(attempts: int, max_attempts: int) -> StageStatus:
    """Where a stage goes after an attempt failed: another try while attempts remain, else FAILED."""
    return StageStatus.PENDING if attempts < max_attempts else StageStatus.FAILED


def transfer_rate(delta_bytes: int, delta_seconds: float) -> float:
    """Bytes per second over an interval; 0 for an empty interval."""
    return delta_bytes / delta_seconds if delta_seconds > 0 else 0.0


def eta_seconds(done: int, total: int, rate: float) -> int | None:
    """Seconds left at `rate`; None when nothing is moving."""
    return int((total - done) / rate) if rate > 0 else None


def refund_attempt(attempts: int) -> int:
    """An attempt that doesn't count (the source changed, or shutdown cut it short)."""
    return max(attempts - 1, 0)


def error_text(exc: BaseException) -> str:
    """`last_error` text for an exception."""
    return f"{type(exc).__name__}: {exc}"[:_ERROR_CHARS]


# --- Claim --------------------------------------------------------------------------------------


async def claim_next_stage(db: AsyncSession, hub: WSHub) -> str | None:
    """Claim the oldest PENDING stage whose track finished ripping; commits. Returns its id, or None."""
    stage = (
        await db.execute(
            select(TrackStage)
            .join(Track, col(Track.id) == col(TrackStage.track_id))
            .where(col(TrackStage.status) == StageStatus.PENDING, col(Track.status) == TrackStatus.DONE)
            .order_by(col(TrackStage.created_at))
            .limit(1)
            .with_for_update(skip_locked=True, of=TrackStage)
        )
    ).scalar_one_or_none()
    if stage is None:
        return None
    stage.status = StageStatus.COPYING
    stage.attempts = (stage.attempts or 0) + 1
    stage.heartbeat_at = datetime.now(UTC)
    stage.last_error = None
    stage_id = stage.id
    await emit_stage_event(hub, db, "stage.started", stage)
    await db.commit()
    return stage_id


# --- Blocking placement (worker thread) -------------------------------------------------------


class _StageProgress:
    """Bytes placed so far. The worker thread writes it; the publisher reads it."""

    def __init__(self, total: int, clock: Callable[[], float]) -> None:
        self.total = total
        self.done = 0
        self.linked: bool | None = None  # unknown until the link attempt is over
        self._clock = clock
        self.last_advance = clock()

    def add(self, n: int) -> None:
        self.done += n
        self.last_advance = self._clock()


@dataclass(frozen=True)
class _Plan:
    """Everything the blocking placement and the publisher need, read from the claimed row."""

    stage_id: str
    track_id: str
    job_id: str
    source: Path
    dest: Path
    stamp: SourceStamp
    resume_from: int


def _current_stamp(path: Path) -> SourceStamp | None:
    """The file's stamp, or None when it can't be read."""
    try:
        return SourceStamp.of(path)
    except OSError:
        return None


def _row_stamp(stage: TrackStage) -> SourceStamp | None:
    """The stamp recorded on the row, or None before the first run."""
    if stage.source_size is None or stage.source_mtime_ns is None:
        return None
    return SourceStamp(size=stage.source_size, mtime_ns=stage.source_mtime_ns)


def _file_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def _adopt_placed(source: Path, dest: Path, cancel: threading.Event, progress: _StageProgress) -> PlaceResult:
    """A finished placement whose commit was lost: hash raw once and report it."""
    digest = hash_file(source, cancel=cancel, on_bytes=progress.add)
    return PlaceResult(size=dest.stat().st_size, sha256=digest, linked=source.samefile(dest))


def place_staged(
    plan: _Plan,
    cancel: threading.Event,
    progress: _StageProgress,
    on_checkpoint: Callable[[int], None],
) -> PlaceResult:
    """Put the source at the destination: adopt a finished placement, else link, else copy.

    The stager never renames, because raw must survive for a re-stage."""
    if plan.resume_from == 0 and is_placed(plan.stamp, plan.dest):
        return _adopt_placed(plan.source, plan.dest, cancel, progress)
    try:
        return place_by_link(
            plan.source, plan.dest, keep_source=True, expect=plan.stamp, cancel=cancel, on_bytes=progress.add
        )
    except LinkUnavailable:
        progress.linked = False
    return copy_file_resumable(
        plan.source,
        plan.dest,
        resume_from=plan.resume_from,
        expect=plan.stamp,
        cancel=cancel,
        on_bytes=progress.add,
        on_checkpoint=on_checkpoint,
    )


def _remove_staged_files(dest: Path) -> None:
    """Delete a destination and its temp file."""
    inprogress_path(dest).unlink(missing_ok=True)
    dest.unlink(missing_ok=True)


# --- Progress publisher -----------------------------------------------------------------------


class _ProgressPublisher:
    """While a copy runs: move `heartbeat_at` when bytes advance, publish progress, call a stall."""

    def __init__(self, run: _StageRun, progress: _StageProgress) -> None:
        self._run = run
        self._progress = progress
        self._last_done = progress.done
        self._last_time = run.clock()

    async def run(self, stop: asyncio.Event) -> None:
        """Tick every `PROGRESS_INTERVAL_SECONDS` until `stop` is set."""
        while True:
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), PROGRESS_INTERVAL_SECONDS)
            if stop.is_set():
                return
            try:
                await self._tick()
            except Exception as exc:
                # Telemetry and the stall watch only: the copy carries on.
                logger.warning("stage progress tick failed stage_id=%s: %s", self._run.plan.stage_id, exc)

    async def _tick(self) -> None:
        now = self._run.clock()
        done = self._progress.done
        if done != self._last_done:
            await self._run.write_heartbeat()
        elif not self._run.stalled and is_stalled(
            self._progress.last_advance, now, self._run.settings.ARM_STAGE_STALL_SECONDS
        ):
            await self._run.mark_stalled(now - self._progress.last_advance)
        rate = transfer_rate(done - self._last_done, now - self._last_time)
        self._last_done, self._last_time = done, now
        await self._emit(done, rate)

    async def _emit(self, done: int, rate: float) -> None:
        plan = self._run.plan
        await self._run.hub.emit(
            topic=f"staging.progress.{plan.track_id}",
            event_type="stage.progress",
            payload={
                "track_id": plan.track_id,
                "job_id": plan.job_id,
                "bytes_done": done,
                "bytes_total": self._progress.total,
                "rate_bps": rate,
                "eta_seconds": eta_seconds(done, self._progress.total, rate),
                "linked": self._progress.linked,
            },
            persist=False,
            job_id=plan.job_id,
            track_id=plan.track_id,
        )


# --- One run ----------------------------------------------------------------------------------


class _StageGone(Exception):
    """The stage row was deleted while the run held it (its job went away)."""


class _StageRun:
    """One claimed stage, from placement to its terminal transition."""

    plan: _Plan

    def __init__(
        self,
        stage_id: str,
        settings: Settings,
        hub: WSHub,
        db_factory: DbFactory,
        cancel: threading.Event,
        clock: Callable[[], float],
    ) -> None:
        self.stage_id = stage_id
        self.settings = settings
        self.hub = hub
        self.clock = clock
        self.cancel = cancel
        self.stalled = False
        self._db_factory = db_factory

    async def run(self) -> None:
        """Place the file and write the outcome. A deleted row ends the run quietly."""
        try:
            plan = await self._prepare()
            if plan is not None:
                self.plan = plan
                await self._place()
        except _StageGone:
            logger.info("stage_id=%s deleted mid-run; nothing to record", self.stage_id)

    @contextlib.asynccontextmanager
    async def stage_txn(self) -> AsyncIterator[tuple[AsyncSession, TrackStage]]:
        """A fresh session with the stage row locked; commits when the block ends."""
        async with self._db_factory() as db:
            stage = (
                await db.execute(select(TrackStage).where(col(TrackStage.id) == self.stage_id).with_for_update())
            ).scalar_one_or_none()
            if stage is None:
                raise _StageGone
            yield db, stage
            await db.commit()

    # -- start --

    async def _prepare(self) -> _Plan | None:
        """Read the claimed row, stamping the source on a first run. None when the source is gone."""
        async with self.stage_txn() as (db, stage):
            source = Path(stage.source_path)
            current = _current_stamp(source)
            if current is None:
                await self._fail(db, stage, SOURCE_MISSING)
                return None
            stamp = _row_stamp(stage)
            if stamp is None:
                stamp = current
                stage.source_size, stage.source_mtime_ns = stamp.size, stamp.mtime_ns
            return _Plan(
                stage_id=stage.id,
                track_id=stage.track_id,
                job_id=stage.job_id,
                source=source,
                dest=Path(stage.dest_path),
                stamp=stamp,
                resume_from=stage.bytes_durable,
            )

    # -- the blocking part --

    async def _place(self) -> None:
        """Run the placement in a thread beside the publisher, then settle the outcome."""
        progress = _StageProgress(self.plan.stamp.size, self.clock)
        stop = asyncio.Event()
        publisher = asyncio.ensure_future(_ProgressPublisher(self, progress).run(stop))
        loop = asyncio.get_running_loop()

        def on_checkpoint(offset: int) -> None:
            # Runs on the worker thread and blocks the copy until the commit lands, so the
            # database never runs ahead of the disk (the copier fsynced before calling).
            asyncio.run_coroutine_threadsafe(self._commit_checkpoint(offset), loop).result()

        outcome: PlaceResult | CopyCancelled | OSError
        try:
            outcome = await asyncio.to_thread(place_staged, self.plan, self.cancel, progress, on_checkpoint)
        except (CopyCancelled, OSError) as exc:
            outcome = exc
        finally:
            await self._stop_publisher(publisher, stop)
        await self._settle(outcome)

    async def _stop_publisher(self, publisher: asyncio.Future[None], stop: asyncio.Event) -> None:
        """Stop the publisher and wait for it, so nothing else writes the row while it is settled."""
        stop.set()
        try:
            await publisher
        except Exception:
            logger.exception("stage progress publisher failed stage_id=%s", self.stage_id)

    async def _settle(self, outcome: PlaceResult | CopyCancelled | OSError) -> None:
        """Pick the terminal transition for how the placement ended."""
        if self.stalled:
            await self._after_stall()
        elif isinstance(outcome, PlaceResult):
            await self._commit_staged(outcome)
        elif isinstance(outcome, SourceChanged):
            await self._reset_for_changed_source()
        elif isinstance(outcome, CopyCancelled):
            await self._requeue_after_shutdown()
        else:
            await self._retry_or_fail(outcome)

    # -- writes while the copy runs --

    async def _commit_checkpoint(self, offset: int) -> None:
        """Record a durable offset, only while the row is still COPYING."""
        async with self._db_factory() as db:
            await db.execute(
                update(TrackStage)
                .where(col(TrackStage.id) == self.stage_id, col(TrackStage.status) == StageStatus.COPYING)
                .values(bytes_durable=offset)
            )
            await db.commit()

    async def write_heartbeat(self) -> None:
        """Bytes advanced: stamp `heartbeat_at` (a Core UPDATE; the row may be gone)."""
        async with self._db_factory() as db:
            await db.execute(
                update(TrackStage)
                .where(col(TrackStage.id) == self.stage_id, col(TrackStage.status) == StageStatus.COPYING)
                .values(heartbeat_at=datetime.now(UTC))
            )
            await db.commit()

    async def mark_stalled(self, idle_seconds: float) -> None:
        """No bytes for too long: STALLED, announce it, and ask the copy to stop."""
        async with self.stage_txn() as (db, stage):
            stage.status = StageStatus.STALLED
            stage.last_error = f"no progress for {int(idle_seconds)} s"
            await emit_stage_event(self.hub, db, "stage.stalled", stage)
        self.stalled = True
        self.cancel.set()

    # -- terminal transitions --

    async def _fail(self, db: AsyncSession, stage: TrackStage, reason: str) -> None:
        stage.status = StageStatus.FAILED
        stage.last_error = reason
        await emit_stage_event(self.hub, db, "stage.failed", stage)

    async def _commit_staged(self, result: PlaceResult) -> None:
        """The file is placed and verified: STAGED, with the digest on the track."""
        async with self.stage_txn() as (db, stage):
            stage.status = StageStatus.STAGED
            stage.staged_at = datetime.now(UTC)
            stage.linked = result.linked
            stage.bytes_durable = result.size
            stage.last_error = None
            track = (await db.execute(select(Track).where(col(Track.id) == stage.track_id))).scalar_one_or_none()
            if track is not None:
                track.sha256 = result.sha256
            await emit_stage_event(self.hub, db, "stage.completed", stage)

    async def _requeue_or_fail(self, db: AsyncSession, stage: TrackStage, error: str | None) -> None:
        """PENDING while attempts remain, else FAILED (announced)."""
        stage.status = status_after_failure(stage.attempts, self.settings.ARM_STAGE_MAX_ATTEMPTS)
        if error is not None:
            stage.last_error = error
        if stage.status == StageStatus.FAILED:
            await emit_stage_event(self.hub, db, "stage.failed", stage)

    async def _after_stall(self) -> None:
        """The thread returned after a stall; whatever it did is discarded (STALLED never commits STAGED)."""
        async with self.stage_txn() as (db, stage):
            await self._requeue_or_fail(db, stage, None)

    async def _retry_or_fail(self, failure: OSError) -> None:
        """A read or write error: try again from the last checkpoint, or give up."""
        async with self.stage_txn() as (db, stage):
            await self._requeue_or_fail(db, stage, error_text(failure))

    async def _reset_for_changed_source(self) -> None:
        """A re-rip replaced the source: start over without spending an attempt."""
        await asyncio.to_thread(_remove_staged_files, self.plan.dest)
        async with self.stage_txn() as (db, stage):
            stage.status = StageStatus.PENDING
            stage.attempts = refund_attempt(stage.attempts)
            stage.bytes_durable = 0
            stage.source_size = stage.source_mtime_ns = None
            stage.linked = None
            await emit_stage_event(self.hub, db, "stage.restarted", stage)

    async def _requeue_after_shutdown(self) -> None:
        """Shutdown stopped the copy at a chunk boundary: PENDING, keeping its last checkpoint."""
        async with self.stage_txn() as (_db, stage):
            stage.status = StageStatus.PENDING
            stage.attempts = refund_attempt(stage.attempts)


# --- The worker -------------------------------------------------------------------------------


class TrackStager:
    """First-in-first-out worker that stages ripped tracks, one at a time."""

    def __init__(
        self,
        settings: Settings,
        hub: WSHub,
        db_factory: DbFactory,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._hub = hub
        self._db_factory = db_factory
        self._clock = clock
        self._wake = asyncio.Event()
        self._stop = asyncio.Event()
        self._exited = asyncio.Event()
        self._running = False
        self._cancel = threading.Event()

    def wake(self) -> None:
        """New work may be waiting."""
        self._wake.set()

    async def run(self) -> None:
        """Claim, copy, commit; wait for a wake or `IDLE_POLL_SECONDS` when idle."""
        self._running = True
        try:
            while not self._stop.is_set():
                if not await self._work_once():
                    await self._idle()
        finally:
            self._exited.set()

    async def stop(self) -> None:
        """Ask the current copy to stop at a chunk boundary and return once `run` has exited."""
        self._stop.set()
        self._cancel.set()
        self._wake.set()
        if self._running:
            await self._exited.wait()

    async def _idle(self) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._wake.wait(), IDLE_POLL_SECONDS)

    async def _work_once(self) -> bool:
        """Stage one track. False when there was nothing to do (or the pass failed)."""
        self._wake.clear()
        self._cancel = threading.Event()
        try:
            stage_id = await self._claim()
            if stage_id is None:
                return False
            await _StageRun(stage_id, self._settings, self._hub, self._db_factory, self._cancel, self._clock).run()
        except Exception:
            logger.exception("stager pass failed")
            return False
        return True

    async def _claim(self) -> str | None:
        async with self._db_factory() as db:
            return await claim_next_stage(db, self._hub)


# The stager the running backend uses, so a fan-out can wake it (see `set_active_stager`).
_active_stager: TrackStager | None = None


def set_active_stager(stager: TrackStager | None) -> None:
    """Publish the running stager (or clear it)."""
    global _active_stager
    _active_stager = stager


def wake_active_stager() -> None:
    """Tell the running stager that work was queued; a no-op when none runs."""
    if _active_stager is not None:
        _active_stager.wake()


# --- Startup sweep ----------------------------------------------------------------------------


class SweepAction(StrEnum):
    KEEP = "keep"
    FAIL_SOURCE_MISSING = "fail_source_missing"
    RESET_CHANGED_SOURCE = "reset_changed_source"
    REQUEUE_PLACED = "requeue_placed"
    REQUEUE_RESUME = "requeue_resume"
    REQUEUE_FRESH = "requeue_fresh"
    RESTAGE = "restage"


@dataclass(frozen=True)
class DiskFacts:
    """What the disk says about one stage row."""

    source_exists: bool
    source_changed: bool  # the row is stamped and the source no longer matches it
    placed: bool  # the destination is a finished placement of the stamped source
    temp_exists: bool
    dest_intact: bool  # the destination exists and has the stamped size


def _classify_interrupted(facts: DiskFacts) -> SweepAction:
    """A COPYING or STALLED row: the process died or stalled mid-copy."""
    if not facts.source_exists:
        return SweepAction.FAIL_SOURCE_MISSING
    if facts.source_changed:
        return SweepAction.RESET_CHANGED_SOURCE
    if facts.placed:
        return SweepAction.REQUEUE_PLACED
    if facts.temp_exists:
        return SweepAction.REQUEUE_RESUME
    return SweepAction.REQUEUE_FRESH


def classify_stage(status: StageStatus, facts: DiskFacts) -> SweepAction:
    """What the startup sweep does with a row."""
    if status in (StageStatus.COPYING, StageStatus.STALLED):
        return _classify_interrupted(facts)
    if status == StageStatus.STAGED and not facts.dest_intact:
        return SweepAction.RESTAGE
    return SweepAction.KEEP


def observe_stage(stage: TrackStage) -> DiskFacts:
    """Read the disk facts `classify_stage` needs."""
    source, dest = Path(stage.source_path), Path(stage.dest_path)
    current, row_stamp, dest_size = _current_stamp(source), _row_stamp(stage), _file_size(dest)
    return DiskFacts(
        source_exists=current is not None,
        source_changed=row_stamp is not None and current != row_stamp,
        placed=row_stamp is not None and is_placed(row_stamp, dest),
        temp_exists=inprogress_path(dest).exists(),
        dest_intact=dest_size is not None and dest_size == stage.source_size,
    )


def _sweep_fail_source_missing(stage: TrackStage) -> None:
    stage.status = StageStatus.FAILED
    stage.last_error = SOURCE_MISSING


def _sweep_reset_changed_source(stage: TrackStage) -> None:
    _remove_staged_files(Path(stage.dest_path))
    stage.status = StageStatus.PENDING
    stage.bytes_durable = 0
    stage.source_size = stage.source_mtime_ns = None
    stage.linked = None


def _sweep_requeue_placed(stage: TrackStage) -> None:
    # The worker adopts the finished file: it hashes raw once and commits STAGED.
    stage.status = StageStatus.PENDING
    stage.bytes_durable = 0


def _sweep_requeue_resume(stage: TrackStage) -> None:
    # The copier truncates the temp file to `bytes_durable` (or restarts when it is short).
    stage.status = StageStatus.PENDING


def _sweep_requeue_fresh(stage: TrackStage) -> None:
    stage.status = StageStatus.PENDING
    stage.bytes_durable = 0


def _sweep_restage(stage: TrackStage) -> None:
    inprogress_path(Path(stage.dest_path)).unlink(missing_ok=True)
    stage.status = StageStatus.PENDING
    stage.bytes_durable = 0
    stage.linked = None
    stage.staged_at = None


_SWEEP_HANDLERS: dict[SweepAction, Callable[[TrackStage], None]] = {
    SweepAction.FAIL_SOURCE_MISSING: _sweep_fail_source_missing,
    SweepAction.RESET_CHANGED_SOURCE: _sweep_reset_changed_source,
    SweepAction.REQUEUE_PLACED: _sweep_requeue_placed,
    SweepAction.REQUEUE_RESUME: _sweep_requeue_resume,
    SweepAction.REQUEUE_FRESH: _sweep_requeue_fresh,
    SweepAction.RESTAGE: _sweep_restage,
}


def _sweep_stage_row(stage: TrackStage) -> bool:
    """Apply the sweep to one row; True when it changed."""
    action = classify_stage(stage.status, observe_stage(stage))
    if action == SweepAction.KEEP:
        return False
    _SWEEP_HANDLERS[action](stage)
    return True


def _orphan_temp_files(root: Path, live_dests: set[str]) -> list[Path]:
    """`*.arm-inprogress` files under `root` whose final path no PENDING or COPYING row owns."""
    if not root.exists():
        return []
    return [p for p in root.rglob(f"*{INPROGRESS_SUFFIX}") if str(p.with_suffix("")) not in live_dests]


def _delete_orphans(orphans: list[Path]) -> int:
    deleted = 0
    for path in orphans:
        try:
            path.unlink()
        except OSError as exc:
            logger.warning("failed to delete staging orphan path=%s err=%s", path, exc)
            continue
        deleted += 1
        logger.info("swept staging orphan path=%s", path)
    return deleted


async def sweep_track_stages(db: AsyncSession, settings: Settings) -> int:
    """Reconcile stage rows with the disk after a restart; returns how many rows and files it touched.

    Attempts are never incremented here. The caller commits."""
    stages = (await db.execute(select(TrackStage))).scalars().all()
    changed = sum(_sweep_stage_row(stage) for stage in stages)
    await db.flush()
    live = {s.dest_path for s in stages if s.status in (StageStatus.PENDING, StageStatus.COPYING)}
    return changed + _delete_orphans(_orphan_temp_files(staging_root(settings), live))
