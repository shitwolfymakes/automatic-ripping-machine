"""Notification channels API.

The channel ``config`` is masked on every read (private apprise fields →
``<hidden>``). Create composes the apprise URL server-side when the body
carries ``{service_id, fields}``; otherwise a raw apprise URL is accepted
and validated. Catalog, compose-url, test-send, and dispatch-log
endpoints are added in subsequent changes.

Note: only the per-field ``fields`` map is masked on read — the composed
``config['url']`` (which embeds the same credentials) is returned as-is.
URL-level redaction is intentionally deferred; the endpoints are
JWT-guarded.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt
from arm_backend.db import get_session
from arm_backend.notification_dispatcher import (
    NOTIFIABLE_EVENT_TYPES,
    AppriseNotifier,
    _first_invalid_apprise_url,
    redact_apprise_url,
)
from arm_backend.notification_format import synthetic_test_message
from arm_backend.notifications import catalog as catalog_module
from arm_backend.notifications.field_map import (
    compose_url_from_fields,
    mask_config,
    merge_patch_config,
)
from arm_backend.notifications.url_composer import compose_apprise_url
from arm_common import NotificationChannel, NotificationDispatchLog, User
from arm_common.schemas import (
    ComposeUrlRequest,
    ComposeUrlResult,
    NotificationChannelCreateRequest,
    NotificationChannelTestRequest,
    NotificationChannelUpdateRequest,
    NotificationChannelView,
    NotificationDispatchLogView,
    NotificationTestRequest,
    NotificationTestResult,
    ServiceCatalog,
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def get_notifier(request: Request) -> AppriseNotifier:
    notifier: AppriseNotifier = request.app.state.notifier
    return notifier


def _to_view_dict(ch: NotificationChannel) -> dict[str, Any]:
    return {
        "id": ch.id,
        "type": ch.type,
        "name": ch.name,
        "enabled": ch.enabled,
        "config": mask_config(ch.config or {}),
        "subscribed_events": list(ch.subscribed_events or []),
        "templates": ch.templates or {},
        "last_fired_at": ch.last_fired_at,
        "last_success_at": ch.last_success_at,
        "last_error": ch.last_error,
        "created_by_user_id": ch.created_by_user_id,
        "created_at": ch.created_at,
        "updated_at": ch.updated_at,
    }


def _validate_apprise_url(url: str) -> None:
    bad = _first_invalid_apprise_url([url])
    if bad is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"apprise rejected URL: {redact_apprise_url(bad)}",
        )


def _validate_events(events: list[str]) -> None:
    bad = [e for e in events if e not in NOTIFIABLE_EVENT_TYPES]
    if bad:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"unknown event type(s): {', '.join(sorted(bad))}",
        )


def _validate_template_keys(templates: dict[str, Any]) -> None:
    bad = [k for k in templates if k not in NOTIFIABLE_EVENT_TYPES]
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


@router.get("/channels", response_model=list[NotificationChannelView])
async def list_channels(
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    rows = (
        (await db.execute(select(NotificationChannel).order_by(col(NotificationChannel.created_at).desc())))
        .scalars()
        .all()
    )
    return [_to_view_dict(r) for r in rows]


@router.get("/channels/{channel_id}", response_model=NotificationChannelView)
async def get_channel(
    channel_id: str,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    ch = (
        await db.execute(select(NotificationChannel).where(col(NotificationChannel.id) == channel_id))
    ).scalar_one_or_none()
    if ch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown channel_id: {channel_id}")
    return _to_view_dict(ch)


@router.post("/channels", response_model=NotificationChannelView, status_code=status.HTTP_201_CREATED)
async def create_channel(
    req: NotificationChannelCreateRequest,
    user: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _validate_events(req.subscribed_events)
    _validate_template_keys(req.templates)
    config = _apprise_config_to_storage(req.config.model_dump(mode="json"))
    ch = NotificationChannel(
        type=req.type,
        name=req.name,
        enabled=req.enabled,
        config=config,
        subscribed_events=list(req.subscribed_events),
        templates={k: v.model_dump(exclude_none=True) for k, v in req.templates.items()},
        created_by_user_id=user.id,
    )
    db.add(ch)
    await db.commit()
    await db.refresh(ch)
    return _to_view_dict(ch)


@router.patch("/channels/{channel_id}", response_model=NotificationChannelView)
async def patch_channel(
    channel_id: str,
    req: NotificationChannelUpdateRequest,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    ch = (
        await db.execute(select(NotificationChannel).where(col(NotificationChannel.id) == channel_id))
    ).scalar_one_or_none()
    if ch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown channel_id: {channel_id}")

    fields = req.model_dump(exclude_unset=True)
    if "subscribed_events" in fields and fields["subscribed_events"] is not None:
        _validate_events(fields["subscribed_events"])
    if "templates" in fields and fields["templates"] is not None:
        _validate_template_keys(fields["templates"])

    if req.name is not None:
        ch.name = req.name
    if req.enabled is not None:
        ch.enabled = req.enabled
    if req.subscribed_events is not None:
        ch.subscribed_events = list(req.subscribed_events)
    if req.templates is not None:
        ch.templates = {k: v.model_dump(exclude_none=True) for k, v in req.templates.items()}
    if req.config is not None:
        incoming = req.config.model_dump(mode="json")
        # A raw-url-only PATCH (no fields) stores the url directly; a fields
        # PATCH merges secrets + recomposes. Either way, validate the final
        # url so a config that resolves to an empty/invalid url is rejected
        # (422) rather than silently bricking the channel.
        if not incoming.get("fields") and incoming.get("url"):
            new_config = incoming
        else:
            new_config = merge_patch_config(ch.config or {}, incoming)
        _validate_apprise_url(new_config.get("url", ""))
        ch.config = new_config
    ch.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(ch)
    return _to_view_dict(ch)


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: str,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> None:
    ch = (
        await db.execute(select(NotificationChannel).where(col(NotificationChannel.id) == channel_id))
    ).scalar_one_or_none()
    if ch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown channel_id: {channel_id}")
    await db.delete(ch)
    await db.commit()


@router.get("/services", response_model=ServiceCatalog)
async def get_services(_: User = Depends(require_jwt)) -> dict[str, Any]:
    return catalog_module.build_catalog()


@router.post("/services/{service_id}/compose-url", response_model=ComposeUrlResult)
async def compose_url(
    service_id: str,
    req: ComposeUrlRequest,
    _: User = Depends(require_jwt),
) -> dict[str, str]:
    return {"url": compose_apprise_url(service_id=service_id, required=req.required, advanced=req.advanced)}


@router.get("/event-types", response_model=list[str])
async def event_types(_: User = Depends(require_jwt)) -> list[str]:
    return sorted(NOTIFIABLE_EVENT_TYPES)


async def _send_and_log(
    *,
    db: AsyncSession,
    notifier: AppriseNotifier,
    url: str,
    event_type: str,
    channel: NotificationChannel | None,
) -> NotificationTestResult:
    title, body = synthetic_test_message(event_type)
    now = datetime.now(UTC)
    ok = True
    err: str | None = None
    try:
        await notifier.notify([url], title, body)
    except Exception as exc:  # never 500 on a bad destination
        ok = False
        err = str(exc)
    if channel is not None:
        channel.last_fired_at = now
        if ok:
            channel.last_success_at = now
            channel.last_error = None
        else:
            channel.last_error = err
    db.add(
        NotificationDispatchLog(
            channel_id=channel.id if channel is not None else None,
            event_id=None,
            event_type=event_type,
            title=title,
            body=body,
            success=ok,
            error=err,
        )
    )
    await db.commit()
    return NotificationTestResult(ok=ok, error=None if ok else "test send failed")


@router.post("/channels/{channel_id}/test", response_model=NotificationTestResult)
async def test_channel(
    channel_id: str,
    req: NotificationChannelTestRequest,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
    notifier: AppriseNotifier = Depends(get_notifier),
) -> NotificationTestResult:
    ch = (
        await db.execute(select(NotificationChannel).where(col(NotificationChannel.id) == channel_id))
    ).scalar_one_or_none()
    if ch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown channel_id: {channel_id}")
    config = ch.config or {}
    # If the editor re-entered fields, merge them in to test the new url.
    # A raw-URL channel (no service_id — e.g. migration-imported) can't
    # recompose, so merge_patch_config leaves the url unchanged and the
    # re-entered fields are effectively ignored (the stored url is tested).
    if req.fields:
        merged = merge_patch_config(
            config, {"type": "apprise", "service_id": config.get("service_id"), "fields": req.fields}
        )
        url = merged.get("url", "")
    else:
        url = config.get("url", "")
    event_type = req.event_type or (ch.subscribed_events or ["rip.completed"])[0]
    if not url:
        return NotificationTestResult(ok=False, error="could not compose url from fields")
    return await _send_and_log(db=db, notifier=notifier, url=url, event_type=event_type, channel=ch)


@router.post("/test", response_model=NotificationTestResult)
async def test_config(
    req: NotificationTestRequest,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
    notifier: AppriseNotifier = Depends(get_notifier),
) -> NotificationTestResult:
    config = req.config.model_dump(mode="json")
    fields = config.get("fields") or {}
    service_id = config.get("service_id")
    url = config.get("url") or ""
    if not url and fields and service_id:
        composed = compose_url_from_fields(service_id, fields)
        if composed:
            url = composed
    if not url:
        return NotificationTestResult(ok=False, error="url is required")
    event_type = req.event_type or "rip.completed"
    return await _send_and_log(db=db, notifier=notifier, url=url, event_type=event_type, channel=None)


@router.get("/dispatch-log", response_model=list[NotificationDispatchLogView])
async def dispatch_log(
    channel_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> list[NotificationDispatchLog]:
    stmt = select(NotificationDispatchLog).order_by(col(NotificationDispatchLog.created_at).desc())
    if channel_id is not None:
        stmt = stmt.where(col(NotificationDispatchLog.channel_id) == channel_id)
    stmt = stmt.limit(limit)
    return list((await db.execute(stmt)).scalars().all())
