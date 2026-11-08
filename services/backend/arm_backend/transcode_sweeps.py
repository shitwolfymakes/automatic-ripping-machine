"""Recovery sweeps over the transcode queue.

Stale claims, orphaned applications and orphaned `.arm-inprogress` files.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import col, select

from arm_backend.config import Settings
from arm_backend.gpu_claim import release_gpu_for_task
from arm_common import (
    SessionApplication,
    SessionApplicationStatus,
    TranscodeTask,
    TranscodeTaskStatus,
    with_log_context,
)

if TYPE_CHECKING:
    from arm_backend.ws.hub import WSHub

logger = logging.getLogger(__name__)


class TranscodeSweeps:
    """The recovery passes: re-queue or fail stale claims, settle orphaned
    applications, delete orphaned `.arm-inprogress` files."""

    def __init__(self, settings: Settings, hub: WSHub, db_factory: async_sessionmaker[AsyncSession]) -> None:
        self._settings = settings
        self._hub = hub
        self._db_factory = db_factory

    # --- stale claim sweep ---------------------------------------------------

    async def sweep_stale_claims(self, db: AsyncSession) -> int:
        """Reset stale `in_progress` rows back to `queued` (or terminal-fail
        when attempts exhausted). Returns the number of rows touched.
        """
        threshold = datetime.now(UTC) - timedelta(seconds=self._settings.ARM_TRANSCODE_STALE_THRESHOLD_SECONDS)
        stale = (
            (
                await db.execute(
                    select(TranscodeTask)
                    .where(col(TranscodeTask.status) == TranscodeTaskStatus.IN_PROGRESS)
                    .where(col(TranscodeTask.claim_heartbeat_at) < threshold)
                )
            )
            .scalars()
            .all()
        )
        if not stale:
            return 0
        touched = 0
        for task in stale:
            # Per-task wrap so the per-job log view picks up every line emitted
            # for this task. job_id is loaded once via application.
            stale_application = (
                await db.execute(
                    select(SessionApplication).where(col(SessionApplication.id) == task.session_application_id)
                )
            ).scalar_one_or_none()
            stale_job_id = stale_application.job_id if stale_application is not None else None
            with with_log_context(
                job_id=stale_job_id,
                track_id=task.source_track_id,
                session_application_id=task.session_application_id,
            ):
                # Release any GPU this task held; a stale claim cannot be holding
                # a real container any more.
                await release_gpu_for_task(db, task.id)
                if task.attempts >= self._settings.ARM_TRANSCODE_MAX_ATTEMPTS:
                    task.status = TranscodeTaskStatus.FAILED
                    task.last_error = f"exceeded retry limit after stale claim (attempts={task.attempts})"
                    logger.error(
                        "transcode task hard-failed after %d stale resets task_id=%s",
                        task.attempts,
                        task.id,
                    )
                    from arm_backend.transcode_apply import emit_task_failed, settle_session_application

                    await emit_task_failed(self._hub, db, task)
                    # Race guard: the app row appearing between the two checks.
                    if stale_application is None:  # pragma: no cover
                        # Re-load defensively in case the row appeared between checks.
                        stale_application = (
                            await db.execute(
                                select(SessionApplication).where(
                                    col(SessionApplication.id) == task.session_application_id
                                )
                            )
                        ).scalar_one()
                    await settle_session_application(db, self._hub, stale_application)
                else:
                    task.status = TranscodeTaskStatus.QUEUED
                    task.claimed_by = None
                    task.claim_heartbeat_at = None
                    logger.warning(
                        "transcode task reset to queued after stale claim task_id=%s attempts=%d",
                        task.id,
                        task.attempts,
                    )
                touched += 1
        await db.commit()
        return touched

    # --- orphaned application sweep -------------------------------------------

    async def sweep_orphaned_applications(self, db: AsyncSession) -> int:
        """Resolve non-terminal session_applications that have no live task.

        A `queued`/`running` application older than the grace window with zero
        live tasks is an orphan (crash between fan-out and dispatch, or its
        tasks were evicted by another application's overwrite). Settle
        terminal-only ones via `aggregate_session_application`; mark true husks
        (zero tasks) `failed`. `waiting_identify` is out of scope by design.

        Acts only on apps with zero or only-terminal tasks — disjoint from every
        live writer, so it cannot race fan-out/claim/aggregate. Does NOT commit;
        the caller commits. Returns the number of applications acted on.
        """
        from arm_backend.transcode_apply import aggregate_session_application, emit_session_outcome

        threshold = datetime.now(UTC) - timedelta(seconds=self._settings.ARM_TRANSCODE_STALE_THRESHOLD_SECONDS)
        candidates = (
            (
                await db.execute(
                    select(SessionApplication)
                    .where(
                        col(SessionApplication.status).in_(
                            [SessionApplicationStatus.QUEUED, SessionApplicationStatus.RUNNING]
                        )
                    )
                    .where(col(SessionApplication.created_at) < threshold)
                )
            )
            .scalars()
            .all()
        )
        if not candidates:
            return 0

        acted = 0
        for application in candidates:
            tasks = (
                (
                    await db.execute(
                        select(TranscodeTask).where(col(TranscodeTask.session_application_id) == application.id)
                    )
                )
                .scalars()
                .all()
            )
            statuses = [t.status for t in tasks]
            has_live = any(s in (TranscodeTaskStatus.QUEUED, TranscodeTaskStatus.IN_PROGRESS) for s in statuses)
            if has_live:
                # Not an orphan — a live task will drive aggregate on completion.
                continue

            with with_log_context(
                job_id=application.job_id,
                session_application_id=application.id,
            ):
                if statuses:
                    # Only-terminal tasks: settle via the shared aggregate logic.
                    outcome = await aggregate_session_application(db, application)
                    if outcome.event_type is None:  # pragma: no cover
                        # Reached only if a live task reappears mid-sweep (a
                        # concurrent auto-retry re-queues a task between our task
                        # read and aggregate's re-read); declining to settle is
                        # then correct. Hard to hit deterministically in tests.
                        continue
                    event_type = outcome.event_type
                else:
                    # True husk: no tasks at all. Mark failed; reason lives in the
                    # log line + WS event (no error column on the model).
                    created_at = application.created_at or datetime.now(UTC)
                    age_s = int((datetime.now(UTC) - created_at).total_seconds())
                    application.status = SessionApplicationStatus.FAILED
                    application.completed_at = datetime.now(UTC)
                    logger.warning(
                        "session_application orphaned: no tasks (crash/eviction) sap=%s job=%s age=%ds",
                        application.id,
                        application.job_id,
                        age_s,
                    )
                    event_type = "session.failed"

                try:
                    await emit_session_outcome(self._hub, db, application, event_type)
                except Exception as exc:  # WS is best-effort; status already set
                    logger.warning("orphan sweep ws emit failed sap=%s: %s", application.id, exc)
                acted += 1
        return acted

    # --- .arm-inprogress sweep ----------------------------------------------

    async def sweep_arm_inprogress(self, media_root: Path) -> int:
        """Delete `*.arm-inprogress` orphans whose final-path's task isn't IN_PROGRESS.

        Runs once at Backend startup. A live in-progress task's `.arm-inprogress`
        is preserved (the transcoder is still writing it). Returns the count
        of deleted orphans.
        """
        if not media_root.exists():
            return 0
        deleted = 0
        async with self._db_factory() as db:
            for path in media_root.rglob("*.arm-inprogress"):
                final = path.with_suffix("")
                relative = final.relative_to(media_root).as_posix()
                live = (
                    await db.execute(
                        select(TranscodeTask)
                        .where(col(TranscodeTask.output_path) == relative)
                        .where(col(TranscodeTask.status) == TranscodeTaskStatus.IN_PROGRESS)
                    )
                ).scalar_one_or_none()
                if live is not None:
                    continue
                try:
                    path.unlink()
                    deleted += 1
                    logger.info("swept arm-inprogress orphan path=%s", path)
                except OSError as exc:
                    logger.warning("failed to delete arm-inprogress orphan path=%s err=%s", path, exc)
        return deleted
