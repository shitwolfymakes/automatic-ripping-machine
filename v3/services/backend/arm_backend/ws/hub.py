"""In-memory pub/sub hub.

Single-process, single-event-loop. Topic strings address subscriber
sets; `emit` builds the `WSEnvelope`, optionally persists to `events`,
and fans out to every WebSocket subscribed to that topic.

Progress topics (`ripper.progress.*`) are throttled at 1 Hz per
`(topic, track_id)` pair — last tick wins inside the window. Typed
event topics (anything else) are not throttled and not coalesced.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncSession

from arm_common import Event, new_id
from arm_common.schemas import WSEnvelope

if TYPE_CHECKING:
    from fastapi import WebSocket

logger = logging.getLogger("arm_backend.ws.hub")

PROGRESS_THROTTLE_SECONDS = 1.0
SEND_TIMEOUT_SECONDS = 2.0


class WSHub:
    def __init__(self) -> None:
        self._subs: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._throttle: dict[tuple[str, str | None], float] = {}

    async def subscribe(self, ws: WebSocket, topic: str) -> None:
        async with self._lock:
            self._subs[topic].add(ws)

    async def unsubscribe(self, ws: WebSocket, topic: str) -> None:
        async with self._lock:
            subs = self._subs.get(topic)
            if subs is not None:
                subs.discard(ws)
                if not subs:
                    self._subs.pop(topic, None)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            for topic in list(self._subs.keys()):
                self._subs[topic].discard(ws)
                if not self._subs[topic]:
                    self._subs.pop(topic, None)

    def subscriber_count(self, topic: str) -> int:
        return len(self._subs.get(topic, set()))

    async def emit(
        self,
        topic: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        persist: bool = True,
        job_id: str | None = None,
        track_id: str | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        is_progress = topic.startswith("ripper.progress.") or topic.startswith("transcode.progress.")
        if is_progress and not self._allow_progress_tick(topic, track_id):
            return

        envelope = WSEnvelope(
            event_id=new_id("evt"),
            event_type=event_type,
            emitted_at=datetime.now(timezone.utc),
            topic=topic,
            job_id=job_id,
            track_id=track_id,
            payload=payload,
        )

        if persist:
            if session is None:
                logger.warning("emit(persist=True) without session for topic=%s; skipping write", topic)
            else:
                event_row = Event(
                    id=envelope.event_id,
                    event_type=event_type,
                    job_id=job_id,
                    track_id=track_id,
                    payload_json=payload,
                )
                session.add(event_row)
                await session.flush()

        await self._broadcast(topic, envelope)

    async def _broadcast(self, topic: str, envelope: WSEnvelope) -> None:
        async with self._lock:
            recipients = list(self._subs.get(topic, set()))
        if not recipients:
            return

        frame = envelope.model_dump(mode="json")
        for ws in recipients:
            try:
                await asyncio.wait_for(ws.send_json(frame), timeout=SEND_TIMEOUT_SECONDS)
            except (asyncio.TimeoutError, Exception) as exc:
                logger.warning("ws send failed on topic=%s: %s; evicting", topic, exc)
                await self.disconnect(ws)

    def _allow_progress_tick(self, topic: str, track_id: str | None) -> bool:
        key = (topic, track_id)
        now = time.monotonic()
        last = self._throttle.get(key, 0.0)
        if now - last < PROGRESS_THROTTLE_SECONDS:
            return False
        self._throttle[key] = now
        return True
