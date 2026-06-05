import ssl
from collections.abc import AsyncIterator
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from arm_backend.config import settings


def _build_engine(url: str) -> AsyncEngine:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    sslmode = query.pop("sslmode", [None])[0]
    sslrootcert = query.pop("sslrootcert", [None])[0]

    connect_args: dict[str, object] = {}
    if sslmode in ("verify-ca", "verify-full"):
        ctx = ssl.create_default_context(cafile=sslrootcert)
        if sslmode == "verify-ca":
            ctx.check_hostname = False
        connect_args["ssl"] = ctx
    elif sslmode == "require":
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        connect_args["ssl"] = ctx

    clean_url = urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
    if clean_url.startswith("postgresql://"):
        clean_url = "postgresql+asyncpg://" + clean_url[len("postgresql://") :]

    return create_async_engine(clean_url, echo=False, future=True, connect_args=connect_args)


engine = _build_engine(settings.DATABASE_URL)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


# Exercised only against a real database: every test overrides this
# FastAPI dependency (fake-session unit tests) or rebinds SessionLocal to
# a SQLite engine (e2e harness), so the production asyncpg path here is
# never hit in CI. Covered for real in production / a real-Postgres tier.
async def get_session() -> AsyncIterator[AsyncSession]:  # pragma: no cover
    async with SessionLocal() as session:
        yield session
