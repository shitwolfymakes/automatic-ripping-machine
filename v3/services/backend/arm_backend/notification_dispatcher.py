"""Phase 11 — outbound notification dispatcher.

Single asyncio task started in the FastAPI lifespan, mirroring the shape
of `TranscodeDispatcher`. Each tick:

1. Selects every `Event` row whose `notified_at IS NULL` and whose
   `event_type` is in `NOTIFIABLE_EVENT_TYPES`.
2. Loads the `Config` singleton and reads `notifications_enabled` and
   `notification_apprise_urls`.
3. If notifications are disabled OR the URL list is empty, marks every
   selected event with `notified_at = now()` and returns. This is the
   "off out of the box" exit behaviour — without it, events would pile
   up indefinitely while disabled and turning notifications on later
   would dump the entire backlog.
4. Otherwise, for each event: load the `Job` (if any), format a (title,
   body) pair, and call the configured `AppriseNotifier`. The notifier
   exception is caught and logged; `notified_at` is set on the row
   regardless. Notifications are best-effort — a permanently-broken URL
   does not pile up retries forever.

URL credentials never appear in log output. `redact_apprise_url(url)`
returns `"<scheme>://****"` — scheme-only redaction is conservative
because Apprise providers stash credentials in netloc, path, or query
depending on the scheme.

`_first_invalid_apprise_url(urls)` lives here too so the apprise import
stays in one module; the config router uses it to validate URL lists at
PATCH-time.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol
from urllib.parse import urlparse

import apprise
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import col, select

from arm_backend.config import Settings
from arm_backend.notification_format import format_event
from arm_backend.seeders import CONFIG_SINGLETON_ID
from arm_common import Config, Event, Job

if TYPE_CHECKING:
    from collections.abc import Sequence

logger = logging.getLogger("arm_backend.notification_dispatcher")


NOTIFIABLE_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "rip.completed",
        "rip.failed",
        "rip.partial",
        "session.completed",
        "session.failed",
        "session.partial",
    }
)


def redact_apprise_url(url: str) -> str:
    """Return a log-safe form of an Apprise URL.

    Returns `"<scheme>://****"`. Apprise places credentials in netloc,
    path, or query depending on the provider — surgical masking is
    fragile, so we keep only the scheme. The user already knows which
    providers they configured; the scheme alone is enough to correlate
    a log line back to a bad URL without leaking the credential.
    """
    parsed = urlparse(url)
    if not parsed.scheme:
        return "****"
    return f"{parsed.scheme}://****"


def _first_invalid_apprise_url(urls: list[str]) -> str | None:
    """Return the first URL `apprise.Apprise().add(url)` rejects, else None.

    Used by the config router to validate a PATCH body before it lands
    in the DB. Each URL gets a fresh Apprise() to keep validation
    side-effect-free — `.add()` mutates the bag.
    """
    for url in urls:
        ap = apprise.Apprise()
        if not ap.add(url):
            return url
    return None


class AppriseNotifier(Protocol):
    async def notify(self, urls: Sequence[str], title: str, body: str) -> None: ...


class _RealAppriseNotifier:
    """Production notifier. Wraps `apprise.Apprise().async_notify`."""

    async def notify(self, urls: Sequence[str], title: str, body: str) -> None:
        ap = apprise.Apprise()
        for url in urls:
            ap.add(url)
        # apprise's async_notify fans out URLs internally; one call covers
        # every configured destination for this event.
        await ap.async_notify(title=title, body=body)


class NotificationDispatcher:
    def __init__(
        self,
        settings: Settings,
        db_factory: async_sessionmaker[AsyncSession],
        notifier: AppriseNotifier,
    ) -> None:
        self._settings = settings
        self._db_factory = db_factory
        self._notifier = notifier
        self._stop = asyncio.Event()
        self._tick_interval = settings.ARM_NOTIFICATION_DISPATCH_INTERVAL_SECONDS

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        logger.info("notification dispatcher starting: tick=%ds", self._tick_interval)
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception as exc:  # never crash the loop
                logger.exception("notification dispatcher tick failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._tick_interval)
            except asyncio.TimeoutError:
                pass
        logger.info("notification dispatcher stopped")

    async def _tick(self) -> None:
        async with self._db_factory() as db:
            # SQL filter on the indexed `event_type`; the small `notified_at
            # IS NULL` predicate is applied in Python to stay compatible with
            # the in-memory test fake (mirrors the Phase 9 crash-recovery
            # helper for the same reason).
            candidates = (
                (
                    await db.execute(
                        select(Event)
                        .where(col(Event.event_type).in_(NOTIFIABLE_EVENT_TYPES))
                        .order_by(col(Event.emitted_at).asc())
                    )
                )
                .scalars()
                .all()
            )
            unsent = [e for e in candidates if e.notified_at is None]
            if not unsent:
                return

            cfg = (await db.execute(select(Config).where(col(Config.id) == CONFIG_SINGLETON_ID))).scalar_one_or_none()
            enabled = cfg is not None and cfg.notifications_enabled
            urls = list(cfg.notification_apprise_urls or []) if cfg is not None else []

            now = datetime.now(UTC)
            if not enabled:
                for event in unsent:
                    event.notified_at = now
                await db.commit()
                logger.info(
                    "notification dispatch: %d event(s) skipped (notifications disabled)",
                    len(unsent),
                )
                return
            if not urls:
                for event in unsent:
                    event.notified_at = now
                await db.commit()
                logger.info(
                    "notification dispatch: %d event(s) skipped (no urls configured)",
                    len(unsent),
                )
                return

            redacted = [redact_apprise_url(u) for u in urls]
            for event in unsent:
                job = await self._load_job(db, event.job_id)
                title, body = format_event(event, job)
                try:
                    await self._notifier.notify(urls, title, body)
                    logger.info(
                        "notification sent: event_id=%s type=%s urls=%s",
                        event.id,
                        event.event_type,
                        redacted,
                    )
                except Exception as exc:
                    logger.exception(
                        "notification failed: event_id=%s type=%s urls=%s err=%s",
                        event.id,
                        event.event_type,
                        redacted,
                        exc,
                    )
                event.notified_at = datetime.now(UTC)
            await db.commit()

    async def _load_job(self, db: AsyncSession, job_id: str | None) -> Job | None:
        if job_id is None:
            return None
        return (await db.execute(select(Job).where(col(Job.id) == job_id))).scalar_one_or_none()
