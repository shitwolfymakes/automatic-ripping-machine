import asyncio
import contextlib
import logging
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI
from sqlalchemy import delete
from sqlmodel import col, select

from arm_backend.config import settings
from arm_backend.crash_recovery import sweep_in_flight_jobs
from arm_backend.db import SessionLocal
from arm_backend.gpu_probe import load_configured_gpus
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
from arm_backend.ripper_manager import RipperManager, reconcile_enrolled_rippers
from arm_backend.routers import (
    auth,
    config as config_router,
    diagnostics,
    drives,
    files as files_router,
    health,
    images as images_router,
    jobs,
    logs as logs_router,
    metadata as metadata_router,
    naming as naming_router,
    notifications as notifications_router,
    rip_presets,
    ripper,
    sessions,
    settings as settings_router,
    system as system_router,
    themes as themes_router,
    transcode_presets,
    transcoder,
    transcodes,
    users as users_router,
)
from arm_backend.seeders import CONFIG_SINGLETON_ID, run_seeders
from arm_backend.transcode_dispatcher import TranscodeDispatcher
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
    """Load the install-time GPU inventory, truncate `gpus`, repopulate.

    Emit `transcode.hw_unavailable` on empty. The descriptor comes from the
    `ARM_GPUS` env (host-side detection at install time); the backend does not
    probe hardware. `load_configured_gpus` degrades to `[]` on malformed input.
    """
    probed = load_configured_gpus(settings.ARM_GPUS)
    now = datetime.now(UTC)
    async with SessionLocal() as session:
        await session.execute(delete(Gpu))
        for g in probed:
            session.add(
                Gpu(
                    vendor=g.vendor,
                    device_path=g.device_path,
                    encoder_kinds=g.encoder_kinds,
                    status=GpuStatus.AVAILABLE,
                    last_seen_at=now,
                )
            )
        if not probed:
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
    from arm_backend.thediscdb.snapshot import refresh as thediscdb_refresh

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
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
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

    from arm_backend.thediscdb.snapshot import SnapshotStore

    app.state.thediscdb = SnapshotStore(Path(settings.ARM_THEDISCDB_PATH))
    thediscdb_refresh_task = asyncio.create_task(_thediscdb_refresh_loop(app))

    # GPU probe — truncate-and-fill the gpus table so the dispatcher's first
    # tick sees a consistent inventory. Runs before the dispatcher starts.
    await _refresh_gpu_inventory(app.state.ws_hub)

    # Phase 9 — reset every RIPPING job's tracks to queued and stamp
    # resumed_from_crash. Idempotent across boots; no-op when nothing crashed.
    try:
        swept = await sweep_in_flight_jobs(SessionLocal)
        if swept:  # pragma: no cover — only when a crashed RIPPING job is recovered; sweep logic is unit-tested in test_crash_recovery
            logger.info("backend startup: resumed %d crashed rip(s)", swept)
    except Exception as exc:  # pragma: no cover — startup-degradation guard; sweep failing is real-DB-only
        logger.exception("startup crash-recovery sweep failed: %s", exc)

    docker_client = _build_docker_client(settings.ARM_TRANSCODE_DOCKER_HOST)
    transcode_dispatcher: TranscodeDispatcher | None = None
    dispatcher_task: asyncio.Task[None] | None = None
    if docker_client is not None:  # pragma: no cover — needs a real docker socket; integration tier, not the SQLite e2e
        transcode_dispatcher = TranscodeDispatcher(
            settings=settings,
            db_factory=SessionLocal,
            docker_client=docker_client,
            hub=app.state.ws_hub,
        )
        # One-shot orphan sweep before the dispatcher loop starts.
        try:
            swept = await transcode_dispatcher.sweep_arm_inprogress(Path(settings.MEDIA_ROOT))
            if swept:
                logger.info("backend startup: swept %d .arm-inprogress orphans", swept)
        except Exception as exc:
            logger.exception("startup .arm-inprogress sweep failed: %s", exc)
        # One-shot reconcile of crash-orphaned session_applications (no live task).
        try:
            async with SessionLocal() as db:
                orphaned = await transcode_dispatcher.sweep_orphaned_applications(db)
                await db.commit()
            if orphaned:
                logger.info("backend startup: reconciled %d orphaned session_application(s)", orphaned)
        except Exception as exc:
            logger.exception("startup orphaned-application sweep failed: %s", exc)
        dispatcher_task = asyncio.create_task(transcode_dispatcher.run())
    app.state.transcode_dispatcher = transcode_dispatcher

    # Drive lifecycle Plan 3 — ripper manager (spec §3). Always the LOCAL
    # daemon and always its OWN client: the drives are plugged into this
    # host, whatever ARM_TRANSCODE_DOCKER_HOST says about transcoders, and a
    # client isn't safe to share across two independent docker-py callers
    # (each has its own connection pool / lifecycle expectations).
    ripper_manager: RipperManager | None = None
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
            try:
                await reconcile_enrolled_rippers(ripper_manager, SessionLocal)
            except Exception as exc:
                logger.exception("startup ripper reconcile failed: %s", exc)
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

    try:
        yield
    finally:
        thediscdb_refresh_task.cancel()
        try:
            await asyncio.wait_for(thediscdb_refresh_task, timeout=10.0)
        except TimeoutError, asyncio.CancelledError:  # pragma: no cover — cancellation is the expected path
            pass
        disk_refresher.stop()
        try:
            await asyncio.wait_for(disk_refresher_task, timeout=10.0)
        except TimeoutError, asyncio.CancelledError:
            disk_refresher_task.cancel()
        log_tailer.stop()
        try:
            await asyncio.wait_for(log_tailer_task, timeout=10.0)
        except asyncio.TimeoutError:  # pragma: no cover — only if the tailer hangs >10s on shutdown
            log_tailer_task.cancel()
        drive_scanner_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await drive_scanner_task
        notification_dispatcher.stop()
        try:
            await asyncio.wait_for(notification_task, timeout=10.0)
        except asyncio.TimeoutError:  # pragma: no cover — only if the dispatcher hangs >10s on shutdown
            notification_task.cancel()
        if transcode_dispatcher is not None:  # pragma: no cover — set only on the real-docker path above
            transcode_dispatcher.stop()
        if dispatcher_task is not None:  # pragma: no cover — set only on the real-docker path above
            try:
                await asyncio.wait_for(dispatcher_task, timeout=10.0)
            except asyncio.TimeoutError:
                dispatcher_task.cancel()
        await app.state.dispatcher.aclose()


app = FastAPI(title="ARM v3 Backend", lifespan=lifespan)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(ripper.router)
app.include_router(jobs.router)
app.include_router(drives.router)
app.include_router(sessions.router)
app.include_router(rip_presets.router)
app.include_router(transcode_presets.router)
app.include_router(transcoder.router)
app.include_router(transcodes.router)
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
