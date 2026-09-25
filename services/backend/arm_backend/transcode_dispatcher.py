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
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, NamedTuple

from paramiko.ssh_exception import SSHException  # type: ignore[import-untyped]
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import col, select

from arm_backend.config import Settings, settings
from arm_backend.docker_probe import TtlProbe, probe_docker
from arm_common import (
    Config,
    Gpu,
    GpuStatus,
    GpuVendor,
    HwPreference,
    Session,
    SessionApplication,
    SessionApplicationStatus,
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

# Per-tick cap on how many ENCODE rows spawn_pending examines (spawn
# attempts, GPU claim checks, etc). Passthrough tasks are exempt from this
# cap entirely and the queued scan itself is unbounded, so a run of 50+
# held/queued encode rows at the head of the FIFO queue can never crowd a
# passthrough task further back out of the scan window.
_QUEUE_SCAN_LIMIT = 50

# A dead docker-over-SSH transport (idle paramiko connection reset by the
# remote end) surfaces as one of these, either raw or wrapped inside
# docker-py's APIError cause chain. EOFError is included because paramiko
# commonly surfaces a dead transport that way (the read side hits EOF when
# the remote end has silently closed the connection).
_TRANSPORT_DEAD_ERRORS = (SSHException, ConnectionResetError, BrokenPipeError, EOFError)


def _is_transport_death(exc: BaseException) -> bool:
    """A dead docker-over-SSH transport surfaces either as a raw paramiko
    SSHException or wrapped inside docker's APIError cause chain (docker-py
    wraps the underlying requests/urllib3 error, whose root cause is
    paramiko's SSHException). Walk __cause__/__context__ to find it.
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, _TRANSPORT_DEAD_ERRORS):
            return True
        cur = cur.__cause__ or cur.__context__
    return False


class GpuAssignment(NamedTuple):
    """Outcome of `_claim_gpu_for_task`. `gpu` is None for the CPU spawn path;
    `action="queue"` means leave the task queued so a later tick can retry
    when a matching GPU frees up (NULL hw_preference + all matching GPUs busy).
    """

    gpu: Gpu | None
    codec: str | None
    action: Literal["spawn", "queue"]


async def max_parallel_transcodes(db: AsyncSession, *, default: int | None = None) -> int:
    """The dispatcher parallelism cap from operator config (Settings >
    Transcoding). Falls back to `default` (the caller's env-derived value)
    only while the config row predates the column (the seeder backfills it
    on the next boot)."""
    from arm_backend.seeders import CONFIG_SINGLETON_ID  # noqa: PLC0415 — avoid module cycle

    cfg = (await db.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    if cfg is None or cfg.max_parallel_transcodes is None:
        return default if default is not None else settings.MAX_PARALLEL_TRANSCODES
    return cfg.max_parallel_transcodes


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
        docker_client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._settings = settings
        self._db_factory = db_factory
        self._docker = docker_client
        self._docker_factory = docker_client_factory
        self._hub = hub
        self._stop = asyncio.Event()
        self._tick_interval = settings.ARM_TRANSCODE_DISPATCH_INTERVAL_SECONDS
        # Surfaced by /api/system/diagnostics so a crash-looping or
        # un-pullable transcoder is visible in the UI, not only in the log.
        self.last_spawn_error: str | None = None
        self._probe = TtlProbe(lambda: probe_docker(self._docker, self._settings.ARM_TRANSCODE_IMAGE))

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        logger.info(
            "transcode dispatcher starting: max_parallel=db-config (env seed %d) image=%s tick=%ds",
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
            await self.sweep_orphaned_applications(db)
            await db.commit()
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
        from arm_backend.transcode_apply import aggregate_session_application

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
                    await self._hub.emit(
                        topic="transcode.events",
                        event_type=event_type,
                        payload={
                            "session_application_id": application.id,
                            "session_id": application.session_id,
                            "job_id": application.job_id,
                            "status": application.status.value,
                        },
                        job_id=application.job_id,
                        session=db,
                    )
                except Exception as exc:  # WS is best-effort; status already set
                    logger.warning("orphan sweep ws emit failed sap=%s: %s", application.id, exc)
                acted += 1
        return acted

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
        """Execute queued passthrough tasks in-process and spawn transcoder
        containers for encode tasks up to `config.max_parallel_transcodes`.

        Passthrough (no preset, or TranscodeTool.NONE) never spawns a
        container and is not counted against encode slots; it always runs
        when queued, FIFO. Encode tasks are additionally gated by
        `config.transcode_enabled` (held in QUEUED when off) and by having a
        docker client + host paths at all (a ripper-only deployment has
        neither); held tasks stay queued for a later tick, never dropped.

        The queued scan is unbounded (no LIMIT) so a run of held encode
        tasks at the head of the FIFO queue can never crowd passthrough
        tasks further back out of this tick entirely; `_QUEUE_SCAN_LIMIT`
        instead caps how many ENCODE tasks are examined per tick (a
        passthrough task never counts against that cap either). Each
        passthrough task commits its own claim + terminal state internally
        (see `execute_passthrough_task`), so the `FOR UPDATE SKIP LOCKED`
        row locks from the initial select are released well before any
        (possibly slow, cross-mount) file move runs.
        """
        from arm_backend.passthrough_executor import execute_passthrough_task
        from arm_backend.transcode_apply import is_passthrough_preset, transcode_enabled_now

        enabled = await transcode_enabled_now(db)

        in_progress = (
            (
                await db.execute(
                    select(TranscodeTask).where(col(TranscodeTask.status) == TranscodeTaskStatus.IN_PROGRESS)
                )
            )
            .scalars()
            .all()
        )
        encode_slots = await max_parallel_transcodes(db, default=self._settings.MAX_PARALLEL_TRANSCODES) - len(
            in_progress
        )

        queued = (
            (
                await db.execute(
                    select(TranscodeTask)
                    .where(col(TranscodeTask.status) == TranscodeTaskStatus.QUEUED)
                    .order_by(col(TranscodeTask.created_at).asc())
                    .with_for_update(skip_locked=True)
                )
            )
            .scalars()
            .all()
        )
        spawned = 0
        held_encode = 0
        encode_examined = 0
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
                if is_passthrough_preset(preset):
                    # Never counted against encode_slots/encode_examined and
                    # never held by the disabled/docker-less gates below: a
                    # file move needs neither a container nor an encode slot.
                    # Isolated per-task try/except: a raise here (hub.emit,
                    # aggregate, or an unexpected DB error) must never abort
                    # the tick and roll back other tasks' already-committed
                    # work or in-flight GPU claims (see execute_passthrough_task
                    # for the commit-per-task structure that makes this safe).
                    try:
                        await execute_passthrough_task(db, task, self._hub, self._settings)
                    except Exception as exc:
                        logger.exception("passthrough execution failed task_id=%s: %s", task.id, exc)
                    continue
                if encode_examined >= _QUEUE_SCAN_LIMIT:
                    # Encode-only cap; passthrough tasks further back in the
                    # queue are still scanned and still run.
                    continue
                encode_examined += 1
                if not enabled:
                    held_encode += 1
                    continue
                if self._docker is None or not self.host_paths_set():
                    held_encode += 1
                    continue
                if encode_slots - spawned <= 0:
                    # No free slot this tick; later passthrough tasks in the
                    # queue must still run, so `continue` (not `break`).
                    continue
                assignment = await self._claim_gpu_for_task(db, task, preset)
                if assignment.action == "queue":
                    logger.info(
                        "transcode task waiting for GPU codec=%s task_id=%s",
                        assignment.codec,
                        task.id,
                    )
                    continue
                try:
                    # `_spawn_container` is a blocking call: a plain docker
                    # socket round-trip normally, but on the SSH-transport-
                    # rebuild path (see `_is_transport_death`) it also does a
                    # blocking TCP+SSH handshake that can take tens of
                    # seconds against a black-holed remote host. Run it off
                    # the event loop so a stuck spawn doesn't freeze
                    # HTTP/WS/ripper callbacks for the whole tick.
                    # `_spawn_container` touches only `self._docker`,
                    # `self._docker_factory`, `self._settings`, and its own
                    # locals/args (never the AsyncSession), so moving it to a
                    # thread doesn't put any DB access off the loop.
                    await asyncio.to_thread(self._spawn_container, task, assignment=assignment)
                    spawned += 1
                    self.last_spawn_error = None
                except Exception as exc:
                    self.last_spawn_error = f"{type(exc).__name__}: {exc}"[:300]
                    logger.exception("transcode spawn failed task_id=%s: %s", task.id, exc)
                    # Release the GPU claim so the task can retry on a later tick.
                    if assignment.gpu is not None:
                        assignment.gpu.status = GpuStatus.AVAILABLE
                        assignment.gpu.claimed_by_task_id = None
        if held_encode:
            logger.debug(
                "%d encode task(s) held (enabled=%s docker=%s)", held_encode, enabled, self._docker is not None
            )
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
        # Disabled rows (Settings > GPUs switch) never participate.
        all_gpus = (await db.execute(select(Gpu))).scalars().all()
        matching = [g for g in all_gpus if g.enabled and codec in (g.encoder_kinds or [])]
        if not matching:
            # No enabled silicon on this host advertises the requested codec — CPU.
            return GpuAssignment(gpu=None, codec=codec, action="spawn")

        available = [g for g in matching if g.status == GpuStatus.AVAILABLE]
        if available:
            # Deterministic pick instead of row order (G-30, first half):
            # vendors in HandBrake-support-quality order, then device path,
            # so a mixed-vendor host always prefers the same silicon and a
            # redeploy can't silently flip which GPU a preset lands on.
            # (Per-preset vendor pinning is the registered second half.)
            vendor_rank = {GpuVendor.NVENC: 0, GpuVendor.QSV: 1, GpuVendor.VAAPI: 2}
            available.sort(key=lambda g: (vendor_rank.get(g.vendor, 99), g.device_path))
            gpu = available[0]
            gpu.status = GpuStatus.BUSY
            gpu.claimed_by_task_id = task.id
            return GpuAssignment(gpu=gpu, codec=codec, action="spawn")

        # All matching GPUs are busy.
        if preset.hw_preference == HwPreference.ANY:
            return GpuAssignment(gpu=None, codec=codec, action="spawn")
        # NULL semantics: hold the task in queued so a later tick retries.
        return GpuAssignment(gpu=None, codec=codec, action="queue")

    def host_paths_set(self) -> bool:
        return bool(
            self._settings.ARM_HOST_RAW_PATH
            and self._settings.ARM_HOST_MEDIA_PATH
            and self._settings.ARM_HOST_LOGS_PATH
            and self._settings.ARM_HOST_CERTS_PATH
        )

    def probe(self) -> tuple[bool, str | None]:
        """Can this dispatcher actually run a transcode right now? Pings the
        docker host and checks the image exists there. Never raises; cached
        for docker_probe.PROBE_TTL_SECONDS (see there for why). A ripper-only
        deployment (no docker client at all) can't run encode tasks; that's
        not a probe failure to retry, just a fixed fact, so short-circuit
        before touching `self._probe`."""
        if self._docker is None:
            return (False, "no docker client (ripper-only deployment or docker unavailable)")
        return self._probe()

    def _spawn_container(self, task: TranscodeTask, *, assignment: GpuAssignment | None = None) -> Any:
        remote = bool(self._settings.ARM_TRANSCODE_DOCKER_HOST)
        if remote and not self._settings.ARM_TRANSCODE_BACKEND_URL:
            logger.warning(
                "ARM_TRANSCODE_DOCKER_HOST set but ARM_TRANSCODE_BACKEND_URL empty — "
                "remote transcoder will use the unroutable in-network https://arm-backend:8443; "
                "set ARM_TRANSCODE_BACKEND_URL to a host-routable backend URL"
            )
        backend_url = (
            self._settings.ARM_TRANSCODE_BACKEND_URL
            if remote and self._settings.ARM_TRANSCODE_BACKEND_URL
            else "https://arm-backend:8443"
        )
        env = {
            "ARM_TRANSCODE_TASK_ID": task.id,
            "ARM_BACKEND_URL": backend_url,
            "ARM_SERVICE_TOKEN": self._settings.ARM_SERVICE_TOKEN,
            "ARM_LOG_LEVEL": self._settings.ARM_LOG_LEVEL,
            # Phase 12 — per-task log filename so parallel transcoders don't
            # clobber a shared `/logs/arm-transcode.log` rotation.
            "ARM_SERVICE_NAME": f"arm-transcode-{task.id[-12:]}",
        }
        # Override the drop uid/gid so the transcoder writes /media as the
        # owner of the (possibly remote) media export, instead of the
        # entrypoint's default uid. Empty settings leave the default in place.
        if self._settings.ARM_TRANSCODE_PUID:
            env["PUID"] = self._settings.ARM_TRANSCODE_PUID
        if self._settings.ARM_TRANSCODE_PGID:
            env["PGID"] = self._settings.ARM_TRANSCODE_PGID
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
            # VAAPI/QSV: the entrypoint self-derives the render gid from the
            # mounted node; an explicit ARM_RENDER_GID is a forced OVERRIDE
            # (passed through as RENDER_GID, which wins in the entrypoint).
            if assignment.gpu.vendor in (GpuVendor.VAAPI, GpuVendor.QSV) and self._settings.ARM_RENDER_GID:
                env["RENDER_GID"] = self._settings.ARM_RENDER_GID
            self._inject_gpu_run_kwargs(extra_run_kwargs, assignment.gpu)
        # Container hostname is the last 12 chars of the ULID — short enough
        # for `docker ps` and unique enough that two simultaneous transcoders
        # never collide.
        hostname = f"arm-transcode-{task.id[-12:]}"
        run_kwargs: dict[str, Any] = dict(
            image=self._settings.ARM_TRANSCODE_IMAGE,
            name=hostname,
            hostname=hostname,
            labels={_DOCKER_LABEL_KEY: task.id},
            environment=env,
            volumes=volumes,
            network=(None if remote else self._settings.ARM_DOCKER_NETWORK),
            detach=True,
            auto_remove=True,
            **extra_run_kwargs,
        )
        try:
            container = self._docker.containers.run(**run_kwargs)
        except Exception as exc:
            if self._docker_factory is not None and _is_transport_death(exc):
                logger.warning(
                    "docker ssh transport dead; rebuilding client and retrying spawn task_id=%s: %s",
                    task.id,
                    exc,
                )
                old_docker = self._docker
                try:
                    rebuilt = self._docker_factory()
                except Exception as factory_exc:  # noqa: BLE001 - factory failure must not wedge the dispatcher
                    logger.warning(
                        "docker client rebuild failed; keeping old client task_id=%s: %s",
                        task.id,
                        factory_exc,
                    )
                    raise
                if rebuilt is None:
                    # _build_docker_client (main.py) returns None on any
                    # failure (dev without the socket, unreachable/
                    # misconfigured remote host). Assigning self._docker =
                    # None here would make every LATER spawn raise
                    # AttributeError instead of the transport-death path
                    # that can actually recover — permanently wedging the
                    # dispatcher. Keep the old (dead) client instead: this
                    # tick's spawn still fails via the original exception
                    # below, and the next tick's spawn attempt will detect
                    # transport death again and retry the rebuild.
                    logger.warning(
                        "docker client rebuild returned None; keeping old client task_id=%s",
                        task.id,
                    )
                    raise
                self._docker = rebuilt
                try:
                    old_docker.close()
                except Exception:  # noqa: BLE001 - best-effort cleanup of the dead client
                    pass
                # A second failure here propagates into the existing
                # error handling in spawn_pending — no infinite retry.
                container = self._docker.containers.run(**run_kwargs)
            else:
                raise
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
        # cancel inside the grace window. No docker client (ripper-only
        # deployment) means there's no container to stop; the row delete
        # below still runs.
        if still_running and self._docker is not None:
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
