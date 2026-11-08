"""Validate and apply operator writes to notification channels: creating one and patching one."""

from __future__ import annotations

from collections.abc import Collection
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status

from arm_backend.config import settings
from arm_backend.notification_dispatcher import (
    NOTABLE_EVENT_TYPES,
    _first_invalid_apprise_url,
    redact_apprise_url,
)
from arm_backend.notifications.bash_hook import HookError, patch_bash_config, secret_set, storage_config
from arm_backend.notifications.field_map import compose_url_from_fields, merge_patch_config
from arm_backend.notifications.inbox_listener import INBOX_CHANNEL_ID
from arm_common import NotificationChannel
from arm_common.schemas import NotificationChannelCreateRequest, NotificationChannelUpdateRequest


def _hook_422(exc: Exception) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


def _validate_template_inputs(templates: dict[str, Any], secret_keys: Collection[str]) -> None:
    """Per-event input overrides may not touch secret inputs."""
    for event, tmpl in templates.items():
        inputs = (tmpl or {}).get("inputs")
        bad = sorted(k for k in (inputs or {}) if k in secret_keys)
        if bad:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"secret inputs cannot be overridden per event ({event}: {', '.join(bad)})",
            )


def _templates_to_storage(templates: dict[str, Any]) -> dict[str, Any]:
    return {k: v.model_dump(exclude_none=True) for k, v in templates.items()}


def _validate_apprise_url(url: str) -> None:
    bad = _first_invalid_apprise_url([url])
    if bad is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"apprise rejected URL: {redact_apprise_url(bad)}",
        )


def _validate_events(events: list[str]) -> None:
    bad = [e for e in events if e not in NOTABLE_EVENT_TYPES]
    if bad:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"unknown event type(s): {', '.join(sorted(bad))}",
        )


def _validate_template_keys(templates: dict[str, Any]) -> None:
    bad = [k for k in templates if k not in NOTABLE_EVENT_TYPES]
    if bad:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"unknown template event type(s): {', '.join(sorted(bad))}",
        )


def _apprise_config_to_storage(config: dict[str, Any]) -> dict[str, Any]:
    """Compose url server-side when {service_id, fields} given and url empty."""
    out = dict(config)
    fields = out.get("fields") or {}
    service_id = out.get("service_id")
    if fields and service_id and not out.get("url"):
        composed = compose_url_from_fields(service_id, fields)
        if composed is not None:
            out["url"] = composed
    _validate_apprise_url(out.get("url", ""))
    return out


def _reject_inbox_config(ch: NotificationChannel, req: NotificationChannelUpdateRequest) -> None:
    if ch.id == INBOX_CHANNEL_ID and req.config is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="the in-app channel config is fixed; edit subscribed_events/enabled/name instead",
        )


def _validate_patch_keys(req: NotificationChannelUpdateRequest) -> None:
    fields = req.model_dump(exclude_unset=True)
    if "subscribed_events" in fields and fields["subscribed_events"] is not None:
        _validate_events(fields["subscribed_events"])
    if "templates" in fields and fields["templates"] is not None:
        _validate_template_keys(fields["templates"])


def _apply_plain_fields(ch: NotificationChannel, req: NotificationChannelUpdateRequest) -> None:
    if req.name is not None:
        ch.name = req.name
    if req.enabled is not None:
        ch.enabled = req.enabled
    if req.subscribed_events is not None:
        ch.subscribed_events = list(req.subscribed_events)


def _apply_bash_config_patch(ch: NotificationChannel, incoming: dict[str, Any]) -> None:
    if incoming.get("type") != "bash":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="a bash channel's config must have type 'bash'",
        )
    try:
        ch.config = patch_bash_config(ch.config or {}, incoming, settings.ARM_SCRIPTS_ROOT)
    except HookError as exc:
        raise _hook_422(exc) from exc


def _apply_apprise_config_patch(ch: NotificationChannel, incoming: dict[str, Any]) -> None:
    # A raw-url-only PATCH (no fields) stores the url directly; a fields
    # PATCH merges secrets + recomposes. Either way, validate the final
    # url so a config that resolves to an empty/invalid url is rejected
    # (422) rather than silently bricking the channel.
    # A client may round-trip the REDACTED url from GET (mask_config
    # returns scheme://****). Treat it like <hidden>: keep the stored url.
    if incoming.get("url") == redact_apprise_url(str((ch.config or {}).get("url") or "")):
        incoming = {**incoming, "url": (ch.config or {}).get("url")}
    if not incoming.get("fields") and incoming.get("url"):
        new_config = incoming
    else:
        new_config = merge_patch_config(ch.config or {}, incoming)
    _validate_apprise_url(new_config.get("url", ""))
    ch.config = new_config


def _apply_config_patch(ch: NotificationChannel, req: NotificationChannelUpdateRequest) -> None:
    if req.config is None:
        return
    incoming = req.config.model_dump(mode="json")
    if ch.type == "bash":
        _apply_bash_config_patch(ch, incoming)
    else:
        _apply_apprise_config_patch(ch, incoming)


def _apply_templates_patch(ch: NotificationChannel, req: NotificationChannelUpdateRequest) -> None:
    # After the config update: a PATCH that swaps the script re-stamps
    # secret_keys, and the per-event overrides are validated against the new set.
    if req.templates is None:
        return
    if ch.type == "bash":
        _validate_template_inputs(_templates_to_storage(req.templates), secret_set(ch.config or {}))
    ch.templates = _templates_to_storage(req.templates)


def apply_channel_patch(ch: NotificationChannel, req: NotificationChannelUpdateRequest) -> None:
    _reject_inbox_config(ch, req)
    _validate_patch_keys(req)
    _apply_plain_fields(ch, req)
    _apply_config_patch(ch, req)
    _apply_templates_patch(ch, req)
    ch.updated_at = datetime.now(UTC)


def new_channel(req: NotificationChannelCreateRequest, created_by_user_id: str) -> NotificationChannel:
    if req.type == "inapp":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="cannot create an inapp channel; the in-app bell (ncl_inbox) is system-managed",
        )
    _validate_events(req.subscribed_events)
    _validate_template_keys(req.templates)
    raw = req.config.model_dump(mode="json")
    if req.type == "bash":
        try:
            # Nothing is stored yet, so the request's secret_keys can only add
            # masking; keep them when the header cannot be read.
            config = storage_config(raw, settings.ARM_SCRIPTS_ROOT, fallback_secret_keys=raw.get("secret_keys") or [])
        except HookError as exc:
            raise _hook_422(exc) from exc
        _validate_template_inputs(_templates_to_storage(req.templates), config["secret_keys"])
    else:
        config = _apprise_config_to_storage(raw)
    return NotificationChannel(
        type=req.type,
        name=req.name,
        enabled=req.enabled,
        config=config,
        subscribed_events=list(req.subscribed_events),
        templates=_templates_to_storage(req.templates),
        created_by_user_id=created_by_user_id,
    )
