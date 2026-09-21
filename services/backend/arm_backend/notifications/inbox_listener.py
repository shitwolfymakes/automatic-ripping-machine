"""In-app inbox delivery as a notification listener.

Writes a `NotificationInbox` row for the UI bell when the seeded inapp
channel (`ncl_inbox`) is enabled and subscribed to the event type. A
local DB write — no external I/O. The inapp channel's per-event template
override is applied via the same `resolve_title_body` as apprise.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.notification_format import TemplateRenderError, context_from_message, resolve_title_body
from arm_backend.notifications.message import Message
from arm_common import NotificationChannel, NotificationInbox

logger = logging.getLogger("arm_backend.notifications.inbox_listener")

INBOX_CHANNEL_ID = "ncl_inbox"


class InboxListener:
    async def handle(self, db: AsyncSession, message: Message) -> None:
        channel = (
            await db.execute(select(NotificationChannel).where(col(NotificationChannel.id) == INBOX_CHANNEL_ID))
        ).scalar_one_or_none()
        if channel is None or not channel.enabled:
            return
        if message.event_type not in (channel.subscribed_events or []):
            return
        template = (channel.templates or {}).get(message.event_type)
        _ctx = context_from_message(
            event_type=message.event_type,
            job=message.job,
            job_id=message.job_id,
            payload=message.payload,
        )
        try:
            title, body = resolve_title_body(
                event_type=message.event_type,
                default_title=message.default_title,
                default_body=message.default_body,
                template=template,
                context=_ctx,
            )
        except TemplateRenderError as exc:
            logger.warning("template render failed: channel=%s %s", channel.id, exc)
            return
        db.add(
            NotificationInbox(
                event_id=message.event_id,
                channel_id=channel.id,
                event_type=message.event_type,
                title=title,
                message=body,
                job_id=message.job_id,
            )
        )
