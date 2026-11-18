import asyncio
import contextlib
import logging
import subprocess
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI
from sqlmodel import col, select

from arm_backend.auth import declare_guest_reads
from arm_backend.config import effective_transcode_capable, settings
from arm_backend.crash_recovery import sweep_in_flight_jobs
from arm_backend.db import SessionLocal
from arm_backend.gpu_inventory import refresh_gpu_inventory
from arm_backend.gpu_probe_runner import GpuProbeRunner
from arm_backend.handbrake_schema_runner import HandbrakeSchemaRunner
from arm_backend.handbrake_schema_store import SchemaStore
from arm_backend.identity.stage_runner import EpisodeStageRunner
from arm_backend import image_cache
from arm_backend.disk_refresh import DiskRefresher
from arm_backend.docker_factory import build_docker_client
from arm_backend.drive_scanner import DriveScanner
from arm_backend.log_tailer import LogTailer
from arm_backend.metadata import MetadataDispatcher
from arm_backend.notification_dispatcher import MessageDispatcher
from arm_backend.notifications.apprise_listener import AppriseListener
from arm_backend.notifications.apprise_notifier import RealAppriseNotifier
from arm_backend.notifications.bash_listener import BashListener
from arm_backend.notifications.inbox_listener import InboxListener
from arm_backend.virtual_drive_lifecycle import run_virtual_drive_watchdog
from arm_backend.ripper_manager import RipperManager
from arm_backend.ripper_reconcile import reconcile_enrolled_rippers
from arm_backend.routers import (
    gpus as gpus_router,
    encoders as encoders_router,
    handbrake_schema as handbrake_schema_router,
    auth,
    config as config_router,
    diagnostics,
    drives,
    files as files_router,
    health,
    identity as identity_router,
    images as images_router,
    iso as iso_router,
    jobs,
    logs as logs_router,
    metadata as metadata_router,
    naming as naming_router,
    notifications as notifications_router,
    rip_presets,
    ripper,
    session_routes,
    sessions,
    settings as settings_router,
    setup as setup_router,
    system as system_router,
    themes as themes_router,
    transcode_presets,
    transcoder,
    transcodes,
    users as users_router,
)
from arm_backend.constants import CONFIG_SINGLETON_ID
from arm_backend.seeders import run_seeders
from arm_backend.thediscdb_schedule import thediscdb_refresh_loop
from arm_backend.transcode_dispatcher import TranscodeDispatcher, set_active_dispatcher
from arm_backend.utils import ensure_roots, default_roots
from arm_backend.ws import WSHub
from arm_backend.ws.router import router as ws_router
from arm_common import Config, configure_service_logging

configure_service_logging("arm-backend", level=settings.ARM_LOG_LEVEL)
logger = logging.getLogger("arm_backend")


def _run_migrations() -> None:
    backend_dir = Path(__file__).resolve().parent.parent
    logger.info("running alembic upgrade head")
    subprocess.run(
        ["alembic", "upgrade", "head"],
        cwd=str(backend_dir),
        check=True,
    )
    logger.info("migrations applied")


async def _run_seeders() -> None:
    logger.info("running first-boot seeders")
    async with SessionLocal() as session:
        await run_seeders(session)
    logger.info("seeders complete")


async def _startup_sweep(sweep: Callable[[], Awaitable[int]], done: str, failed: str) -> None:
    """Run one boot sweep and log how many rows it touched; a failure is
    logged and never stops startup."""
    try:
        count = await sweep()
        if count:
            logger.info(done, count)
    except Exception as exc:
        logger.exception(failed, exc)


async def _sweep_orphaned_applications(dispatcher: TranscodeDispatcher) -> int:
    """Reconcile session applications a crash left orphaned, on a session of
    their own; returns how many."""
    async with SessionLocal() as db:
        orphaned = await dispatcher.sweeps.sweep_orphaned_applications(db)
        await db.commit()
    return orphaned


async def _load_signing_key() -> bytes:
    """Read the session signing key the first-boot seeders stored on the
    config row."""
    async with SessionLocal() as session:
        cfg = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one()
        # Defensive only: _run_seeders always populates this.
        if cfg.session_signing_key is None:  # pragma: no cover
            raise RuntimeError("session_signing_key missing — seeders should have populated it")
        return cfg.session_signing_key


class _BackendServices:
    """The backend's long-running services: `start` brings them up in boot
    order and `stop` runs their shutdown steps in order."""

    _thediscdb_refresh_task: asyncio.Task[None]
    _dispatcher_task: asyncio.Task[None]
    _iso_watchdog_task: asyncio.Task[None] | None
    _notification_task: asyncio.Task[None]
    _log_tailer_task: asyncio.Task[None]
    _drive_scanner_task: asyncio.Task[None]
    _disk_refresher_task: asyncio.Task[None]
    _transcode_dispatcher: TranscodeDispatcher
    _notification_dispatcher: MessageDispatcher
    _log_tailer: LogTailer
    _drive_scanner: DriveScanner
    _disk_refresher: DiskRefresher
    _shutdown_steps: list[tuple[str, Callable[[], Awaitable[None]]]]

    def __init__(self, app: FastAPI) -> None:
        self._app = app

    async def start(self) -> None:
        _run_migrations()
        await _run_seeders()
        # Rebuild the image-proxy disk-cache index from disk (LRU/TTL). Sync, fast,
        # no DB — safe to run before the session/dispatchers come up.
        image_cache.startup_scan()
        self._app.state.signing_key = await _load_signing_key()
        # Silently create any missing data root (never chown, never raise —
        # the entrypoint's writability guard owns the fatal cases). Diagnostics
        # re-ensures on every read.
        ensure_roots(default_roots())
        self._attach_request_services()

        self._start_thediscdb()

        # GPU inventory — seed the gpus table from ARM_GPUS only when empty
        # (DB-authoritative thereafter). Runs before the dispatcher starts.
        await refresh_gpu_inventory(self._app.state.ws_hub)

        # Reset every RIPPING job's tracks to queued and stamp
        # resumed_from_crash. Idempotent across boots; no-op when nothing crashed.
        await _startup_sweep(
            lambda: sweep_in_flight_jobs(SessionLocal),
            "backend startup: resumed %d crashed rip(s)",
            "startup crash-recovery sweep failed: %s",
        )

        # Episode stage startup sweep (Review Focus 5): schedule the background
        # episode stage once for every TV-candidate job that never got an
        # episode-source entry (e.g. the backend restarted between identify and
        # the runner picking it up).
        await _startup_sweep(
            self._app.state.episode_stage.sweep_startup,
            "backend startup: scheduled episode stage for %d job(s)",
            "startup episode-stage sweep failed: %s",
        )

        await self._load_handbrake_schema_store()
        self._transcode_dispatcher = self._build_transcode_dispatcher()
        # One-shot sweeps run in every mode (they are DB/file-side, not
        # docker-side): a ripper-only deployment still needs orphaned
        # .arm-inprogress markers and crash-orphaned session_applications cleaned
        # up on boot.
        await _startup_sweep(
            lambda: self._transcode_dispatcher.sweeps.sweep_arm_inprogress(Path(settings.MEDIA_ROOT)),
            "backend startup: swept %d .arm-inprogress orphans",
            "startup .arm-inprogress sweep failed: %s",
        )
        await _startup_sweep(
            lambda: _sweep_orphaned_applications(self._transcode_dispatcher),
            "backend startup: reconciled %d orphaned session_application(s)",
            "startup orphaned-application sweep failed: %s",
        )
        self._start_transcode_dispatcher()
        gpu_probe_runner = self._start_gpu_probe_runner()
        handbrake_schema_runner = self._start_handbrake_schema_runner()

        await self._start_ripper_manager()

        self._start_notifications()

        self._start_log_tailer()

        self._start_drive_scanner()

        self._start_disk_refresher()

        self._shutdown_steps = [
            ("thediscdb refresh", self._stop_thediscdb_refresh),
            ("disk refresher", self._stop_disk_refresher),
            ("log tailer", self._stop_log_tailer),
            ("drive scanner", self._stop_drive_scanner),
            ("iso watchdog", self._stop_iso_watchdog),
            ("notification dispatcher", self._stop_notifications),
            # Cancels the boot pass and any re-probe, waiting briefly so each
            # cancelled probe removes its container.
            ("gpu probe runner", gpu_probe_runner.shutdown),
            ("handbrake schema runner", handbrake_schema_runner.shutdown),
            ("transcode dispatcher", self._stop_transcode_dispatcher),
            ("episode stage runner", self._app.state.episode_stage.shutdown),
            ("metadata dispatcher", self._app.state.dispatcher.aclose),
        ]

    def _attach_request_services(self) -> None:
        """Put the clients the request path shares on app.state."""
        http = httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=10.0))
        self._app.state.http = http
        self._app.state.started_at = datetime.now(UTC)
        self._app.state.dispatcher = MetadataDispatcher(http)
        self._app.state.ws_hub = WSHub()
        # Background episode stage runs off the
        # request path, triggered by identify/resolve/PATCH (routers) and the
        # startup sweep below. One SourceHttp per source id lives on the runner
        # for its whole lifetime (rate limit / cache / backoff state, and TVDB's
        # login token on the provider built from it).
        self._app.state.episode_stage = EpisodeStageRunner(SessionLocal, http, self._app.state.ws_hub)

    def _start_thediscdb(self) -> None:
        """Open the TheDiscDB snapshot and start its daily refresh loop."""
        from arm_backend.identity.sources.thediscdb_snapshot import SnapshotStore

        self._app.state.thediscdb = SnapshotStore(Path(settings.ARM_THEDISCDB_PATH))
        self._thediscdb_refresh_task = asyncio.create_task(thediscdb_refresh_loop(self._app))

    def _build_transcode_dispatcher(self) -> TranscodeDispatcher:
        """Build the transcode dispatcher, with a docker client only when this
        deployment can transcode."""
        # No-transcode-mode: the dispatcher always runs, even for a
        # ripper-only deployment (ARM_TRANSCODE_CAPABLE=false, no remote docker
        # host), since it still needs it for passthrough tasks and the
        # stale-claim/orphan sweeps. Docker itself stays optional: `capable`
        # gates whether we even try to build a client, and the dispatcher
        # degrades encode to "held" (see TranscodeDispatcher.spawn_pending /
        # .probe) when `self._docker is None`.
        capable = effective_transcode_capable(settings)
        if (
            not settings.ARM_TRANSCODE_CAPABLE and settings.ARM_TRANSCODE_DOCKER_HOST
        ):  # pragma: no cover, contradictory env combo, defensive log only
            logger.warning(
                "ARM_TRANSCODE_CAPABLE=false but ARM_TRANSCODE_DOCKER_HOST is set; "
                "a remote docker host implies capability, treating this deployment as capable"
            )

        def _make_docker_client() -> object | None:
            return build_docker_client(settings.ARM_TRANSCODE_DOCKER_HOST)

        docker_client = _make_docker_client() if capable else None
        if not capable:  # pragma: no cover, needs ARM_TRANSCODE_CAPABLE=false; e2e runs the default-capable path
            logger.info("transcode capability off (ripper-only); dispatcher runs for passthrough and sweeps only")
        return TranscodeDispatcher(
            settings=settings,
            db_factory=SessionLocal,
            docker_client=docker_client,
            hub=self._app.state.ws_hub,
            docker_client_factory=_make_docker_client if capable else None,
            schema_store=self._app.state.handbrake_schema_store,
        )

    def _start_transcode_dispatcher(self) -> None:
        """Start the transcode dispatcher's loop and publish it as the active
        dispatcher."""
        self._dispatcher_task = asyncio.create_task(self._transcode_dispatcher.run())
        self._app.state.transcode_dispatcher = self._transcode_dispatcher
        set_active_dispatcher(self._transcode_dispatcher)

    async def _load_handbrake_schema_store(self) -> None:
        """Publish the schema store with the newest stored dump loaded, so claim and register have a schema
        before the boot run finishes."""
        store = SchemaStore()
        async with SessionLocal() as db:
            await store.load_latest(db)
        self._app.state.handbrake_schema_store = store

    def _start_handbrake_schema_runner(self) -> HandbrakeSchemaRunner:
        """Start the boot dump of the transcode image's HandBrake schema; returns the runner for shutdown."""
        runner = HandbrakeSchemaRunner(
            settings, SessionLocal, self._transcode_dispatcher, self._app.state.handbrake_schema_store
        )
        self._app.state.handbrake_schema_runner = runner
        runner.start_boot_run()
        return runner

    def _start_gpu_probe_runner(self) -> GpuProbeRunner:
        """Start the boot pass of per-device GPU probes; returns the runner for
        shutdown."""
        # Per-device GPU probes: the boot pass removes orphaned probe containers
        # and verifies every enabled row that was never probed or has no verified
        # encoder, in the background (a no-op without a docker client); the
        # /api/gpus re-probe endpoints schedule through the same runner.
        gpu_probe_runner = GpuProbeRunner(settings, SessionLocal, self._transcode_dispatcher, self._app.state.ws_hub)
        self._app.state.gpu_probe_runner = gpu_probe_runner
        gpu_probe_runner.start_boot_pass()
        return gpu_probe_runner

    async def _start_ripper_manager(self) -> None:
        """Reconcile the enrolled rippers on the local docker daemon and start
        the ISO watchdog."""
        # Ripper manager. Always the LOCAL
        # daemon and always its OWN client: the drives are plugged into this
        # host, whatever ARM_TRANSCODE_DOCKER_HOST says about transcoders, and a
        # client isn't safe to share across two independent docker-py callers
        # (each has its own connection pool / lifecycle expectations).
        ripper_manager: RipperManager | None = None
        self._iso_watchdog_task = None
        local_docker = build_docker_client(purpose="ripper manager")
        if local_docker is not None:  # pragma: no cover — needs a real docker socket; integration tier
            ripper_manager = RipperManager(settings=settings, docker_client=local_docker)
            if not ripper_manager.host_paths_set():
                # Keep the manager on app.state even though it's disabled: the
                # diagnostics endpoint distinguishes "no docker socket" (manager
                # is None) from "docker is fine but ARM_HOST_*_PATH isn't set"
                # (manager present, host_paths_set() False) — see routers/system.py.
                logger.warning("ripper manager disabled: ARM_HOST_*_PATH not set (set them via .env)")
            else:
                # The reconcile runs the virtual-drive (ISO) sweep first, so a
                # finished ISO rip is retired before the enrolled list is loaded
                # and never respawned. The hub exists by now.
                try:
                    await reconcile_enrolled_rippers(ripper_manager, SessionLocal, hub=self._app.state.ws_hub)
                except Exception as exc:
                    logger.exception("startup ripper reconcile failed: %s", exc)
                # Rip from ISO: retire each virtual drive whose one-shot ripper has exited.
                self._iso_watchdog_task = asyncio.create_task(
                    run_virtual_drive_watchdog(SessionLocal, ripper_manager, self._app.state.ws_hub)
                )
        self._app.state.ripper_manager = ripper_manager

    def _start_notifications(self) -> None:
        """Start the outbound notification dispatcher (Apprise, bash hooks and
        the inbox)."""
        # Outbound notifications (Apprise + bash hooks). Off out of the box;
        # the dispatcher polls but no-ops until the user enables notifications in
        # the UI and saves at least one valid Apprise URL.
        notifier = RealAppriseNotifier(settings.ARM_NOTIFY_IMAGE_URL)
        self._app.state.notifier = notifier
        self._notification_dispatcher = MessageDispatcher(
            settings=settings,
            db_factory=SessionLocal,
            listeners=[
                AppriseListener(notifier),
                BashListener(
                    scripts_root=settings.ARM_SCRIPTS_ROOT, media_root=settings.MEDIA_ROOT, raw_root=settings.RAW_ROOT
                ),
                InboxListener(),
            ],
        )
        self._notification_task = asyncio.create_task(self._notification_dispatcher.run())
        self._app.state.notification_dispatcher = self._notification_dispatcher

    def _start_log_tailer(self) -> None:
        """Start the singleton tail of the job logs onto their WebSocket
        topics."""
        # Singleton tail of `/logs/*.log` → `logs.{job_id}` WS topic.
        self._log_tailer = LogTailer(self._app.state.ws_hub)
        self._log_tailer_task = asyncio.create_task(self._log_tailer.run())
        self._app.state.log_tailer = self._log_tailer

    def _start_drive_scanner(self) -> None:
        """Start the periodic host drive scan."""
        self._drive_scanner = DriveScanner(
            SessionLocal, sysfs_root=Path(settings.ARM_SYSFS_ROOT), disk_root=Path(settings.ARM_HOST_DISK_ROOT)
        )
        self._drive_scanner_task = asyncio.create_task(self._drive_scanner.run())
        self._app.state.drive_scanner = self._drive_scanner

    def _start_disk_refresher(self) -> None:
        """Start the periodic disk-usage refresh of the data roots."""
        _roots_map = getattr(self._app.state, "system_paths", None) or {
            "MEDIA_ROOT": settings.MEDIA_ROOT,
            "RAW_ROOT": settings.RAW_ROOT,
            "ISO_INGRESS_ROOT": settings.ISO_INGRESS_ROOT,
            "LOG_DIR": "/logs",
        }
        self._disk_refresher = DiskRefresher(list(_roots_map.values()))
        self._disk_refresher_task = asyncio.create_task(self._disk_refresher.run())
        self._app.state.disk_refresher = self._disk_refresher

    async def _stop_thediscdb_refresh(self) -> None:
        self._thediscdb_refresh_task.cancel()
        try:
            await asyncio.wait_for(self._thediscdb_refresh_task, timeout=10.0)
        except TimeoutError, asyncio.CancelledError:  # pragma: no cover, cancellation is the expected path
            pass

    async def _stop_disk_refresher(self) -> None:
        self._disk_refresher.stop()
        try:
            await asyncio.wait_for(self._disk_refresher_task, timeout=10.0)
        except TimeoutError, asyncio.CancelledError:
            self._disk_refresher_task.cancel()

    async def _stop_log_tailer(self) -> None:
        self._log_tailer.stop()
        try:
            await asyncio.wait_for(self._log_tailer_task, timeout=10.0)
        except asyncio.TimeoutError:  # pragma: no cover, only if the tailer hangs >10s on shutdown
            self._log_tailer_task.cancel()

    async def _stop_drive_scanner(self) -> None:
        self._drive_scanner_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._drive_scanner_task

    async def _stop_iso_watchdog(self) -> None:
        if self._iso_watchdog_task is not None:  # pragma: no cover — only with a real docker socket (see above)
            self._iso_watchdog_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._iso_watchdog_task

    async def _stop_notifications(self) -> None:
        self._notification_dispatcher.stop()
        try:
            await asyncio.wait_for(self._notification_task, timeout=10.0)
        except asyncio.TimeoutError:  # pragma: no cover, only if the dispatcher hangs >10s on shutdown
            self._notification_task.cancel()

    async def _stop_transcode_dispatcher(self) -> None:
        # transcode_dispatcher/dispatcher_task are unconditionally set above
        # (the dispatcher always runs, docker or not).
        self._transcode_dispatcher.stop()
        try:
            await asyncio.wait_for(self._dispatcher_task, timeout=10.0)
        except asyncio.TimeoutError:  # pragma: no cover, only if the dispatcher hangs >10s on shutdown
            self._dispatcher_task.cancel()

    async def stop(self) -> None:
        """Run every shutdown step; each runs whatever an earlier one raised."""
        for name, step in self._shutdown_steps:
            try:
                await step()
            except Exception:
                logger.exception("backend shutdown: stopping the %s failed", name)


@asynccontextmanager
async def _lifespan_services(app: FastAPI) -> AsyncIterator[None]:
    services = _BackendServices(app)
    await services.start()
    try:
        yield
    finally:
        await services.stop()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # The active-dispatcher holder is cleared however startup or shutdown
    # ends, so a stopped dispatcher never answers gpu_awaiting_probe.
    try:
        async with _lifespan_services(app):
            yield
    finally:
        set_active_dispatcher(None)


app = FastAPI(title="ARM v3 Backend", lifespan=lifespan)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(ripper.router)
app.include_router(jobs.router)
app.include_router(identity_router.router)
app.include_router(drives.router)
app.include_router(iso_router.router)
app.include_router(sessions.router)
app.include_router(session_routes.router)
app.include_router(rip_presets.router)
app.include_router(transcode_presets.router)
app.include_router(transcoder.router)
app.include_router(transcodes.router)
app.include_router(gpus_router.router)
app.include_router(encoders_router.router)
app.include_router(handbrake_schema_router.router)
app.include_router(config_router.router)
app.include_router(diagnostics.router)
app.include_router(metadata_router.router)
app.include_router(naming_router.router)
app.include_router(notifications_router.router)
app.include_router(logs_router.router)
app.include_router(images_router.router)
app.include_router(themes_router.router)
app.include_router(settings_router.router)
app.include_router(system_router.router)
app.include_router(setup_router.router)
app.include_router(files_router.router)
app.include_router(users_router.router)
app.include_router(ws_router)
declare_guest_reads(app.routes)


def main() -> None:
    uvicorn.run(
        "arm_backend.main:app",
        host=settings.BIND_HOST,
        port=settings.BIND_PORT,
        ssl_certfile=settings.TLS_CERT_PATH,
        ssl_keyfile=settings.TLS_KEY_PATH,
        log_level=settings.ARM_LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
