"""Phase 11 — `NotificationDispatcher._tick` exhaustive cases.

Mirrors the FakeSession + db_factory shape used by the transcode
dispatcher tests. The Apprise lib itself is bypassed — tests inject a
`_FakeNotifier` that records `(urls, title, body)` calls and can be
configured to raise.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

from arm_backend.config import Settings  # noqa: E402
from arm_backend.notification_dispatcher import (  # noqa: E402
    NotificationDispatcher,
    redact_apprise_url,
)
from arm_common import (  # noqa: E402
    Config,
    DiscType,
    Event,
    Job,
    JobStatus,
    RetentionPolicy,
)
from tests._fakes import FakeSession  # noqa: E402


def _settings() -> Settings:
    return Settings.model_construct(
        DATABASE_URL="postgresql://x:x@localhost/x",
        ARM_SERVICE_TOKEN="tok-service",
        ARM_NOTIFICATION_DISPATCH_INTERVAL_SECONDS=5,
    )


def _db_factory(db: FakeSession) -> Any:
    class _Factory:
        def __call__(self) -> "_Factory":
            return self

        async def __aenter__(self) -> FakeSession:
            return db

        async def __aexit__(self, *exc: Any) -> None:
            return None

    return _Factory()


class _FakeNotifier:
    def __init__(self, raises: Exception | None = None) -> None:
        self.calls: list[tuple[tuple[str, ...], str, str]] = []
        self.raises = raises

    async def notify(self, urls: Sequence[str], title: str, body: str) -> None:
        self.calls.append((tuple(urls), title, body))
        if self.raises is not None:
            raise self.raises


def _seed_config(
    db: FakeSession,
    *,
    enabled: bool = False,
    urls: list[str] | None = None,
) -> None:
    db.rows["config"] = [
        Config(
            id=1,
            tmdb_api_key=None,
            omdb_api_key=None,
            musicbrainz_user_agent=None,
            auto_transcode_on_idle=False,
            auto_rip_on_insert=True,
            block_on_miss=True,
            default_retention_policy=RetentionPolicy.PRUNE_AFTER_SESSION,
            notification_apprise_urls=urls or [],
            notifications_enabled=enabled,
        )
    ]


def _seed_job(db: FakeSession) -> None:
    db.rows.setdefault("jobs", []).append(
        Job(
            id="job_x",
            drive_id="drv_x",
            disc_type=DiscType.DVD,
            title="Iron Man",
            year=2008,
            status=JobStatus.RIPPED,
            metadata_json={},
            resumed_from_crash=False,
        )
    )


def _make_event(
    *,
    event_id: str = "evt_1",
    event_type: str = "rip.completed",
    job_id: str | None = "job_x",
    payload: dict[str, Any] | None = None,
    notified_at: datetime | None = None,
    emitted_at: datetime | None = None,
) -> Event:
    return Event(
        id=event_id,
        event_type=event_type,
        emitted_at=emitted_at or datetime.now(UTC),
        job_id=job_id,
        track_id=None,
        session_application_id=None,
        payload_json=payload or {"drive_id": "drv_x", "tracks_done": 1, "tracks_total": 1},
        notified_at=notified_at,
    )


@pytest.mark.asyncio
async def test_disabled_marks_notified_without_calling() -> None:
    db = FakeSession()
    _seed_config(db, enabled=False, urls=["discord://AAA/BBB"])
    _seed_job(db)
    event = _make_event()
    db.rows["events"] = [event]

    notifier = _FakeNotifier()
    dispatcher = NotificationDispatcher(_settings(), _db_factory(db), notifier)
    await dispatcher._tick()

    assert notifier.calls == []
    assert event.notified_at is not None
    assert db.committed == 1


@pytest.mark.asyncio
async def test_enabled_with_urls_dispatches_event() -> None:
    db = FakeSession()
    _seed_config(db, enabled=True, urls=["discord://AAA/BBB"])
    _seed_job(db)
    event = _make_event()
    db.rows["events"] = [event]

    notifier = _FakeNotifier()
    dispatcher = NotificationDispatcher(_settings(), _db_factory(db), notifier)
    await dispatcher._tick()

    assert len(notifier.calls) == 1
    urls, title, body = notifier.calls[0]
    assert urls == ("discord://AAA/BBB",)
    assert title == "ARM: rip completed"
    assert "Iron Man (2008)" in body
    assert "drive=drv_x" in body
    assert event.notified_at is not None


@pytest.mark.asyncio
async def test_enabled_but_urls_empty_marks_without_calling() -> None:
    db = FakeSession()
    _seed_config(db, enabled=True, urls=[])
    _seed_job(db)
    event = _make_event()
    db.rows["events"] = [event]

    notifier = _FakeNotifier()
    dispatcher = NotificationDispatcher(_settings(), _db_factory(db), notifier)
    await dispatcher._tick()

    assert notifier.calls == []
    assert event.notified_at is not None


@pytest.mark.asyncio
async def test_non_notifiable_event_type_ignored() -> None:
    db = FakeSession()
    _seed_config(db, enabled=True, urls=["discord://AAA/BBB"])
    _seed_job(db)
    skip = _make_event(event_id="evt_skip", event_type="track.progress")
    progress = _make_event(event_id="evt_progress", event_type="rip.identified")
    db.rows["events"] = [skip, progress]

    notifier = _FakeNotifier()
    dispatcher = NotificationDispatcher(_settings(), _db_factory(db), notifier)
    await dispatcher._tick()

    assert notifier.calls == []
    assert skip.notified_at is None
    assert progress.notified_at is None


@pytest.mark.asyncio
async def test_already_notified_row_ignored() -> None:
    db = FakeSession()
    _seed_config(db, enabled=True, urls=["discord://AAA/BBB"])
    _seed_job(db)
    already = _make_event(event_id="evt_done", notified_at=datetime.now(UTC))
    db.rows["events"] = [already]

    notifier = _FakeNotifier()
    dispatcher = NotificationDispatcher(_settings(), _db_factory(db), notifier)
    await dispatcher._tick()

    assert notifier.calls == []


@pytest.mark.asyncio
async def test_notifier_raises_still_marks_notified(caplog: pytest.LogCaptureFixture) -> None:
    db = FakeSession()
    _seed_config(db, enabled=True, urls=["discord://AAA/BBB"])
    _seed_job(db)
    event = _make_event()
    db.rows["events"] = [event]

    notifier = _FakeNotifier(raises=RuntimeError("network down"))
    dispatcher = NotificationDispatcher(_settings(), _db_factory(db), notifier)
    with caplog.at_level(logging.ERROR, logger="arm_backend.notification_dispatcher"):
        await dispatcher._tick()

    assert event.notified_at is not None
    assert any("notification failed" in rec.message for rec in caplog.records)


@pytest.mark.asyncio
async def test_multi_event_tick() -> None:
    db = FakeSession()
    _seed_config(db, enabled=True, urls=["discord://AAA/BBB", "ntfy://my-topic"])
    _seed_job(db)
    older = _make_event(event_id="evt_a", emitted_at=datetime.now(UTC) - timedelta(seconds=30))
    newer = _make_event(event_id="evt_b", event_type="session.completed")
    third = _make_event(event_id="evt_c", event_type="rip.failed")
    db.rows["events"] = [older, newer, third]

    notifier = _FakeNotifier()
    dispatcher = NotificationDispatcher(_settings(), _db_factory(db), notifier)
    await dispatcher._tick()

    assert len(notifier.calls) == 3
    for urls, _title, _body in notifier.calls:
        assert urls == ("discord://AAA/BBB", "ntfy://my-topic")
    for event in (older, newer, third):
        assert event.notified_at is not None


@pytest.mark.asyncio
async def test_log_lines_redact_credential_segment(caplog: pytest.LogCaptureFixture) -> None:
    db = FakeSession()
    _seed_config(db, enabled=True, urls=["discord://AAA/BBB"])
    _seed_job(db)
    event = _make_event()
    db.rows["events"] = [event]

    notifier = _FakeNotifier()
    dispatcher = NotificationDispatcher(_settings(), _db_factory(db), notifier)
    with caplog.at_level(logging.INFO, logger="arm_backend.notification_dispatcher"):
        await dispatcher._tick()

    rendered = " ".join(rec.getMessage() for rec in caplog.records)
    assert "AAA" not in rendered
    assert "BBB" not in rendered
    assert "discord://****" in rendered


def test_redact_apprise_url_shape() -> None:
    assert redact_apprise_url("discord://AAA/BBB") == "discord://****"
    assert redact_apprise_url("mailto://user:pass@host") == "mailto://****"
    assert redact_apprise_url("not-a-url") == "****"
