"""UI-side config read/write. Never wire-exposes `session_signing_key`.

`notification_apprise_urls` round-trips by value but never appears in log
output — the validation helper redacts the URL in any 400 response, and
the handler itself logs nothing about config bodies. Phase 11 added the
`notifications_enabled` master toggle (default False) so the UI can enable
or disable outbound Apprise dispatch without dropping the saved URL list.

As of the notification-channels feature, `notification_apprise_urls` is
DEPRECATED as a delivery source — the dispatcher now reads
`notification_channels` rows (migration 0015 imported the existing list).
The field is still accepted/returned here for backward compatibility but
is no longer used for dispatch; `notifications_enabled` remains the global
master toggle. New URLs should be added as channels via /api/notifications.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.db import get_session
from arm_backend.notification_dispatcher import (
    _first_invalid_apprise_url,
    redact_apprise_url,
)
from arm_backend.seeders import CONFIG_SINGLETON_ID
from arm_common import Config, User
from arm_common.config_metadata import CONFIG_FIELD_META
from arm_common.schemas import ConfigUpdateRequest, ConfigView
from arm_common.secrets import HIDDEN_SECRET

router = APIRouter(prefix="/api/config", tags=["config"])

_NON_EDITABLE_KEYS = frozenset(m.key for m in CONFIG_FIELD_META if not m.editable)

# Secret-tier config fields, derived from the registry so a future secret field
# auto-masks. The `& ConfigView.model_fields` guard keeps masking aligned to what's
# actually exposed: e.g. when tvdb_api_key gains its registry+ConfigView entry (B29),
# it masks automatically; a secret-tier field not yet on ConfigView is skipped.
_SECRET_KEYS = frozenset(m.key for m in CONFIG_FIELD_META if m.tier == "secret") & set(ConfigView.model_fields)


def _to_view(cfg: Config) -> ConfigView:
    view = ConfigView(
        tmdb_api_key=cfg.tmdb_api_key,
        omdb_api_key=cfg.omdb_api_key,
        tvdb_api_key=cfg.tvdb_api_key,
        makemkv_key=cfg.makemkv_key,
        musicbrainz_user_agent=cfg.musicbrainz_user_agent,
        auto_transcode_on_idle=cfg.auto_transcode_on_idle,
        auto_rip_on_insert=cfg.auto_rip_on_insert,
        block_on_miss=cfg.block_on_miss,
        # `bool(...)` coerces the None a bare in-memory Config carries (the
        # server_default is DB-level only) to False, so _to_view works for
        # rows/fixtures predating this column. The sibling bools predate their
        # consumers' fixtures so they don't need it.
        ripping_paused=bool(cfg.ripping_paused),
        default_retention_policy=cfg.default_retention_policy,
        notification_apprise_urls=list(cfg.notification_apprise_urls or []),
        notifications_enabled=cfg.notifications_enabled,
        metadata_provider=cfg.metadata_provider or "tmdb",
        makemkv_key_valid=cfg.makemkv_key_valid,
        makemkv_key_state=cfg.makemkv_key_state,
        makemkv_key_checked_at=cfg.makemkv_key_checked_at,
        updated_by_user_id=cfg.updated_by_user_id,
        updated_at=cfg.updated_at,
    )
    for key in _SECRET_KEYS:
        if getattr(view, key):  # non-empty stored secret → mask; None/"" stays as-is
            setattr(view, key, HIDDEN_SECRET)
    return view


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
    request: Request,
    user: User = Depends(require_jwt),
    session: AsyncSession = Depends(get_session),
) -> ConfigView:
    # FastAPI has already validated the body into `req` (a ConfigUpdateRequest),
    # so a non-object body is rejected with 422 before we get here — `raw` is
    # always a dict. We re-read the raw body because `req` silently drops unknown
    # keys, so model_dump() would never reveal a forbidden (infra/non-editable) key.
    raw = await request.json()
    forbidden = _NON_EDITABLE_KEYS & set(raw.keys())
    if forbidden:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"non-editable settings cannot be patched: {sorted(forbidden)}",
        )

    cfg = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="config singleton missing")

    fields = req.model_dump(exclude_unset=True)
    # A secret field whose submitted value is the masked sentinel means "keep the
    # stored secret" — drop it from the update set so it isn't overwritten with the
    # literal "<hidden>". Real values update; "" / None clears (normal setattr below).
    for key in _SECRET_KEYS:
        if fields.get(key) == HIDDEN_SECRET:
            del fields[key]
    if fields.get("notification_apprise_urls"):
        bad = _first_invalid_apprise_url(fields["notification_apprise_urls"])
        if bad is not None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"invalid apprise URL: {redact_apprise_url(bad)}",
            )
    if "metadata_provider" in fields and fields["metadata_provider"] not in ("tmdb", "omdb"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid metadata_provider: {fields['metadata_provider']!r} (must be 'tmdb' or 'omdb')",
        )
    for key, value in fields.items():
        setattr(cfg, key, value)
    cfg.updated_by_user_id = user.id
    cfg.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(cfg)
    return _to_view(cfg)
