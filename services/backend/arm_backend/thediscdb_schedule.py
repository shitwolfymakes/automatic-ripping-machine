"""The daily TheDiscDB check: refresh the local snapshot when it is missing
or older than thediscdb_refresh_days."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from sqlmodel import col, select

from arm_backend.config import settings
from arm_backend.constants import CONFIG_SINGLETON_ID
from arm_backend.db import SessionLocal
from arm_common import Config

logger = logging.getLogger(__name__)


async def thediscdb_refresh_loop(app: FastAPI) -> None:
    """Daily check; refresh the snapshot when absent or older than
    cfg.thediscdb_refresh_days. Failures keep the previous index."""
    from arm_backend.identity.sources.thediscdb_refresh import refresh as thediscdb_refresh

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
