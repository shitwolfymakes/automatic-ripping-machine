"""Apprise delivery as a notification listener.

For each enabled apprise channel subscribed to the event type, apply the
channel's per-event template override, fire the apprise URL, record
per-channel outcome (`last_*`), and write a dispatch-log row. Per-channel failures are
isolated; failure logs the REDACTED url.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from arm_backend.notification_format import TemplateRenderError, context_from_message, resolve_title_body
from arm_backend.notifications.apprise_notifier import AppriseNotifier
from arm_backend.notifications.delivery import record_outcome, select_channels
from arm_backend.notifications.message import Message
from arm_backend.notifications.url_composer import redact_apprise_url

logger = logging.getLogger("arm_backend.notifications.apprise_listener")


class AppriseListener:
    def __init__(self, notifier: AppriseNotifier) -> None:
        self._notifier = notifier

    async def handle(self, db: AsyncSession, message: Message) -> None:
        if not message.apprise_enabled:
            # Global notifications toggle is off: external delivery is gated
            # here (the inbox listener still runs — see Message.apprise_enabled).
            return
        targets = await select_channels(db, "apprise", message.event_type)
        _ctx = context_from_message(
            event_type=message.event_type,
            job=message.job,
            job_id=message.job_id,
            payload=message.payload,
        )
        for channel in targets:
            url = (channel.config or {}).get("url", "")
            template = (channel.templates or {}).get(message.event_type)
            try:
                title, body = resolve_title_body(
                    event_type=message.event_type,
                    default_title=message.default_title,
                    default_body=message.default_body,
                    template=template,
                    context=_ctx,
                )
            except TemplateRenderError as exc:
                record_outcome(db, channel, message, fired_at=datetime.now(UTC), title="", body="", error=str(exc))
                logger.warning("template render failed: channel=%s %s", channel.id, exc)
                continue
            fire_now = datetime.now(UTC)
            err: str | None = None
            try:
                await self._notifier.notify([url], title, body)
            except Exception as exc:
                err = str(exc)
                logger.exception(
                    "notification failed: event_id=%s channel=%s url=%s",
                    message.event_id,
                    channel.id,
                    redact_apprise_url(url),
                )
            record_outcome(db, channel, message, fired_at=fire_now, title=title, body=body, error=err)
