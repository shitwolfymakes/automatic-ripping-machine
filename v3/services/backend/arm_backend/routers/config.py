"""UI-side config read/write. Never wire-exposes `session_signing_key`."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.db import get_session
from arm_backend.seeders import CONFIG_SINGLETON_ID
from arm_common import Config, User
from arm_common.schemas import ConfigUpdateRequest, ConfigView

router = APIRouter(prefix="/api/config", tags=["config"])


def _to_view(cfg: Config) -> ConfigView:
    return ConfigView(
        tmdb_api_key=cfg.tmdb_api_key,
        omdb_api_key=cfg.omdb_api_key,
        musicbrainz_user_agent=cfg.musicbrainz_user_agent,
        auto_transcode_on_idle=cfg.auto_transcode_on_idle,
        block_on_miss=cfg.block_on_miss,
        default_retention_policy=cfg.default_retention_policy,
        notification_apprise_urls=list(cfg.notification_apprise_urls or []),
        updated_by_user_id=cfg.updated_by_user_id,
        updated_at=cfg.updated_at,
    )


@router.get("", response_model=ConfigView)
async def get_config(
    _: User = Depends(require_jwt),
    session: AsyncSession = Depends(get_session),
) -> ConfigView:
    cfg = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="config singleton missing")
    return _to_view(cfg)


@router.patch("", response_model=ConfigView)
async def update_config(
    req: ConfigUpdateRequest,
    user: User = Depends(require_jwt),
    session: AsyncSession = Depends(get_session),
) -> ConfigView:
    cfg = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="config singleton missing")

    fields = req.model_dump(exclude_unset=True)
    for key, value in fields.items():
        setattr(cfg, key, value)
    cfg.updated_by_user_id = user.id
    cfg.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(cfg)
    return _to_view(cfg)
