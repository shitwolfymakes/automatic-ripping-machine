"""Apprise delivery as a notification listener.

Extracted verbatim from the old `NotificationDispatcher._tick`: for each
enabled apprise channel subscribed to the event type, apply the channel's
per-event template override, fire the apprise URL, record per-channel
outcome (`last_*`), and write a dispatch-log row. Per-channel failures are
isolated; failure logs the REDACTED url.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from arm_backend.notification_dispatcher import AppriseNotifier, redact_apprise_url
from arm_backend.notification_format import resolve_title_body
from arm_backend.notifications.message import Message
from arm_common import NotificationChannel, NotificationDispatchLog

logger = logging.getLogger("arm_backend.notifications.apprise_listener")


class AppriseListener:
    def __init__(self, notifier: AppriseNotifier) -> None:
        self._notifier = notifier

    async def handle(self, db: AsyncSession, message: Message) -> None:
        channels = (await db.execute(select(NotificationChannel))).scalars().all()
        targets = [
            c
            for c in channels
            if c.enabled and c.type == "apprise" and message.event_type in (c.subscribed_events or [])
        ]
        for channel in targets:
            url = (channel.config or {}).get("url", "")
            template = (channel.templates or {}).get(message.event_type)
            title, body = resolve_title_body(
                event_type=message.event_type,
                default_title=message.default_title,
                default_body=message.default_body,
                template=template,
            )
            fire_now = datetime.now(UTC)
            ok = True
            err: str | None = None
            try:
                await self._notifier.notify([url], title, body)
            except Exception as exc:
                ok = False
                err = str(exc)
                logger.exception(
                    "notification failed: event_id=%s channel=%s url=%s",
                    message.event_id,
                    channel.id,
                    redact_apprise_url(url),
                )
            channel.last_fired_at = fire_now
            if ok:
                channel.last_success_at = fire_now
                channel.last_error = None
            else:
                channel.last_error = err
            db.add(
                NotificationDispatchLog(
                    channel_id=channel.id,
                    event_id=message.event_id,
                    event_type=message.event_type,
                    title=title,
                    body=body,
                    success=ok,
                    error=err,
                )
            )
