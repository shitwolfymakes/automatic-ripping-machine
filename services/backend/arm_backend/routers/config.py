"""UI-side config read/write. Never wire-exposes `session_signing_key`.

`notification_apprise_urls` round-trips by value but never appears in log
output — the validation helper redacts the URL in any 400 response, and
the handler itself logs nothing about config bodies. The
`notifications_enabled` master toggle (default False) lets the UI enable
or disable outbound Apprise dispatch without dropping the saved URL list.

`notification_apprise_urls` is DEPRECATED as a delivery source — the
dispatcher reads `notification_channels` rows. The field is still
accepted/returned here for backward compatibility but is not used for
dispatch; `notifications_enabled` remains the global
master toggle. New URLs should be added as channels via /api/notifications.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt, require_writer
from arm_backend.config import effective_transcode_capable, settings
from arm_backend.config_effects import reresolve_identity, redrain_parked_applications
from arm_backend.config_validation import reject_non_editable_keys, validate_config_update
from arm_backend.db import get_session
from arm_backend.identity.sources.registry import (
    crc64service_enabled,
    episode_auto_apply,
    episode_sources_setting,
    episode_tolerance,
    hint_sources_setting,
    movie_auto_apply,
    movie_sources_setting,
    music_auto_apply,
    music_sources_setting,
    search_provider_setting,
)
from arm_backend.key_checks import check_online_key, makemkv_key_status
from arm_backend.constants import CONFIG_SINGLETON_ID
from arm_common import Config, Job, JobStatus, User
from arm_common.config_metadata import CONFIG_FIELD_META
from arm_common.enums import PreviouslyRippedAction
from arm_common.schemas import (
    ConfigUpdateRequest,
    ConfigView,
    KeyCheckRequest,
    KeyCheckResponse,
    identity_suggestion_of,
    previously_ripped_job_id,
)
from arm_common.secrets import HIDDEN_SECRET

router = APIRouter(prefix="/api/config", tags=["config"])

logger = logging.getLogger("arm_backend.routers.config")

# Secret-tier config fields, derived from the registry so a future secret field
# auto-masks. The `& ConfigView.model_fields` guard keeps masking aligned to what's
# actually exposed: e.g. when tvdb_api_key gains its registry+ConfigView entry,
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
        episode_sources=list(episode_sources_setting(cfg)),
        disc_hint_sources=list(hint_sources_setting(cfg)),
        episode_match_tolerance_seconds=episode_tolerance(cfg),
        episode_auto_apply=episode_auto_apply(cfg),
        ripping_paused=bool(cfg.ripping_paused),
        # bool()/int() coerce the None a bare in-memory Config carries (DB-level
        # server_default only) for rows/fixtures predating these columns.
        hold_for_review=bool(cfg.hold_for_review),
        manual_wait_seconds=int(cfg.manual_wait_seconds) if cfg.manual_wait_seconds is not None else 60,
        on_previously_ripped=cfg.on_previously_ripped or PreviouslyRippedAction.HOLD,
        drive_scan_interval_seconds=int(cfg.drive_scan_interval_seconds or 30),
        drive_detected_prune_days=int(cfg.drive_detected_prune_days or 7),
        # NULL falls back to the env value, exactly as the dispatcher does.
        max_parallel_transcodes=int(cfg.max_parallel_transcodes)
        if cfg.max_parallel_transcodes is not None
        else settings.MAX_PARALLEL_TRANSCODES,
        max_parallel_iso_rips=int(cfg.max_parallel_iso_rips or 1),
        # None-coerce covers rows/fixtures predating the column (NULL = enabled).
        # A deployment that cannot transcode reports disabled, as every
        # enforcement point already treats it.
        transcode_enabled=effective_transcode_capable(settings) and cfg.transcode_enabled is not False,
        transcode_capable=effective_transcode_capable(settings),
        default_retention_policy=cfg.default_retention_policy,
        notification_apprise_urls=list(cfg.notification_apprise_urls or []),
        notifications_enabled=cfg.notifications_enabled,
        movie_sources=list(movie_sources_setting(cfg)),
        music_sources=list(music_sources_setting(cfg)),
        search_provider_movie=search_provider_setting(cfg, "movie"),
        search_provider_tv=search_provider_setting(cfg, "tv"),
        search_provider_music=search_provider_setting(cfg, "music"),
        movie_auto_apply=movie_auto_apply(cfg),
        music_auto_apply=music_auto_apply(cfg),
        crc64service_enabled=crc64service_enabled(cfg),
        makemkv_key_valid=cfg.makemkv_key_valid,
        makemkv_key_state=cfg.makemkv_key_state,
        makemkv_key_checked_at=cfg.makemkv_key_checked_at,
        makemkv_key_checked_by_drive_id=cfg.makemkv_key_checked_by_drive_id,
        updated_by_user_id=cfg.updated_by_user_id,
        updated_at=cfg.updated_at,
    )
    for key in _SECRET_KEYS:
        if getattr(view, key):  # non-empty stored secret → mask; None/"" stays as-is
            setattr(view, key, HIDDEN_SECRET)
    return view


async def _load_config(session: AsyncSession) -> Config:
    cfg = (await session.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
    if cfg is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="config singleton missing")
    return cfg


@router.get("", response_model=ConfigView)
async def get_config(
    _: User = Depends(require_jwt),
    session: AsyncSession = Depends(get_session),
) -> ConfigView:
    return _to_view(await _load_config(session))


def _drop_masked_secrets(fields: dict[str, Any]) -> None:
    # A secret field whose submitted value is the masked sentinel means "keep the
    # stored secret" — drop it from the update set so it isn't overwritten with the
    # literal "<hidden>". Real values update; "" / None clears (normal setattr below).
    for key in _SECRET_KEYS:
        if fields.get(key) == HIDDEN_SECRET:
            del fields[key]


def _require_transcode_capable(fields: dict[str, Any]) -> None:
    if fields.get("transcode_enabled") is True and not effective_transcode_capable(settings):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="cannot enable transcoding: this deployment is ripper-only "
            "(ARM_TRANSCODE_CAPABLE=false and no ARM_TRANSCODE_DOCKER_HOST)",
        )


def _is_unpausing(cfg: Config, fields: dict[str, Any]) -> bool:
    # Detect un-pause (ripping_paused ON -> OFF) before applying, so we can give
    # held review-gate discs a FRESH countdown rather than resuming an already-
    # expired one (which would auto-rip the instant ripping resumes — surprising
    # to an operator who paused to deal with it later).
    return bool(cfg.ripping_paused) and fields.get("ripping_paused") is False


def _is_reenabling_transcode(cfg: Config, fields: dict[str, Any]) -> bool:
    # Detect transcoding re-enable (OFF -> ON). A NULL column reads as enabled,
    # so only an explicit False counts as "was off". Encode applications that
    # reached the parked-application drain while the toggle was off stayed
    # WAITING_IDENTIFY; they're re-drained after the commit.
    return cfg.transcode_enabled is False and fields.get("transcode_enabled") is True


def _identity_sources_changed(cfg: Config, fields: dict[str, Any]) -> bool:
    # Which sources may contribute to a job's identity changed: the resolver
    # only consults the setting when it runs, so re-run it for live jobs
    # after the commit or a disabled source's fields stay on them.
    return any(key in fields and fields[key] != getattr(cfg, key) for key in _IDENTITY_SOURCE_KEYS)


def _makemkv_key_changed(cfg: Config, fields: dict[str, Any]) -> bool:
    # A ripper's verdict belongs to the key it checked. A new key has none
    # until a ripper checks it, so the old one must not be read as its own.
    return "makemkv_key" in fields and fields["makemkv_key"] != cfg.makemkv_key


def _apply_update(cfg: Config, fields: dict[str, Any], user: User, makemkv_key_changed: bool) -> None:
    for key, value in fields.items():
        setattr(cfg, key, value)
    if makemkv_key_changed:
        cfg.makemkv_key_valid = None
        cfg.makemkv_key_state = None
        cfg.makemkv_key_checked_at = None
        cfg.makemkv_key_checked_by_drive_id = None
    cfg.updated_by_user_id = user.id
    cfg.updated_at = datetime.now(timezone.utc)


async def _restart_held_countdowns(session: AsyncSession) -> None:
    now = datetime.now(timezone.utc)
    held = (await session.execute(select(Job).where(col(Job.status) == JobStatus.AWAITING_REVIEW))).scalars().all()
    for job in held:
        # A previously-ripped hold and a held suggestion have no countdown to restart.
        if (
            previously_ripped_job_id(job.metadata_json) is not None
            or identity_suggestion_of(job.metadata_json) is not None
        ):
            continue
        job.wait_start_time = now
        session.add(job)


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
    reject_non_editable_keys(raw)
    cfg = await _load_config(session)
    fields = req.model_dump(exclude_unset=True)
    _drop_masked_secrets(fields)
    validate_config_update(fields, raw, cfg)
    _require_transcode_capable(fields)

    unpausing = _is_unpausing(cfg, fields)
    reenabling_transcode = _is_reenabling_transcode(cfg, fields)
    identity_sources_changed = _identity_sources_changed(cfg, fields)
    makemkv_key_changed = _makemkv_key_changed(cfg, fields)

    _apply_update(cfg, fields, user, makemkv_key_changed)
    if unpausing:
        await _restart_held_countdowns(session)

    await session.commit()
    await session.refresh(cfg)
    view = _to_view(cfg)
    if reenabling_transcode:
        await redrain_parked_applications(session, getattr(request.app.state, "ws_hub", None))
    if identity_sources_changed:
        await reresolve_identity(
            session, getattr(request.app.state, "ws_hub", None), getattr(request.app.state, "episode_stage", None)
        )
    return view


# Settings that pick which identity sources run (and so which stored claims
# the resolver applies).
_IDENTITY_SOURCE_KEYS = ("episode_sources", "disc_hint_sources", "movie_sources", "music_sources")


_KEY_ATTR = {"tmdb": "tmdb_api_key", "omdb": "omdb_api_key", "tvdb": "tvdb_api_key", "makemkv": "makemkv_key"}


@router.post("/keys/{name}/check", response_model=KeyCheckResponse)
async def check_key(
    name: Literal["tmdb", "omdb", "tvdb", "makemkv"],
    body: KeyCheckRequest,
    request: Request,
    _: User = Depends(require_writer),
    session: AsyncSession = Depends(get_session),
) -> KeyCheckResponse:
    cfg = await _load_config(session)

    stored_key = getattr(cfg, _KEY_ATTR[name]) or ""
    unsaved_value = body.value if isinstance(body.value, str) and body.value else None

    if name == "makemkv":
        return makemkv_key_status(cfg, stored_key, unsaved_value)

    key = unsaved_value or stored_key
    if not key:
        return KeyCheckResponse(name=name, status="missing", detail="no key set", checked_at=None)

    http: httpx.AsyncClient = request.app.state.http
    check_status, check_detail = await check_online_key(http, name, key)
    return KeyCheckResponse(name=name, status=check_status, detail=check_detail, checked_at=datetime.now(timezone.utc))
