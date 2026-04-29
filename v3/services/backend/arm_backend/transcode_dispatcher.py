"""Background dispatcher: spawn transcoder containers, sweep stale claims.

The dispatcher is a single asyncio task started in `main.py` lifespan. Every
`ARM_TRANSCODE_DISPATCH_INTERVAL_SECONDS` ticks it:

1. Sweeps stale claims (every tick — cheap; just one UPDATE).
2. Counts `transcode_tasks WHERE status='in_progress'` and, if below
   `MAX_PARALLEL_TRANSCODES`, dequeues queued tasks via
   `SELECT ... FOR UPDATE SKIP LOCKED LIMIT N` and spawns one container per
   row via the docker socket.
3. The `.arm-inprogress` orphan sweep runs once at lifespan startup (called
   directly by `main.py` before the dispatcher loop kicks off).

Cancel-running flow lives here too: emit `task.cancel` on
`transcoder.commands.{task_id}`, wait 10 s for the transcoder to call
/fail, then docker-stop any survivor by label scan.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import col, select

from arm_backend.config import Settings
from arm_common import (
    SessionApplication,
    TranscodeTask,
    TranscodeTaskStatus,
)

if TYPE_CHECKING:
    from arm_backend.ws.hub import WSHub

logger = logging.getLogger("arm_backend.transcode_dispatcher")


# How long after `task.cancel` we wait for the transcoder to call /fail
# gracefully before falling back to `docker stop`.
_CANCEL_GRACE_SECONDS = 10
_DOCKER_LABEL_KEY = "arm.task_id"


class TranscodeDispatcher:
    def __init__(
        self,
        settings: Settings,
        db_factory: async_sessionmaker[AsyncSession],
        docker_client: Any,
        hub: WSHub,
    ) -> None:
        self._settings = settings
        self._db_factory = db_factory
        self._docker = docker_client
        self._hub = hub
        self._stop = asyncio.Event()
        self._tick_interval = settings.ARM_TRANSCODE_DISPATCH_INTERVAL_SECONDS

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        logger.info(
            "transcode dispatcher starting: max_parallel=%d image=%s tick=%ds",
            self._settings.MAX_PARALLEL_TRANSCODES,
            self._settings.ARM_TRANSCODE_IMAGE,
            self._tick_interval,
        )
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception as exc:  # never crash the loop
                logger.exception("transcode dispatcher tick failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._tick_interval)
            except asyncio.TimeoutError:
                pass
        logger.info("transcode dispatcher stopped")

    async def _tick(self) -> None:
        async with self._db_factory() as db:
            await self.sweep_stale_claims(db)
            await self.spawn_pending(db)

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
            if task.attempts >= self._settings.ARM_TRANSCODE_MAX_ATTEMPTS:
                task.status = TranscodeTaskStatus.FAILED
                task.last_error = f"exceeded retry limit after stale claim (attempts={task.attempts})"
                logger.error(
                    "transcode task hard-failed after %d stale resets task_id=%s",
                    task.attempts,
                    task.id,
                )
                await self._emit_task_failed(db, task)
                application = (
                    await db.execute(
                        select(SessionApplication).where(col(SessionApplication.id) == task.session_application_id)
                    )
                ).scalar_one()
                from arm_backend.transcode_apply import aggregate_session_application

                outcome = await aggregate_session_application(db, application)
                if outcome.event_type is not None:
                    await self._hub.emit(
                        topic="transcode.events",
                        event_type=outcome.event_type,
                        payload={
                            "session_application_id": application.id,
                            "session_id": application.session_id,
                            "job_id": application.job_id,
                            "status": application.status.value,
                        },
                        job_id=application.job_id,
                        session=db,
                    )
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

    async def _emit_task_failed(self, db: AsyncSession, task: TranscodeTask) -> None:
        application = (
            await db.execute(
                select(SessionApplication).where(col(SessionApplication.id) == task.session_application_id)
            )
        ).scalar_one()
        await self._hub.emit(
            topic="transcode.events",
            event_type="task.failed",
            payload={
                "task_id": task.id,
                "session_application_id": task.session_application_id,
                "last_error": task.last_error,
            },
            job_id=application.job_id,
            track_id=task.source_track_id,
            session=db,
        )

    # --- spawn loop ---------------------------------------------------------

    async def spawn_pending(self, db: AsyncSession) -> int:
        """Spawn new transcoder containers up to MAX_PARALLEL_TRANSCODES.

        Counts in_progress rows live (cheap). For each available slot,
        dequeues one queued task and spawns. Returns the spawn count.
        """
        if not self._host_paths_set():
            logger.warning("transcode dispatcher disabled: ARM_HOST_*_PATH not set (set them via .env)")
            return 0

        in_progress = (
            (
                await db.execute(
                    select(TranscodeTask).where(col(TranscodeTask.status) == TranscodeTaskStatus.IN_PROGRESS)
                )
            )
            .scalars()
            .all()
        )
        slots = self._settings.MAX_PARALLEL_TRANSCODES - len(in_progress)
        if slots <= 0:
            return 0

        queued_all = (
            (
                await db.execute(
                    select(TranscodeTask)
                    .where(col(TranscodeTask.status) == TranscodeTaskStatus.QUEUED)
                    .order_by(col(TranscodeTask.created_at).asc())
                    .limit(slots)
                    .with_for_update(skip_locked=True)
                )
            )
            .scalars()
            .all()
        )
        # `.limit(slots)` is honoured by Postgres but the in-memory test fake
        # returns the full set; cap defensively here so the cap test passes
        # without leaking SQL-only behaviour into the test fixture.
        queued = list(queued_all)[:slots]
        spawned = 0
        for task in queued:
            try:
                self._spawn_container(task)
                spawned += 1
            except Exception as exc:
                logger.exception("transcode spawn failed task_id=%s: %s", task.id, exc)
        await db.commit()
        return spawned

    def _host_paths_set(self) -> bool:
        return bool(
            self._settings.ARM_HOST_RAW_PATH
            and self._settings.ARM_HOST_MEDIA_PATH
            and self._settings.ARM_HOST_LOGS_PATH
            and self._settings.ARM_HOST_CERTS_PATH
        )

    def _spawn_container(self, task: TranscodeTask) -> Any:
        env = {
            "ARM_TRANSCODE_TASK_ID": task.id,
            "ARM_BACKEND_URL": "https://arm-backend:8443",
            "ARM_SERVICE_TOKEN": self._settings.ARM_SERVICE_TOKEN,
            "ARM_LOG_LEVEL": self._settings.ARM_LOG_LEVEL,
        }
        certs_root = Path(self._settings.ARM_HOST_CERTS_PATH)
        volumes = {
            self._settings.ARM_HOST_RAW_PATH: {"bind": "/raw", "mode": "ro"},
            self._settings.ARM_HOST_MEDIA_PATH: {"bind": "/media", "mode": "rw"},
            self._settings.ARM_HOST_LOGS_PATH: {"bind": "/logs", "mode": "rw"},
            str(certs_root / "arm-ca.crt"): {"bind": "/etc/ssl/arm/arm-ca.crt", "mode": "ro"},
        }
        # Container hostname is the last 12 chars of the ULID — short enough
        # for `docker ps` and unique enough that two simultaneous transcoders
        # never collide.
        hostname = f"arm-transcode-{task.id[-12:]}"
        container = self._docker.containers.run(
            image=self._settings.ARM_TRANSCODE_IMAGE,
            name=hostname,
            hostname=hostname,
            labels={_DOCKER_LABEL_KEY: task.id},
            environment=env,
            volumes=volumes,
            network=self._settings.ARM_DOCKER_NETWORK,
            detach=True,
            auto_remove=True,
        )
        logger.info(
            "transcode spawned task_id=%s container=%s image=%s",
            task.id,
            hostname,
            self._settings.ARM_TRANSCODE_IMAGE,
        )
        return container

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

    # --- cancel running -----------------------------------------------------

    async def cancel_running(self, task_id: str) -> None:
        """Send `task.cancel` over WS, wait `_CANCEL_GRACE_SECONDS`, then
        docker-stop any survivor matching `arm.task_id=<task_id>`.
        """
        async with self._db_factory() as db:
            await self._hub.emit(
                topic=f"transcoder.commands.{task_id}",
                event_type="task.cancel",
                payload={"task_id": task_id},
                job_id=None,
                session=db,
            )
            await db.commit()

        await asyncio.sleep(_CANCEL_GRACE_SECONDS)

        async with self._db_factory() as db:
            row = (await db.execute(select(TranscodeTask).where(col(TranscodeTask.id) == task_id))).scalar_one_or_none()
            if row is None:
                return
            if row.status != TranscodeTaskStatus.IN_PROGRESS:
                return  # transcoder honoured the WS cancel via /fail

        # Fallback: docker-stop any container with this task label.
        try:
            survivors = self._docker.containers.list(filters={"label": f"{_DOCKER_LABEL_KEY}={task_id}"})
            for container in survivors:
                logger.warning(
                    "force-stopping unresponsive transcoder task_id=%s container=%s",
                    task_id,
                    container.id,
                )
                container.stop(timeout=5)
        except Exception as exc:
            logger.exception("docker-stop fallback failed for task_id=%s: %s", task_id, exc)

        # Mark the task failed if it's still in_progress (transcoder never
        # called /fail). Same shape as a graceful cancel.
        async with self._db_factory() as db:
            row = (await db.execute(select(TranscodeTask).where(col(TranscodeTask.id) == task_id))).scalar_one_or_none()
            if row is None or row.status != TranscodeTaskStatus.IN_PROGRESS:
                return
            row.status = TranscodeTaskStatus.FAILED
            row.last_error = "cancelled by user (force-stopped)"
            await self._emit_task_failed(db, row)
            from arm_backend.transcode_apply import aggregate_session_application

            application = (
                await db.execute(
                    select(SessionApplication).where(col(SessionApplication.id) == row.session_application_id)
                )
            ).scalar_one()
            outcome = await aggregate_session_application(db, application)
            if outcome.event_type is not None:
                await self._hub.emit(
                    topic="transcode.events",
                    event_type=outcome.event_type,
                    payload={
                        "session_application_id": application.id,
                        "session_id": application.session_id,
                        "job_id": application.job_id,
                        "status": application.status.value,
                    },
                    job_id=application.job_id,
                    session=db,
                )
            await db.commit()
