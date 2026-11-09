"""Bookkeeping shared by the external-delivery listeners.

Which channels an event goes to, and the record of each delivery.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from arm_backend.notifications.message import Message
from arm_common import NotificationChannel, NotificationDispatchLog


async def select_channels(db: AsyncSession, channel_type: str, event_type: str) -> list[NotificationChannel]:
    """The enabled channels of `channel_type` subscribed to `event_type`."""
    channels = (await db.execute(select(NotificationChannel))).scalars().all()
    return [c for c in channels if c.enabled and c.type == channel_type and event_type in (c.subscribed_events or [])]


def record_outcome(
    db: AsyncSession,
    channel: NotificationChannel,
    message: Message,
    *,
    fired_at: datetime,
    title: str,
    body: str,
    error: str | None,
) -> None:
    """Record one delivery on its channel (`last_*`) and in the dispatch log;
    `error` None means it succeeded.
    """
    channel.last_fired_at = fired_at
    if error is None:
        channel.last_success_at = fired_at
        channel.last_error = None
    else:
        channel.last_error = error
    db.add(
        NotificationDispatchLog(
            channel_id=channel.id,
            event_id=message.event_id,
            event_type=message.event_type,
            title=title,
            body=body,
            success=error is None,
            error=error,
        )
    )
