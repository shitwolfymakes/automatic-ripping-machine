"""The unit a listener consumes, and the listener interface.

The message-dispatch core formats each notable Event into one `Message`
(via `notification_format`) and hands it to every registered listener.
Each listener decides internally whether it cares and how it delivers.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from arm_common import Job


@dataclass(frozen=True)
class Message:
    event_id: str
    event_type: str
    job_id: str | None
    default_title: str
    default_body: str
    # The loaded Job (or None) so listeners can resolve per-channel
    # template overrides and the inbox can deep-link.
    job: Job | None
    # The event's payload_json, so listeners can build the render context
    # without re-loading the Event.
    payload: dict[str, Any]
    # Global Config.notifications_enabled at dispatch time. Gates EXTERNAL
    # delivery only (AppriseListener no-ops when False); the in-app inbox
    # always delivers so the bell works out of the box.
    apprise_enabled: bool = True


class NotificationListener(Protocol):
    async def handle(self, db: AsyncSession, message: Message) -> None: ...
