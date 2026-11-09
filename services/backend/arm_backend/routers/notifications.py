"""Notification channels API.

The channel ``config`` is masked on every read (private apprise fields become
``<hidden>``; bash secret inputs, named by ``secret_keys``, become
``<hidden>`` too). Create composes the apprise URL server-side when the body carries
``{service_id, fields}``; otherwise a raw apprise URL is accepted and
validated. A ``bash`` channel runs a script from the scripts mount
(``script`` is a bare file name, validated against path traversal); its
``secret_keys`` are server-owned. They are stamped from the script header;
when the header cannot be read, a create keeps the request's list (it can only
add masking) and a PATCH keeps the stored list. On a PATCH, ``<hidden>`` on a
stored secret keeps the stored value and that key stays secret until the
client replaces it, even if the new header no longer declares it; ``<hidden>``
on a non-secret key is a literal. ``GET /scripts`` and
``GET /scripts/{name}`` list and inspect the scripts mount; ``POST
/scripts/preview`` resolves (and optionally runs) a bash hook for one event
with sample context, without persisting anything. Catalog, compose-url,
test-send, and dispatch-log endpoints are added in subsequent changes.

Note: only the per-field ``fields`` map is masked on read — the composed
``config['url']`` (which embeds the same credentials) is returned as-is.
URL-level redaction is intentionally deferred; the endpoints are
JWT-guarded.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, func, select

from arm_backend.auth import require_jwt, require_writer
from arm_backend.config import settings
from arm_backend.db import get_session
from arm_backend.notification_events import EVENT_VOCAB
from arm_backend.notification_format import TemplateRenderError, resolve_title_body
from arm_backend.notifications import catalog as catalog_module
from arm_backend.notifications.apprise_notifier import AppriseNotifier
from arm_backend.notifications.channel_edits import apply_channel_patch, new_channel
from arm_backend.notifications.bash_config import mask_bash_config, merge_bash_config
from arm_backend.notifications.bash_hook import (
    HookError,
    PreparedRun,
    masked,
    prepare_run,
    redact_secrets,
    secret_set,
)
from arm_backend.notifications.bash_runner import run_script
from arm_backend.notifications.inbox_listener import INBOX_CHANNEL_ID
from arm_backend.notifications.field_map import (
    compose_url_from_fields,
    mask_config,
    merge_patch_config,
)
from arm_backend.notifications.script_meta import (
    ScriptUnreadableError,
    list_scripts,
    read_script_info,
    validate_script_name,
)
from arm_backend.notifications.url_composer import compose_apprise_url
from arm_common import NotificationChannel, NotificationDispatchLog, NotificationInbox, User
from arm_common.schemas import (
    BashPreviewRequest,
    BashPreviewResult,
    BashScriptInfo,
    BashScriptSummary,
    ComposeUrlRequest,
    ComposeUrlResult,
    EventTypeInfo,
    NotificationChannelCreateRequest,
    NotificationChannelTestRequest,
    NotificationChannelUpdateRequest,
    NotificationChannelView,
    NotificationDispatchLogView,
    NotificationInboxCountView,
    NotificationInboxUpdateRequest,
    NotificationInboxView,
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
        "config": mask_bash_config(ch.config or {}) if ch.type == "bash" else mask_config(ch.config or {}),
        "subscribed_events": list(ch.subscribed_events or []),
        "templates": ch.templates or {},
        "last_fired_at": ch.last_fired_at,
        "last_success_at": ch.last_success_at,
        "last_error": ch.last_error,
        "created_by_user_id": ch.created_by_user_id,
        "created_at": ch.created_at,
        "updated_at": ch.updated_at,
    }


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
    user: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    ch = new_channel(req, user.id)
    db.add(ch)
    await db.commit()
    await db.refresh(ch)
    return _to_view_dict(ch)


@router.patch("/channels/{channel_id}", response_model=NotificationChannelView)
async def patch_channel(
    channel_id: str,
    req: NotificationChannelUpdateRequest,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    ch = (
        await db.execute(select(NotificationChannel).where(col(NotificationChannel.id) == channel_id))
    ).scalar_one_or_none()
    if ch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown channel_id: {channel_id}")
    apply_channel_patch(ch, req)
    await db.commit()
    await db.refresh(ch)
    return _to_view_dict(ch)


@router.delete("/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: str,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> None:
    ch = (
        await db.execute(select(NotificationChannel).where(col(NotificationChannel.id) == channel_id))
    ).scalar_one_or_none()
    if ch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown channel_id: {channel_id}")
    if channel_id == INBOX_CHANNEL_ID:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="cannot delete the system in-app notification channel",
        )
    await db.delete(ch)
    await db.commit()


@router.get("/services", response_model=ServiceCatalog)
async def get_services(_: User = Depends(require_jwt)) -> dict[str, Any]:
    return catalog_module.build_catalog()


@router.get("/scripts", response_model=list[BashScriptSummary])
async def get_scripts(_: User = Depends(require_writer)) -> list[BashScriptSummary]:
    return list_scripts(settings.ARM_SCRIPTS_ROOT)


def _prepare_sample(config: dict[str, Any], template: dict[str, Any] | None, event_type: str) -> PreparedRun:
    spec = EVENT_VOCAB.get(event_type)
    return prepare_run(
        config=config,
        template=template,
        event_type=event_type,
        default_title=spec.default_title if spec else "ARM: test notification",
        default_body=spec.default_body if spec else f"ARM test notification ({event_type})",
        context=_sample_context(event_type),
        scripts_root=settings.ARM_SCRIPTS_ROOT,
        media_root=settings.MEDIA_ROOT,
        raw_root=settings.RAW_ROOT,
    )


@router.post("/scripts/preview", response_model=BashPreviewResult)
async def preview_script(
    req: BashPreviewRequest,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> BashPreviewResult:
    config = req.config.model_dump(mode="json")
    # ``secret_keys`` is server-owned: a preview may never name its own secrets,
    # or stored values would be readable through the masked-input round-trip.
    config["secret_keys"] = []
    if req.channel_id is not None:
        ch = (
            await db.execute(select(NotificationChannel).where(col(NotificationChannel.id) == req.channel_id))
        ).scalar_one_or_none()
        if ch is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown channel_id: {req.channel_id}")
        if config.get("script") != (ch.config or {}).get("script"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="preview with channel_id must use the channel's stored script",
            )
        # Same script, so the carried keys are already in the stored set.
        config = merge_bash_config(ch.config or {}, config)[0]
        config["secret_keys"] = sorted(secret_set(ch.config or {}))
    template = req.template.model_dump(exclude_none=True) if req.template is not None else None
    try:
        run = _prepare_sample(config, template, req.event_type)
    except HookError as exc:
        return BashPreviewResult(title="", body="", inputs={}, env={}, argv=[], error=str(exc))
    inputs, env = masked(run)
    result = None
    if req.run:
        # The response must not undo the masking above: a script that echoes
        # a secret (curl -v, set -x) would hand it back in its output.
        result = await run_script(
            run.path,
            title=run.title,
            body=run.body,
            env=run.env,
            timeout_seconds=run.timeout_seconds,
            redact=lambda text: redact_secrets(text, run),
        )
    return BashPreviewResult(title=run.title, body=run.body, inputs=inputs, env=env, argv=run.argv, result=result)


@router.get("/scripts/{name}", response_model=BashScriptInfo)
async def get_script(name: str, _: User = Depends(require_writer)) -> BashScriptInfo:
    try:
        validate_script_name(name)
        return read_script_info(settings.ARM_SCRIPTS_ROOT, name)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown script: {name}") from exc
    except ScriptUnreadableError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"script is not readable: {exc}"
        ) from exc


@router.post("/services/{service_id}/compose-url", response_model=ComposeUrlResult)
async def compose_url(
    service_id: str,
    req: ComposeUrlRequest,
    _: User = Depends(require_jwt),
) -> dict[str, str]:
    return {"url": compose_apprise_url(service_id=service_id, required=req.required, advanced=req.advanced)}


@router.get("/event-types", response_model=list[EventTypeInfo])
async def event_types(_: User = Depends(require_jwt)) -> list[EventTypeInfo]:
    return [
        EventTypeInfo(
            key=key,
            label=spec.label,
            variables=list(spec.variables),
            default_title=spec.default_title,
            default_body=spec.default_body,
        )
        for key, spec in sorted(EVENT_VOCAB.items())
    ]


# Readable placeholder values for each variable name used in sample contexts.
_SAMPLE_VALUES: dict[str, str] = {
    "job_title": "Example Movie",
    "drive_id": "sr0",
    "tracks_done": "3",
    "tracks_total": "3",
    "tracks_failed": "0",
    "status": "ripped",
    "job_id": "job_example",
    "job_year": "2024",
    "job_disc_type": "dvd",
    "occurred_at": "2024-01-01T00:00:00+00:00",
    "volume_label": "EXAMPLE_DISC",
    "disc_type": "dvd",
    "session_id": "ses_example",
    "session_application_id": "sapp_example",
}


def _sample_context(event_type: str) -> dict[str, str]:
    """Build a flat string context for *event_type* from its declared variables.

    Every variable is filled with a readable placeholder so template renders
    never fail due to a missing key. The ``event_type`` variable is always set
    to the actual event type.
    """
    spec = EVENT_VOCAB.get(event_type)
    variables = spec.variables if spec is not None else ()
    ctx: dict[str, str] = {"event_type": event_type}
    for var in variables:
        if var not in ctx:
            ctx[var] = _SAMPLE_VALUES.get(var, f"<{var}>")
    return ctx


def _bash_send(
    config: dict[str, Any], template: dict[str, Any] | None, event_type: str
) -> Callable[[str, str], Awaitable[None]]:
    async def _send(_title: str, _body: str) -> None:
        run = _prepare_sample(config, template, event_type)
        result = await run_script(
            run.path,
            title=run.title,
            body=run.body,
            env=run.env,
            timeout_seconds=run.timeout_seconds,
            redact=lambda text: redact_secrets(text, run),
        )
        if not result.ok:
            raise RuntimeError(result.error or "")

    return _send


async def _send_and_log(
    *,
    db: AsyncSession,
    send: Callable[[str, str], Awaitable[None]],
    event_type: str,
    channel: NotificationChannel | None,
    template: dict[str, str | None] | None = None,
    detail_errors: bool,
) -> NotificationTestResult:
    spec = EVENT_VOCAB.get(event_type)
    default_title = spec.default_title if spec is not None else "ARM: test notification"
    default_body = spec.default_body if spec is not None else f"ARM test notification ({event_type})"
    ctx = _sample_context(event_type)
    try:
        title, body = resolve_title_body(
            event_type=event_type,
            default_title=default_title,
            default_body=default_body,
            template=template,
            context=ctx,
        )
    except TemplateRenderError as exc:
        return NotificationTestResult(ok=False, error=f"template error: {exc}")
    now = datetime.now(UTC)
    ok = True
    err: str | None = None
    try:
        await send(title, body)
    except Exception as exc:  # never 500 on a bad destination
        ok = False
        # A bash hook reports the real reason (the operator owns the script);
        # an apprise failure stays a fixed string so provider internals do not leak.
        err = str(exc) if detail_errors else "test send failed"
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
    return NotificationTestResult(ok=ok, error=None if ok else err)


@router.post("/channels/{channel_id}/test", response_model=NotificationTestResult)
async def test_channel(
    channel_id: str,
    req: NotificationChannelTestRequest,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
    notifier: AppriseNotifier = Depends(get_notifier),
) -> NotificationTestResult:
    ch = (
        await db.execute(select(NotificationChannel).where(col(NotificationChannel.id) == channel_id))
    ).scalar_one_or_none()
    if ch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown channel_id: {channel_id}")
    config = ch.config or {}
    event_type = req.event_type or (ch.subscribed_events or ["rip.completed"])[0]
    # Render using the channel's per-event template override (if any).
    raw_template = (ch.templates or {}).get(event_type)
    template: dict[str, str | None] | None = raw_template if isinstance(raw_template, dict) else None
    if ch.type == "bash":
        return await _send_and_log(
            db=db,
            send=_bash_send(config, template, event_type),
            event_type=event_type,
            channel=ch,
            template=template,
            detail_errors=True,
        )
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
    if not url:
        return NotificationTestResult(ok=False, error="could not compose url from fields")

    async def _send(t: str, b: str) -> None:
        await notifier.notify([url], t, b)

    return await _send_and_log(
        db=db, send=_send, event_type=event_type, channel=ch, template=template, detail_errors=False
    )


@router.post("/test", response_model=NotificationTestResult)
async def test_config(
    req: NotificationTestRequest,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
    notifier: AppriseNotifier = Depends(get_notifier),
) -> NotificationTestResult:
    config = req.config.model_dump(mode="json")
    event_type = req.event_type or "rip.completed"
    if config.get("type") == "bash":
        return await _send_and_log(
            db=db, send=_bash_send(config, None, event_type), event_type=event_type, channel=None, detail_errors=True
        )
    fields = config.get("fields") or {}
    service_id = config.get("service_id")
    url = config.get("url") or ""
    if not url and fields and service_id:
        composed = compose_url_from_fields(service_id, fields)
        if composed:
            url = composed
    if not url:
        return NotificationTestResult(ok=False, error="url is required")

    async def _send(t: str, b: str) -> None:
        await notifier.notify([url], t, b)

    return await _send_and_log(db=db, send=_send, event_type=event_type, channel=None, detail_errors=False)


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


@router.get("/inbox", response_model=list[NotificationInboxView])
async def list_inbox(
    include_cleared: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> list[NotificationInbox]:
    stmt = select(NotificationInbox).order_by(col(NotificationInbox.created_at).desc())
    if not include_cleared:
        stmt = stmt.where(col(NotificationInbox.cleared).is_(False))
    return list((await db.execute(stmt.limit(limit))).scalars().all())


@router.get("/inbox/count", response_model=NotificationInboxCountView)
async def inbox_count(
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
) -> NotificationInboxCountView:
    stmt = select(NotificationInbox.seen, NotificationInbox.cleared, func.count()).group_by(
        col(NotificationInbox.seen), col(NotificationInbox.cleared)
    )
    counts = {(bool(s), bool(c)): n for s, c, n in (await db.execute(stmt)).all()}
    cleared = counts.get((True, True), 0) + counts.get((False, True), 0)
    unseen = counts.get((False, False), 0)
    seen = counts.get((True, False), 0)
    return NotificationInboxCountView(unseen=unseen, seen=seen, cleared=cleared, total=cleared + unseen + seen)


@router.post("/inbox/dismiss-all")
async def inbox_dismiss_all(
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    # Same effect as dismissing each row (PATCH seen + cleared), so dismissed
    # rows leave the inbox and become purgeable either way.
    stmt = select(NotificationInbox).where(col(NotificationInbox.cleared).is_(False))
    rows = list((await db.execute(stmt)).scalars().all())
    now = datetime.now(UTC)
    updated = 0
    for r in rows:
        if not r.seen:
            r.seen = True
            r.seen_at = now
        r.cleared = True
        r.cleared_at = now
        updated += 1
    await db.commit()
    return {"updated": updated}


@router.post("/inbox/purge")
async def inbox_purge(
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    stmt = select(NotificationInbox).where(col(NotificationInbox.cleared).is_(True))
    rows = list((await db.execute(stmt)).scalars().all())
    for r in rows:
        await db.delete(r)
    deleted = len(rows)
    await db.commit()
    return {"deleted": deleted}


@router.patch("/inbox/{inbox_id}", response_model=NotificationInboxView)
async def patch_inbox(
    inbox_id: str,
    req: NotificationInboxUpdateRequest,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> NotificationInbox:
    row = (
        await db.execute(select(NotificationInbox).where(col(NotificationInbox.id) == inbox_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown inbox_id: {inbox_id}")
    now = datetime.now(UTC)
    if req.seen is not None:
        row.seen = req.seen
        row.seen_at = now if req.seen else None
    if req.cleared is not None:
        row.cleared = req.cleared
        row.cleared_at = now if req.cleared else None
    await db.commit()
    await db.refresh(row)
    return row
