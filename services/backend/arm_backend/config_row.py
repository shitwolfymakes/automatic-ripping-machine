"""Reads the config singleton row, the one query every caller shares."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.constants import CONFIG_SINGLETON_ID
from arm_common import Config


async def load_config_or_none(db: AsyncSession) -> Config | None:
    """The config singleton, or None before the seeder has written it."""
    return (await db.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
