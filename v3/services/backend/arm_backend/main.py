import logging
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import uvicorn
from fastapi import FastAPI

from arm_backend.config import settings
from arm_backend.db import SessionLocal
from arm_backend.metadata import MetadataDispatcher
from arm_backend.routers import health, jobs, ripper
from arm_backend.seeders import run_seeders

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


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _run_migrations()
    await _run_seeders()
    http = httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=10.0, write=10.0, pool=10.0))
    app.state.dispatcher = MetadataDispatcher(http, omdb_api_key_override=settings.OMDB_API_KEY)
    try:
        yield
    finally:
        await app.state.dispatcher.aclose()


app = FastAPI(title="ARM v3 Backend", lifespan=lifespan)
app.include_router(health.router)
app.include_router(ripper.router)
app.include_router(jobs.router)


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
