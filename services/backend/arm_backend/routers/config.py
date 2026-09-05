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
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt, require_writer
from arm_backend.config import settings
from arm_backend.db import get_session
from arm_backend.makemkv_status import makemkv_state_detail
from arm_backend.seeders import CONFIG_SINGLETON_ID
from arm_common import Config, Job, JobStatus, User
from arm_common.config_metadata import CONFIG_FIELD_META
from arm_common.schemas import ConfigUpdateRequest, ConfigView, KeyCheckRequest, KeyCheckResponse
from arm_common.secrets import HIDDEN_SECRET

_KEY_CHECK_TIMEOUT_SECONDS = 10.0

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
        # `bool(...)` coerces the None a bare in-memory Config carries (these
        # columns' server_default is DB-level only) to False, so _to_view works
        # for rows/fixtures predating them. The sibling bools above predate their
        # consumers' fixtures, so they don't need it.
        community_keydb_enabled=bool(cfg.community_keydb_enabled),
        makemkv_sdf_enabled=bool(cfg.makemkv_sdf_enabled),
        thediscdb_enabled=bool(cfg.thediscdb_enabled),
        thediscdb_refresh_days=int(cfg.thediscdb_refresh_days) if cfg.thediscdb_refresh_days is not None else 7,
        ripping_paused=bool(cfg.ripping_paused),
        # bool()/int() coerce the None a bare in-memory Config carries (DB-level
        # server_default only) for rows/fixtures predating these columns.
        hold_for_review=bool(cfg.hold_for_review),
        manual_wait_seconds=int(cfg.manual_wait_seconds) if cfg.manual_wait_seconds is not None else 60,
        drive_scan_interval_seconds=int(cfg.drive_scan_interval_seconds or 30),
        drive_detected_prune_days=int(cfg.drive_detected_prune_days or 7),
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
    user: User = Depends(require_writer),
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
    if "metadata_provider" in fields and fields["metadata_provider"] not in ("tmdb", "omdb"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid metadata_provider: {fields['metadata_provider']!r} (must be 'tmdb' or 'omdb')",
        )
    for key in ("drive_scan_interval_seconds", "drive_detected_prune_days"):
        if key in fields and (fields[key] is None or fields[key] < 1):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} must be a positive integer")
    # Detect un-pause (ripping_paused ON -> OFF) before applying, so we can give
    # held review-gate discs a FRESH countdown rather than resuming an already-
    # expired one (which would auto-rip the instant ripping resumes — surprising
    # to an operator who paused to deal with it later). timed-review-gate spec §6.3.
    unpausing = bool(cfg.ripping_paused) and fields.get("ripping_paused") is False

    for key, value in fields.items():
        setattr(cfg, key, value)
    cfg.updated_by_user_id = user.id
    cfg.updated_at = datetime.now(timezone.utc)

    if unpausing:
        now = datetime.now(timezone.utc)
        held = (await session.execute(select(Job).where(col(Job.status) == JobStatus.AWAITING_REVIEW))).scalars().all()
        for job in held:
            job.wait_start_time = now
            session.add(job)

    await session.commit()
    await session.refresh(cfg)
    return _to_view(cfg)


_KEY_ATTR = {"tmdb": "tmdb_api_key", "omdb": "omdb_api_key", "tvdb": "tvdb_api_key", "makemkv": "makemkv_key"}


async def _check_tmdb(http: httpx.AsyncClient, key: str) -> tuple[Literal["ok", "invalid", "error"], str | None]:
    headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
    try:
        r = await http.get(
            f"{settings.ARM_TMDB_BASE_URL}/configuration", headers=headers, timeout=_KEY_CHECK_TIMEOUT_SECONDS
        )
    except httpx.HTTPError as exc:
        return "error", str(exc)
    if r.status_code == 200:
        return "ok", None
    if r.status_code == 401:
        return "invalid", "TMDb rejected the key"
    return "error", f"tmdb status={r.status_code}"


async def _check_omdb(http: httpx.AsyncClient, key: str) -> tuple[Literal["ok", "invalid", "error"], str | None]:
    try:
        r = await http.get(
            settings.ARM_OMDB_BASE_URL,
            params={"apikey": key, "i": "tt0111161"},
            timeout=_KEY_CHECK_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        return "error", str(exc)
    if r.status_code == 401:
        return "invalid", "OMDb rejected the key"
    if r.status_code != 200:
        return "error", f"omdb status={r.status_code}"
    try:
        body = r.json()
    except ValueError as exc:
        return "error", f"omdb returned a non-JSON response: {exc}"
    if body.get("Response") == "True":
        return "ok", None
    if body.get("Response") == "False":
        return "invalid", body.get("Error", "omdb rejected the key")
    return "error", "omdb returned an unexpected response"


async def _check_tvdb(http: httpx.AsyncClient, key: str) -> tuple[Literal["ok", "invalid", "error"], str | None]:
    try:
        r = await http.post(
            f"{settings.ARM_TVDB_BASE_URL}/login",
            json={"apikey": key},
            timeout=_KEY_CHECK_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        return "error", str(exc)
    if r.status_code == 200:
        return "ok", None
    if r.status_code == 401:
        return "invalid", "TVDB rejected the key"
    return "error", f"tvdb status={r.status_code}"


@router.post("/keys/{name}/check", response_model=KeyCheckResponse)
async def check_key(
    name: Literal["tmdb", "omdb", "tvdb", "makemkv"],
    body: KeyCheckRequest,
    request: Request,
    _: User = Depends(require_writer),
    session: AsyncSession = Depends(get_session),
) -> KeyCheckResponse:
    cfg = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="config singleton missing")

    stored_key = getattr(cfg, _KEY_ATTR[name]) or ""
    unsaved_value = body.value if isinstance(body.value, str) and body.value else None

    if name == "makemkv":
        if unsaved_value is not None and unsaved_value != stored_key:
            return KeyCheckResponse(
                name=name,
                status="unknown",
                detail="save the key; the ripper verifies it before the next rip",
                checked_at=None,
            )
        if not stored_key:
            return KeyCheckResponse(name=name, status="missing", detail="no key set", checked_at=None)
        if cfg.makemkv_key_valid is True:
            return KeyCheckResponse(name=name, status="ok", detail=None, checked_at=cfg.makemkv_key_checked_at)
        if cfg.makemkv_key_valid is False:
            return KeyCheckResponse(
                name=name,
                status="invalid",
                detail=makemkv_state_detail(cfg.makemkv_key_state),
                checked_at=cfg.makemkv_key_checked_at,
            )
        detail = "probe failed" if cfg.makemkv_key_state == "probe_failed" else "not checked yet"
        return KeyCheckResponse(name=name, status="unknown", detail=detail, checked_at=cfg.makemkv_key_checked_at)

    key = unsaved_value or stored_key
    if not key:
        return KeyCheckResponse(name=name, status="missing", detail="no key set", checked_at=None)

    http: httpx.AsyncClient = request.app.state.http
    if name == "tmdb":
        check_status, check_detail = await _check_tmdb(http, key)
    elif name == "omdb":
        check_status, check_detail = await _check_omdb(http, key)
    else:
        check_status, check_detail = await _check_tvdb(http, key)
    return KeyCheckResponse(name=name, status=check_status, detail=check_detail, checked_at=datetime.now(timezone.utc))
