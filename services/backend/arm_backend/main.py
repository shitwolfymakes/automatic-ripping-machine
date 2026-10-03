import asyncio
import contextlib
import logging
import subprocess
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI
from sqlmodel import col, select

from arm_backend.config import effective_transcode_capable, settings
from arm_backend.crash_recovery import sweep_in_flight_jobs
from arm_backend.db import SessionLocal
from arm_backend.gpu_probe import load_configured_gpus
from arm_backend.gpu_probe_runner import GpuProbeRunner
from arm_backend.identity.stage_runner import EpisodeStageRunner
from arm_backend import image_cache
from arm_backend.disk_refresh import DiskRefresher
from arm_backend.drive_scanner import DriveScanner
from arm_backend.log_tailer import LogTailer
from arm_backend.metadata import MetadataDispatcher
from arm_backend.notification_dispatcher import (
    MessageDispatcher,
    _RealAppriseNotifier,
)
from arm_backend.notifications.apprise_listener import AppriseListener
from arm_backend.notifications.bash_listener import BashListener
from arm_backend.notifications.inbox_listener import InboxListener
from arm_backend.iso_rips import run_virtual_drive_watchdog
from arm_backend.ripper_manager import RipperManager, reconcile_enrolled_rippers
from arm_backend.routers import (
    gpus as gpus_router,
    encoders as encoders_router,
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
from arm_backend.seeders import CONFIG_SINGLETON_ID, run_seeders
from arm_backend.transcode_dispatcher import TranscodeDispatcher, set_active_dispatcher
from arm_backend.utils import ensure_roots, default_roots
from arm_backend.ws import WSHub
from arm_backend.ws.router import router as ws_router
from arm_common import Config, Gpu, GpuStatus, configure_service_logging

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


async def _refresh_gpu_inventory(hub: WSHub) -> None:
    """Seed the `gpus` table from `ARM_GPUS` - but only when it is empty.

    The table is DB-authoritative: operators manage devices from Settings >
    GPUs (enable/disable/delete), and those edits must survive restarts, so
    an already-populated table is left untouched. Deleting every row and
    restarting the backend is the deliberate re-seed path (the GPUs card
    documents it). The env descriptor comes from host-side detection at
    install time (or is hand-written for remote transcode hosts). Its
    `encoder_kinds` are hints only: seeded rows start with no verified
    encoders and `probed_at` NULL, and the boot probe pass
    (`GpuProbeRunner.probe_unprobed`) verifies each device. `load_configured_gpus`
    degrades to `[]` on malformed input. Emits `transcode.hw_unavailable` when
    the inventory ends up empty.
    """
    now = datetime.now(UTC)
    async with SessionLocal() as session:
        existing = (await session.execute(select(Gpu))).scalars().all()
        if existing:
            logger.info("gpu inventory: %d device(s) in DB (authoritative); ARM_GPUS not consulted", len(existing))
            return
        probed = load_configured_gpus(settings.ARM_GPUS)
        for g in probed:
            session.add(
                Gpu(
                    vendor=g.vendor,
                    device_path=g.device_path,
                    encoder_kinds=[],
                    status=GpuStatus.AVAILABLE,
                    last_seen_at=now,
                    probed_at=None,
                )
            )
        if probed:
            logger.info("gpu inventory: seeded %d device(s) from ARM_GPUS into an empty table", len(probed))
        else:
            await hub.emit(
                topic="transcode.events",
                event_type="transcode.hw_unavailable",
                payload={},
                session=session,
            )
        await session.commit()


async def _thediscdb_refresh_loop(app: FastAPI) -> None:
    """Daily check; refresh the snapshot when absent or older than
    cfg.thediscdb_refresh_days. Failures keep the previous index."""
    from arm_backend.identity.sources.thediscdb_snapshot import refresh as thediscdb_refresh

    while True:
        try:
            async with SessionLocal() as session:
                cfg = (
                    await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))
                ).scalar_one_or_none()
                if cfg is not None and cfg.thediscdb_enabled:
                    stale_after = timedelta(days=max(1, cfg.thediscdb_refresh_days))
                    last = cfg.thediscdb_refreshed_at
                    store = app.state.thediscdb
                    if not store.exists() or last is None or datetime.now(UTC) - last > stale_after:
                        count = await thediscdb_refresh(app.state.http, Path(settings.ARM_THEDISCDB_PATH))
                        cfg.thediscdb_refreshed_at = datetime.now(UTC)
                        session.add(cfg)
                        await session.commit()
                        logger.info("thediscdb: snapshot refreshed (%d discs)", count)
        except Exception as e:  # noqa: BLE001 — never kill the loop
            logger.warning("thediscdb: refresh loop error: %s", e)
        await asyncio.sleep(24 * 3600)


def _build_docker_client(docker_host: str = "", *, purpose: str = "transcode dispatcher") -> object | None:
    """Construct a docker-py client. When `docker_host` is set (e.g.
    "ssh://sam@transcoder-server"), target that remote daemon so transcode
    containers spawn on a remote GPU host; otherwise use the local socket.
    Returns None if the client can't be built (dev without the socket, or an
    unreachable/misconfigured remote host) so the caller's docker-backed
    feature (named by `purpose`, e.g. "ripper manager") stays disabled rather
    than crashing the backend."""
    try:
        import docker  # type: ignore[import-untyped]

        client: object = docker.DockerClient(base_url=docker_host) if docker_host else docker.from_env()
        return client
    except Exception as exc:
        logger.warning("docker-py client unavailable: %s — %s disabled", exc, purpose)
        return None


@asynccontextmanager
async def _lifespan_services(app: FastAPI) -> AsyncIterator[None]:
    _run_migrations()
    await _run_seeders()
    # Rebuild the image-proxy disk-cache index from disk (LRU/TTL). Sync, fast,
    # no DB — safe to run before the session/dispatchers come up.
    image_cache.startup_scan()
    async with SessionLocal() as session:
        cfg = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one()
        if cfg.session_signing_key is None:  # pragma: no cover — _run_seeders always populates this; defensive only
            raise RuntimeError("session_signing_key missing — seeders should have populated it")
        app.state.signing_key = cfg.session_signing_key
    # Silently create any missing data root (never chown, never raise —
    # the entrypoint's writability guard owns the fatal cases). Diagnostics
    # re-ensures on every read.
    ensure_roots(default_roots())
    http = httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=10.0))
    app.state.http = http
    app.state.started_at = datetime.now(UTC)
    app.state.dispatcher = MetadataDispatcher(http, omdb_api_key_override=settings.OMDB_API_KEY)
    app.state.ws_hub = WSHub()
    # Background episode stage (spec 5, 6.2, 6.3, 9; plan Task 8): runs off the
    # request path, triggered by identify/resolve/PATCH (routers) and the
    # startup sweep below. One SourceHttp per source id lives on the runner
    # for its whole lifetime (rate limit / cache / backoff state, and TVDB's
    # login token on the provider built from it).
    app.state.episode_stage = EpisodeStageRunner(SessionLocal, http, app.state.ws_hub)

    from arm_backend.identity.sources.thediscdb_snapshot import SnapshotStore

    app.state.thediscdb = SnapshotStore(Path(settings.ARM_THEDISCDB_PATH))
    thediscdb_refresh_task = asyncio.create_task(_thediscdb_refresh_loop(app))

    # GPU inventory — seed the gpus table from ARM_GPUS only when empty
    # (DB-authoritative thereafter). Runs before the dispatcher starts.
    await _refresh_gpu_inventory(app.state.ws_hub)

    # Phase 9 — reset every RIPPING job's tracks to queued and stamp
    # resumed_from_crash. Idempotent across boots; no-op when nothing crashed.
    try:
        swept = await sweep_in_flight_jobs(SessionLocal)
        if swept:  # pragma: no cover — only when a crashed RIPPING job is recovered; sweep logic is unit-tested in test_crash_recovery
            logger.info("backend startup: resumed %d crashed rip(s)", swept)
    except Exception as exc:  # pragma: no cover — startup-degradation guard; sweep failing is real-DB-only
        logger.exception("startup crash-recovery sweep failed: %s", exc)

    # Episode stage startup sweep (Review Focus 5): schedule the background
    # episode stage once for every TV-candidate job that never got an
    # episode-source entry (e.g. the backend restarted between identify and
    # the runner picking it up).
    try:
        swept = await app.state.episode_stage.sweep_startup()
        # Only hit when an eligible job exists; sweep logic is unit-tested in test_stage_runner.
        if swept:  # pragma: no cover
            logger.info("backend startup: scheduled episode stage for %d job(s)", swept)
    except Exception as exc:  # pragma: no cover — startup-degradation guard; sweep failing is real-DB-only
        logger.exception("startup episode-stage sweep failed: %s", exc)

    # No-transcode-mode: the dispatcher now always runs, even for a
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
        return _build_docker_client(settings.ARM_TRANSCODE_DOCKER_HOST)

    docker_client = _make_docker_client() if capable else None
    if not capable:  # pragma: no cover, needs ARM_TRANSCODE_CAPABLE=false; e2e runs the default-capable path
        logger.info("transcode capability off (ripper-only); dispatcher runs for passthrough and sweeps only")
    transcode_dispatcher = TranscodeDispatcher(
        settings=settings,
        db_factory=SessionLocal,
        docker_client=docker_client,
        hub=app.state.ws_hub,
        docker_client_factory=_make_docker_client if capable else None,
    )
    # One-shot sweeps run in every mode (they are DB/file-side, not
    # docker-side): a ripper-only deployment still needs orphaned
    # .arm-inprogress markers and crash-orphaned session_applications cleaned
    # up on boot.
    try:
        swept = await transcode_dispatcher.sweep_arm_inprogress(Path(settings.MEDIA_ROOT))
        if swept:  # pragma: no cover, only when a startup orphan exists; sweep logic is unit-tested in test_transcode_dispatcher
            logger.info("backend startup: swept %d .arm-inprogress orphans", swept)
    except Exception as exc:  # pragma: no cover, startup-degradation guard; sweep failing is real-DB-only
        logger.exception("startup .arm-inprogress sweep failed: %s", exc)
    try:
        async with SessionLocal() as db:
            orphaned = await transcode_dispatcher.sweep_orphaned_applications(db)
            await db.commit()
        if orphaned:  # pragma: no cover, only when a startup orphan exists; sweep logic is unit-tested in test_transcode_dispatcher
            logger.info("backend startup: reconciled %d orphaned session_application(s)", orphaned)
    except Exception as exc:  # pragma: no cover, startup-degradation guard; sweep failing is real-DB-only
        logger.exception("startup orphaned-application sweep failed: %s", exc)
    dispatcher_task = asyncio.create_task(transcode_dispatcher.run())
    app.state.transcode_dispatcher = transcode_dispatcher
    set_active_dispatcher(transcode_dispatcher)
    # Per-device GPU probes: the boot pass removes orphaned probe containers
    # and verifies every enabled row that was never probed or has no verified
    # encoder, in the background (a no-op without a docker client); the
    # /api/gpus re-probe endpoints schedule through the same runner.
    gpu_probe_runner = GpuProbeRunner(settings, SessionLocal, transcode_dispatcher, app.state.ws_hub)
    app.state.gpu_probe_runner = gpu_probe_runner
    gpu_probe_runner.start_boot_pass()

    # Drive lifecycle Plan 3 — ripper manager (spec §3). Always the LOCAL
    # daemon and always its OWN client: the drives are plugged into this
    # host, whatever ARM_TRANSCODE_DOCKER_HOST says about transcoders, and a
    # client isn't safe to share across two independent docker-py callers
    # (each has its own connection pool / lifecycle expectations).
    ripper_manager: RipperManager | None = None
    iso_watchdog_task: asyncio.Task[None] | None = None
    local_docker = _build_docker_client(purpose="ripper manager")
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
            # and never respawned (spec 6.2). The hub exists by now.
            try:
                await reconcile_enrolled_rippers(ripper_manager, SessionLocal, hub=app.state.ws_hub)
            except Exception as exc:
                logger.exception("startup ripper reconcile failed: %s", exc)
            # Rip from ISO: retire each virtual drive whose one-shot ripper has exited.
            iso_watchdog_task = asyncio.create_task(
                run_virtual_drive_watchdog(SessionLocal, ripper_manager, app.state.ws_hub)
            )
    app.state.ripper_manager = ripper_manager

    # Phase 11 - outbound notifications (Apprise + bash hooks). Off out of the box;
    # the dispatcher polls but no-ops until the user enables notifications in
    # the UI and saves at least one valid Apprise URL.
    notifier = _RealAppriseNotifier(settings.ARM_NOTIFY_IMAGE_URL)
    app.state.notifier = notifier
    notification_dispatcher = MessageDispatcher(
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
    notification_task = asyncio.create_task(notification_dispatcher.run())
    app.state.notification_dispatcher = notification_dispatcher

    # Phase 12 — singleton tail of `/logs/*.log` → `logs.{job_id}` WS topic.
    log_tailer = LogTailer(app.state.ws_hub)
    log_tailer_task = asyncio.create_task(log_tailer.run())
    app.state.log_tailer = log_tailer

    # Drive lifecycle Plan 2 — periodic host drive scan (spec §2).
    drive_scanner = DriveScanner(
        SessionLocal, sysfs_root=Path(settings.ARM_SYSFS_ROOT), disk_root=Path(settings.ARM_HOST_DISK_ROOT)
    )
    drive_scanner_task = asyncio.create_task(drive_scanner.run())
    app.state.drive_scanner = drive_scanner

    _roots_map = getattr(app.state, "system_paths", None) or {
        "MEDIA_ROOT": settings.MEDIA_ROOT,
        "RAW_ROOT": settings.RAW_ROOT,
        "ISO_INGRESS_ROOT": settings.ISO_INGRESS_ROOT,
        "LOG_DIR": "/logs",
    }
    disk_refresher = DiskRefresher(list(_roots_map.values()))
    disk_refresher_task = asyncio.create_task(disk_refresher.run())
    app.state.disk_refresher = disk_refresher

    async def _stop_thediscdb_refresh() -> None:
        thediscdb_refresh_task.cancel()
        try:
            await asyncio.wait_for(thediscdb_refresh_task, timeout=10.0)
        except TimeoutError, asyncio.CancelledError:  # pragma: no cover, cancellation is the expected path
            pass

    async def _stop_disk_refresher() -> None:
        disk_refresher.stop()
        try:
            await asyncio.wait_for(disk_refresher_task, timeout=10.0)
        except TimeoutError, asyncio.CancelledError:
            disk_refresher_task.cancel()

    async def _stop_log_tailer() -> None:
        log_tailer.stop()
        try:
            await asyncio.wait_for(log_tailer_task, timeout=10.0)
        except asyncio.TimeoutError:  # pragma: no cover, only if the tailer hangs >10s on shutdown
            log_tailer_task.cancel()

    async def _stop_drive_scanner() -> None:
        drive_scanner_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await drive_scanner_task

    async def _stop_iso_watchdog() -> None:
        if iso_watchdog_task is not None:  # pragma: no cover — only with a real docker socket (see above)
            iso_watchdog_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await iso_watchdog_task

    async def _stop_notifications() -> None:
        notification_dispatcher.stop()
        try:
            await asyncio.wait_for(notification_task, timeout=10.0)
        except asyncio.TimeoutError:  # pragma: no cover, only if the dispatcher hangs >10s on shutdown
            notification_task.cancel()

    async def _stop_transcode_dispatcher() -> None:
        # transcode_dispatcher/dispatcher_task are unconditionally set above
        # (the dispatcher always runs, docker or not).
        transcode_dispatcher.stop()
        try:
            await asyncio.wait_for(dispatcher_task, timeout=10.0)
        except asyncio.TimeoutError:  # pragma: no cover, only if the dispatcher hangs >10s on shutdown
            dispatcher_task.cancel()

    shutdown_steps: list[tuple[str, Callable[[], Awaitable[None]]]] = [
        ("thediscdb refresh", _stop_thediscdb_refresh),
        ("disk refresher", _stop_disk_refresher),
        ("log tailer", _stop_log_tailer),
        ("drive scanner", _stop_drive_scanner),
        ("iso watchdog", _stop_iso_watchdog),
        ("notification dispatcher", _stop_notifications),
        # Cancels the boot pass and any re-probe, waiting briefly so each
        # cancelled probe removes its container.
        ("gpu probe runner", gpu_probe_runner.shutdown),
        ("transcode dispatcher", _stop_transcode_dispatcher),
        ("episode stage runner", app.state.episode_stage.shutdown),
        ("metadata dispatcher", app.state.dispatcher.aclose),
    ]

    try:
        yield
    finally:
        # Each step runs whatever an earlier one raised.
        for name, step in shutdown_steps:
            try:
                await step()
            except Exception:
                logger.exception("backend shutdown: stopping the %s failed", name)


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
