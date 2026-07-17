"""Phase 11 — `MessageDispatcher._tick` exhaustive cases (via AppriseListener).

Mirrors the FakeSession + db_factory shape used by the transcode
dispatcher tests. The Apprise lib itself is bypassed — tests inject a
`_FakeNotifier` that records `(urls, title, body)` calls and can be
configured to raise. The end-to-end channel routing / dispatch-log /
`last_*` behaviour now lives in `AppriseListener`; the dispatcher feeds it.
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
    MessageDispatcher,
    redact_apprise_url,
)
from arm_backend.notifications.apprise_listener import AppriseListener  # noqa: E402
from arm_common import (  # noqa: E402
    Config,
    DiscType,
    Event,
    Job,
    JobStatus,
    NotificationChannel,
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


def _seed_channel(
    db: FakeSession,
    *,
    channel_id: str = "ncl_x",
    url: str = "discord://AAA/BBB",
    subscribed: list[str] | None = None,
    enabled: bool = True,
) -> NotificationChannel:
    channel = NotificationChannel(
        id=channel_id,
        type="apprise",
        name=channel_id,
        enabled=enabled,
        config={"type": "apprise", "url": url},
        subscribed_events=subscribed or ["rip.completed"],
    )
    db.rows.setdefault("notification_channels", []).append(channel)
    return channel


def _seed_job(db: FakeSession) -> None:
    db.rows.setdefault("jobs", []).append(
        Job(
            id="job_01JZXR7K3M5Q8N4VWA00000001",
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
    job_id: str | None = "job_01JZXR7K3M5Q8N4VWA00000001",
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
    dispatcher = MessageDispatcher(_settings(), _db_factory(db), [AppriseListener(notifier)])
    await dispatcher._tick()

    assert notifier.calls == []
    assert event.notified_at is not None
    assert db.committed == 1


@pytest.mark.asyncio
async def test_enabled_with_subscribed_channel_dispatches_event() -> None:
    db = FakeSession()
    _seed_config(db, enabled=True)
    _seed_channel(db, url="discord://AAA/BBB", subscribed=["rip.completed"])
    _seed_job(db)
    event = _make_event()
    db.rows["events"] = [event]

    notifier = _FakeNotifier()
    dispatcher = MessageDispatcher(_settings(), _db_factory(db), [AppriseListener(notifier)])
    await dispatcher._tick()

    assert len(notifier.calls) == 1
    urls, title, body = notifier.calls[0]
    assert urls == ("discord://AAA/BBB",)
    assert title == "ARM: rip completed"
    assert "Iron Man (2008)" in body
    assert "drive=drv_x" in body
    assert event.notified_at is not None
    # a dispatch-log row records the successful send
    logs = db.rows.get("notification_dispatch_log", [])
    assert len(logs) == 1 and logs[0].success is True and logs[0].channel_id == "ncl_x"


@pytest.mark.asyncio
async def test_enabled_but_no_subscribed_channels_marks_without_calling() -> None:
    # Channel exists but is subscribed to a different event type, so the
    # rip.completed event has no target: it is still marked notified_at and
    # the notifier is never called (the old "URL list empty → skip" intent).
    db = FakeSession()
    _seed_config(db, enabled=True)
    _seed_channel(db, subscribed=["rip.failed"])
    _seed_job(db)
    event = _make_event()
    db.rows["events"] = [event]

    notifier = _FakeNotifier()
    dispatcher = MessageDispatcher(_settings(), _db_factory(db), [AppriseListener(notifier)])
    await dispatcher._tick()

    assert notifier.calls == []
    assert event.notified_at is not None
    assert db.rows.get("notification_dispatch_log", []) == []


@pytest.mark.asyncio
async def test_non_notifiable_event_type_ignored() -> None:
    db = FakeSession()
    _seed_config(db, enabled=True, urls=["discord://AAA/BBB"])
    _seed_job(db)
    skip = _make_event(event_id="evt_skip", event_type="track.progress")
    progress = _make_event(event_id="evt_progress", event_type="rip.identified")
    db.rows["events"] = [skip, progress]

    notifier = _FakeNotifier()
    dispatcher = MessageDispatcher(_settings(), _db_factory(db), [AppriseListener(notifier)])
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
    dispatcher = MessageDispatcher(_settings(), _db_factory(db), [AppriseListener(notifier)])
    await dispatcher._tick()

    assert notifier.calls == []


@pytest.mark.asyncio
async def test_notifier_raises_still_marks_notified(caplog: pytest.LogCaptureFixture) -> None:
    db = FakeSession()
    _seed_config(db, enabled=True)
    channel = _seed_channel(db, subscribed=["rip.completed"])
    _seed_job(db)
    event = _make_event()
    db.rows["events"] = [event]

    notifier = _FakeNotifier(raises=RuntimeError("network down"))
    dispatcher = MessageDispatcher(_settings(), _db_factory(db), [AppriseListener(notifier)])
    with caplog.at_level(logging.ERROR, logger="arm_backend.notification_dispatcher"):
        await dispatcher._tick()

    assert event.notified_at is not None
    assert any("notification failed" in rec.message for rec in caplog.records)
    # failure is isolated to the channel + recorded in the dispatch log
    assert channel.last_error is not None and channel.last_success_at is None
    logs = db.rows.get("notification_dispatch_log", [])
    assert len(logs) == 1 and logs[0].success is False


@pytest.mark.asyncio
async def test_multi_event_tick() -> None:
    db = FakeSession()
    _seed_config(db, enabled=True)
    # One channel subscribed to every event type these three events carry, so
    # each event fans out to it (one notify call per event, per the per-channel
    # routing model).
    _seed_channel(
        db,
        url="discord://AAA/BBB",
        subscribed=["rip.completed", "session.completed", "rip.failed"],
    )
    _seed_job(db)
    older = _make_event(event_id="evt_a", emitted_at=datetime.now(UTC) - timedelta(seconds=30))
    newer = _make_event(event_id="evt_b", event_type="session.completed")
    third = _make_event(event_id="evt_c", event_type="rip.failed")
    db.rows["events"] = [older, newer, third]

    notifier = _FakeNotifier()
    dispatcher = MessageDispatcher(_settings(), _db_factory(db), [AppriseListener(notifier)])
    await dispatcher._tick()

    assert len(notifier.calls) == 3
    for urls, _title, _body in notifier.calls:
        assert urls == ("discord://AAA/BBB",)
    for event in (older, newer, third):
        assert event.notified_at is not None
    assert len(db.rows.get("notification_dispatch_log", [])) == 3


@pytest.mark.asyncio
async def test_log_lines_redact_credential_segment(caplog: pytest.LogCaptureFixture) -> None:
    # The failure log line is the only place a channel URL is emitted; it must
    # show the scheme-only redacted form, never the credential segment.
    db = FakeSession()
    _seed_config(db, enabled=True)
    _seed_channel(db, url="discord://AAA/BBB", subscribed=["rip.completed"])
    _seed_job(db)
    event = _make_event()
    db.rows["events"] = [event]

    notifier = _FakeNotifier(raises=RuntimeError("network down"))
    dispatcher = MessageDispatcher(_settings(), _db_factory(db), [AppriseListener(notifier)])
    with caplog.at_level(logging.INFO, logger="arm_backend.notifications.apprise_listener"):
        await dispatcher._tick()

    rendered = " ".join(rec.getMessage() for rec in caplog.records)
    assert "AAA" not in rendered
    assert "BBB" not in rendered
    assert "discord://****" in rendered


def test_redact_apprise_url_shape() -> None:
    assert redact_apprise_url("discord://AAA/BBB") == "discord://****"
    assert redact_apprise_url("mailto://user:pass@host") == "mailto://****"
    assert redact_apprise_url("not-a-url") == "****"
