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
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import col, select

from arm_backend.config import Settings
from arm_common import (
    Gpu,
    GpuStatus,
    GpuVendor,
    HwPreference,
    Session,
    SessionApplication,
    TranscodePreset,
    TranscodeTask,
    TranscodeTaskStatus,
    with_log_context,
)

if TYPE_CHECKING:
    from arm_backend.ws.hub import WSHub

logger = logging.getLogger("arm_backend.transcode_dispatcher")


# How long after `task.cancel` we wait for the transcoder to call /fail
# gracefully before falling back to `docker stop`.
_CANCEL_GRACE_SECONDS = 10
_DOCKER_LABEL_KEY = "arm.task_id"


class GpuAssignment(NamedTuple):
    """Outcome of `_claim_gpu_for_task`. `gpu` is None for the CPU spawn path;
    `action="queue"` means leave the task queued so a later tick can retry
    when a matching GPU frees up (NULL hw_preference + all matching GPUs busy).
    """

    gpu: Gpu | None
    codec: str | None
    action: Literal["spawn", "queue"]


async def release_gpu_for_task(db: AsyncSession, task_id: str) -> None:
    """Flip every GPU row claimed by this task back to AVAILABLE.

    Called from the transcoder router on complete/fail and from the
    stale-claim sweep. Idempotent — a no-op if no GPU was claimed.
    Caller is responsible for committing.
    """
    gpus = (await db.execute(select(Gpu).where(col(Gpu.claimed_by_task_id) == task_id))).scalars().all()
    for gpu in gpus:
        gpu.status = GpuStatus.AVAILABLE
        gpu.claimed_by_task_id = None


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
                    await self._emit_task_failed(db, task)
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
                    application = stale_application
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
            # Load the owning application once so the spawn log lines carry
            # job_id for the per-job log view (Phase 12).
            application = (
                await db.execute(
                    select(SessionApplication).where(col(SessionApplication.id) == task.session_application_id)
                )
            ).scalar_one_or_none()
            job_id = application.job_id if application is not None else None
            with with_log_context(job_id=job_id, session_application_id=task.session_application_id):
                preset = await self._resolve_preset_for_task(db, task)
                assignment = await self._claim_gpu_for_task(db, task, preset)
                if assignment.action == "queue":
                    logger.info(
                        "transcode task waiting for GPU codec=%s task_id=%s",
                        assignment.codec,
                        task.id,
                    )
                    continue
                try:
                    self._spawn_container(task, assignment=assignment)
                    spawned += 1
                except Exception as exc:
                    logger.exception("transcode spawn failed task_id=%s: %s", task.id, exc)
                    # Release the GPU claim so the task can retry on a later tick.
                    if assignment.gpu is not None:
                        assignment.gpu.status = GpuStatus.AVAILABLE
                        assignment.gpu.claimed_by_task_id = None
        await db.commit()
        return spawned

    async def _resolve_preset_for_task(self, db: AsyncSession, task: TranscodeTask) -> TranscodePreset | None:
        application = (
            await db.execute(
                select(SessionApplication).where(col(SessionApplication.id) == task.session_application_id)
            )
        ).scalar_one_or_none()
        if application is None:
            return None
        sess = (await db.execute(select(Session).where(col(Session.id) == application.session_id))).scalar_one_or_none()
        if sess is None or sess.transcode_preset_id is None:
            return None
        return (
            await db.execute(select(TranscodePreset).where(col(TranscodePreset.id) == sess.transcode_preset_id))
        ).scalar_one_or_none()

    async def _claim_gpu_for_task(
        self, db: AsyncSession, task: TranscodeTask, preset: TranscodePreset | None
    ) -> GpuAssignment:
        """Implements the `hw_preference` × GPU-availability matrix.

        Branches:
        - `cpu_only`, or no preset, or preset has no codec → CPU spawn.
        - matching GPU AVAILABLE → claim it, GPU spawn.
        - all matching GPUs BUSY + `any` → CPU spawn.
        - all matching GPUs BUSY + NULL → queue (retry next tick).
        - no GPU advertises this codec at all → CPU spawn (NULL fallback).
        """
        if preset is None or preset.codec is None:
            return GpuAssignment(gpu=None, codec=None, action="spawn")
        if preset.hw_preference == HwPreference.CPU_ONLY:
            return GpuAssignment(gpu=None, codec=preset.codec.value, action="spawn")

        codec = preset.codec.value
        # Filter in Python — `text[]` ANY predicates are awkward to express in
        # SQLAlchemy ORM and the in-memory test fake doesn't grok them. The
        # gpus table is small (1-4 rows on real hosts) so the cost is trivial.
        all_gpus = (await db.execute(select(Gpu))).scalars().all()
        matching = [g for g in all_gpus if codec in (g.encoder_kinds or [])]
        if not matching:
            # No silicon on this host advertises the requested codec — CPU.
            return GpuAssignment(gpu=None, codec=codec, action="spawn")

        available = [g for g in matching if g.status == GpuStatus.AVAILABLE]
        if available:
            gpu = available[0]
            gpu.status = GpuStatus.BUSY
            gpu.claimed_by_task_id = task.id
            return GpuAssignment(gpu=gpu, codec=codec, action="spawn")

        # All matching GPUs are busy.
        if preset.hw_preference == HwPreference.ANY:
            return GpuAssignment(gpu=None, codec=codec, action="spawn")
        # NULL semantics: hold the task in queued so a later tick retries.
        return GpuAssignment(gpu=None, codec=codec, action="queue")

    def _host_paths_set(self) -> bool:
        return bool(
            self._settings.ARM_HOST_RAW_PATH
            and self._settings.ARM_HOST_MEDIA_PATH
            and self._settings.ARM_HOST_LOGS_PATH
            and self._settings.ARM_HOST_CERTS_PATH
        )

    def _spawn_container(self, task: TranscodeTask, *, assignment: GpuAssignment | None = None) -> Any:
        env = {
            "ARM_TRANSCODE_TASK_ID": task.id,
            "ARM_BACKEND_URL": "https://arm-backend:8443",
            "ARM_SERVICE_TOKEN": self._settings.ARM_SERVICE_TOKEN,
            "ARM_LOG_LEVEL": self._settings.ARM_LOG_LEVEL,
            # Phase 12 — per-task log filename so parallel transcoders don't
            # clobber a shared `/logs/arm-transcode.log` rotation.
            "ARM_SERVICE_NAME": f"arm-transcode-{task.id[-12:]}",
        }
        certs_root = Path(self._settings.ARM_HOST_CERTS_PATH)
        volumes = {
            self._settings.ARM_HOST_RAW_PATH: {"bind": "/raw", "mode": "ro"},
            self._settings.ARM_HOST_MEDIA_PATH: {"bind": "/media", "mode": "rw"},
            self._settings.ARM_HOST_LOGS_PATH: {"bind": "/logs", "mode": "rw"},
            str(certs_root / "arm-ca.crt"): {"bind": "/etc/ssl/arm/arm-ca.crt", "mode": "ro"},
        }
        extra_run_kwargs: dict[str, Any] = {}
        if assignment is not None and assignment.gpu is not None:
            env["ARM_GPU_VENDOR"] = assignment.gpu.vendor.value
            env["ARM_GPU_DEVICE"] = assignment.gpu.device_path
            if assignment.codec is not None:
                env["ARM_GPU_CODEC"] = assignment.codec
            # VAAPI/QSV need the render-node group inside the container; the
            # entrypoint adds `arm` to RENDER_GID before gosu (a docker
            # --group-add wouldn't survive the gosu group reset). NVENC's device
            # access comes via the nvidia runtime, so it doesn't need this.
            if assignment.gpu.vendor in (GpuVendor.VAAPI, GpuVendor.QSV) and self._settings.ARM_RENDER_GID:
                env["RENDER_GID"] = self._settings.ARM_RENDER_GID
            self._inject_gpu_run_kwargs(extra_run_kwargs, assignment.gpu)
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
            **extra_run_kwargs,
        )
        logger.info(
            "transcode spawned task_id=%s container=%s image=%s gpu=%s",
            task.id,
            hostname,
            self._settings.ARM_TRANSCODE_IMAGE,
            assignment.gpu.device_path if assignment and assignment.gpu else "cpu",
        )
        return container

    def _inject_gpu_run_kwargs(self, kwargs: dict[str, Any], gpu: Gpu) -> None:
        """Vendor-specific docker-py kwargs.

        VAAPI/QSV: pass the `/dev/dri/renderD*` node via `devices=`.
        NVENC: ask for the NVIDIA runtime + a single GPU via `device_requests`.
        """
        if gpu.vendor in (GpuVendor.VAAPI, GpuVendor.QSV):
            # Grant cgroup access to the render node. File-level access (the node
            # is root:render 0660) is handled by the container entrypoint adding
            # `arm` to RENDER_GID — see _spawn_container; a docker group_add here
            # wouldn't survive the entrypoint's gosu group reset.
            kwargs["devices"] = [f"{gpu.device_path}:{gpu.device_path}:rwm"]
            return
        if gpu.vendor == GpuVendor.NVENC:
            # device_path is "nvidia://N"; pass the index as a string ID so
            # `--gpus device=N` semantics select that single GPU.
            #
            # `count` and `device_ids` are mutually exclusive on the docker
            # daemon side ("cannot set both Count and DeviceIDs on device
            # request"). Pin to a specific GPU when we have an index;
            # otherwise fall back to "count: 1 (any free GPU)".
            idx = gpu.device_path.removeprefix("nvidia://")
            base_kwargs: dict[str, Any] = {
                "driver": "nvidia",
                "capabilities": [["gpu", "video"]],
            }
            if idx:
                base_kwargs["device_ids"] = [idx]
            else:
                base_kwargs["count"] = 1
            try:
                import docker  # type: ignore[import-untyped]

                kwargs["runtime"] = "nvidia"
                kwargs["device_requests"] = [docker.types.DeviceRequest(**base_kwargs)]
            # docker-py is a hard dependency (pyproject) — this fallback is dead.
            except ImportError:  # pragma: no cover
                # Legacy guard from when docker-py was test-optional. Kept
                # so the kwarg shape stays correct if that ever regresses.
                kwargs["runtime"] = "nvidia"
                fallback = {
                    "Driver": base_kwargs["driver"],
                    "Capabilities": base_kwargs["capabilities"],
                }
                if "device_ids" in base_kwargs:
                    fallback["DeviceIDs"] = base_kwargs["device_ids"]
                else:
                    fallback["Count"] = base_kwargs["count"]
                kwargs["device_requests"] = [fallback]

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
        docker-stop any survivor and delete the row.

        Cancel = delete: the row vanishes from the DB and `task.deleted`
        fires over WS. If the transcoder honoured the cancel cleanly by
        calling `/fail` during the grace window the row was already
        marked FAILED — we delete it anyway, since the user's intent was
        to remove it entirely.
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

        # Fetch once to decide whether docker-stop is still needed and to
        # capture the metadata we need for the task.deleted emit.
        async with self._db_factory() as db:
            row = (await db.execute(select(TranscodeTask).where(col(TranscodeTask.id) == task_id))).scalar_one_or_none()
            if row is None:
                return  # already gone (race with another delete or rollback)
            still_running = row.status == TranscodeTaskStatus.IN_PROGRESS
            application_id = row.session_application_id
            track_id = row.source_track_id

        # Force-stop the container if the transcoder didn't honour the WS
        # cancel inside the grace window.
        if still_running:
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

        # Delete the row + emit task.deleted. Re-select fresh in case the
        # transcoder /fail call mutated the row between our fetch and now.
        async with self._db_factory() as db:
            row = (await db.execute(select(TranscodeTask).where(col(TranscodeTask.id) == task_id))).scalar_one_or_none()
            # Race guard: row deleted between the post-grace fetch and here.
            if row is None:  # pragma: no cover
                return
            application = (
                await db.execute(select(SessionApplication).where(col(SessionApplication.id) == application_id))
            ).scalar_one_or_none()
            job_id = application.job_id if application is not None else None
            await db.delete(row)
            await self._hub.emit(
                topic="transcode.events",
                event_type="task.deleted",
                payload={"task_id": task_id, "session_application_id": application_id},
                job_id=job_id,
                track_id=track_id,
                session=db,
            )
            await db.commit()
