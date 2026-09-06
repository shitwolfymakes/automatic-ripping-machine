"""Bash hook delivery as a notification listener.

Same bookkeeping as `AppriseListener`: for each enabled bash channel
subscribed to the event, prepare the run (templates + inputs), execute the
script, record `last_*`, write a dispatch-log row. Gated by the global
notifications toggle like Apprise: a script is external delivery.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from arm_backend.notification_format import context_from_message
from arm_backend.notifications.bash_hook import HookError, prepare_run
from arm_backend.notifications.bash_runner import run_script
from arm_backend.notifications.message import Message
from arm_common import NotificationChannel, NotificationDispatchLog

logger = logging.getLogger("arm_backend.notifications.bash_listener")


class BashListener:
    def __init__(self, *, scripts_root: str, media_root: str, raw_root: str) -> None:
        self._scripts_root = scripts_root
        self._media_root = media_root
        self._raw_root = raw_root

    async def handle(self, db: AsyncSession, message: Message) -> None:
        if not message.apprise_enabled:
            return
        channels = (await db.execute(select(NotificationChannel))).scalars().all()
        targets = [
            c for c in channels if c.enabled and c.type == "bash" and message.event_type in (c.subscribed_events or [])
        ]
        if not targets:
            return
        ctx = context_from_message(
            event_type=message.event_type, job=message.job, job_id=message.job_id, payload=message.payload
        )
        for channel in targets:
            fire_now = datetime.now(UTC)
            title = body = ""
            err: str | None = None
            try:
                run = prepare_run(
                    config=channel.config or {},
                    template=(channel.templates or {}).get(message.event_type),
                    event_type=message.event_type,
                    default_title=message.default_title,
                    default_body=message.default_body,
                    context=ctx,
                    scripts_root=self._scripts_root,
                    media_root=self._media_root,
                    raw_root=self._raw_root,
                )
                title, body = run.title, run.body
                result = await run_script(
                    run.path, title=title, body=body, env=run.env, timeout_seconds=run.timeout_seconds
                )
                if not result.ok:
                    err = result.error
            except HookError as exc:
                err = str(exc)
            if err is not None:
                logger.warning("bash hook failed: event_id=%s channel=%s %s", message.event_id, channel.id, err)
            channel.last_fired_at = fire_now
            if err is None:
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
                    success=err is None,
                    error=err,
                )
            )
