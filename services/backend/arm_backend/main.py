import asyncio
import logging
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
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
from arm_backend.log_tailer import LogTailer
from arm_backend.metadata import MetadataDispatcher
from arm_backend.notification_dispatcher import (
    MessageDispatcher,
    _RealAppriseNotifier,
)
from arm_backend.notifications.apprise_listener import AppriseListener
from arm_backend.notifications.inbox_listener import InboxListener
from arm_backend.routers import (
    auth,
    config as config_router,
    diagnostics,
    drives,
    health,
    iso as iso_router,
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
    transcode_presets,
    transcoder,
    transcodes,
)
from arm_backend.seeders import CONFIG_SINGLETON_ID, run_seeders
from arm_backend.transcode_dispatcher import TranscodeDispatcher
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


def _build_docker_client() -> object | None:
    """Construct a docker-py client. Returns None if the socket isn't reachable
    (dev environments without `/var/run/docker.sock` mounted)."""
    try:
        import docker  # type: ignore[import-untyped]

        client: object = docker.from_env()
        return client
    except Exception as exc:
        logger.warning("docker-py client unavailable: %s — transcode dispatcher disabled", exc)
        return None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _run_migrations()
    await _run_seeders()
    async with SessionLocal() as session:
        cfg = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one()
        if cfg.session_signing_key is None:  # pragma: no cover — _run_seeders always populates this; defensive only
            raise RuntimeError("session_signing_key missing — seeders should have populated it")
        app.state.signing_key = cfg.session_signing_key
    http = httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=10.0))
    app.state.http = http
    app.state.started_at = datetime.now(UTC)
    app.state.dispatcher = MetadataDispatcher(http)
    app.state.ws_hub = WSHub()

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

    docker_client = _build_docker_client()
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
        dispatcher_task = asyncio.create_task(transcode_dispatcher.run())
    app.state.transcode_dispatcher = transcode_dispatcher

    # Phase 11 — outbound Apprise notifications. Off out of the box; the
    # dispatcher polls but no-ops until the user enables notifications in
    # the UI and saves at least one valid Apprise URL.
    notifier = _RealAppriseNotifier()
    app.state.notifier = notifier
    notification_dispatcher = MessageDispatcher(
        settings=settings,
        db_factory=SessionLocal,
        listeners=[AppriseListener(notifier), InboxListener()],
    )
    notification_task = asyncio.create_task(notification_dispatcher.run())
    app.state.notification_dispatcher = notification_dispatcher

    # Phase 12 — singleton tail of `/logs/*.log` → `logs.{job_id}` WS topic.
    log_tailer = LogTailer(app.state.ws_hub)
    log_tailer_task = asyncio.create_task(log_tailer.run())
    app.state.log_tailer = log_tailer

    try:
        yield
    finally:
        log_tailer.stop()
        try:
            await asyncio.wait_for(log_tailer_task, timeout=10.0)
        except asyncio.TimeoutError:  # pragma: no cover — only if the tailer hangs >10s on shutdown
            log_tailer_task.cancel()
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
app.include_router(iso_router.router)
app.include_router(logs_router.router)
app.include_router(settings_router.router)
app.include_router(system_router.router)
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
