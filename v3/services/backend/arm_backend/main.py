import asyncio
import logging
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI
from sqlmodel import col, select

from arm_backend.config import settings
from arm_backend.db import SessionLocal
from arm_backend.metadata import MetadataDispatcher
from arm_backend.routers import (
    auth,
    config as config_router,
    diagnostics,
    drives,
    health,
    jobs,
    rip_presets,
    ripper,
    sessions,
    transcode_presets,
    transcoder,
    transcodes,
)
from arm_backend.seeders import CONFIG_SINGLETON_ID, run_seeders
from arm_backend.transcode_dispatcher import TranscodeDispatcher
from arm_backend.ws import WSHub
from arm_backend.ws.router import router as ws_router
from arm_common import Config

logging.basicConfig(
    level=settings.ARM_LOG_LEVEL.upper(),
    format='{"ts":"%(asctime)s","level":"%(levelname)s","service":"arm-backend","msg":%(message)r}',
)
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
        if cfg.session_signing_key is None:
            raise RuntimeError("session_signing_key missing — seeders should have populated it")
        app.state.signing_key = cfg.session_signing_key
    http = httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=10.0))
    app.state.dispatcher = MetadataDispatcher(http, omdb_api_key_override=settings.OMDB_API_KEY)
    app.state.ws_hub = WSHub()

    docker_client = _build_docker_client()
    transcode_dispatcher: TranscodeDispatcher | None = None
    dispatcher_task: asyncio.Task[None] | None = None
    if docker_client is not None:
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

    try:
        yield
    finally:
        if transcode_dispatcher is not None:
            transcode_dispatcher.stop()
        if dispatcher_task is not None:
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
