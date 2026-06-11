"""Dispatcher routes events to subscribed enabled channels + writes logs."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

from datetime import UTC, datetime  # noqa: E402

import pytest  # noqa: E402

from arm_backend.config import Settings  # noqa: E402
from arm_backend.notification_dispatcher import NotificationDispatcher  # noqa: E402
from arm_common import Config, Event, NotificationChannel  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


class _FakeNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.fail_urls: set[str] = set()

    async def notify(self, urls, title, body) -> None:
        self.calls.append((list(urls), title, body))
        if any(u in self.fail_urls for u in urls):
            raise RuntimeError("boom")


def _settings() -> Settings:
    import os
    os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
    os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")
    return Settings()


def _db_factory(db: FakeSession):
    class _Factory:
        def __call__(self):
            class _Ctx:
                async def __aenter__(self_) -> FakeSession:
                    return db
                async def __aexit__(self_, *a) -> None:
                    return None
            return _Ctx()
    return _Factory()


@pytest.mark.asyncio
async def test_dispatch_routes_to_subscribed_channels() -> None:
    db = FakeSession()
    db.rows["events"] = [Event(id="evt_1", event_type="rip.completed", emitted_at=datetime.now(UTC), payload_json={})]
    db.rows["config"] = [Config(id=1, notifications_enabled=True)]
    db.rows["notification_channels"] = [
        NotificationChannel(id="ncl_a", type="apprise", name="A", enabled=True,
                            config={"type": "apprise", "url": "json://a/x"}, subscribed_events=["rip.completed"]),
        NotificationChannel(id="ncl_b", type="apprise", name="B", enabled=True,
                            config={"type": "apprise", "url": "json://b/x"}, subscribed_events=["rip.failed"]),
        NotificationChannel(id="ncl_c", type="apprise", name="C", enabled=False,
                            config={"type": "apprise", "url": "json://c/x"}, subscribed_events=["rip.completed"]),
    ]
    notifier = _FakeNotifier()
    d = NotificationDispatcher(settings=_settings(), db_factory=_db_factory(db), notifier=notifier)
    await d._tick()
    # only channel A (subscribed + enabled) gets the event
    assert notifier.calls == [(["json://a/x"], "ARM: rip completed", notifier.calls[0][2])]
    assert db.rows["events"][0].notified_at is not None
    assert db.rows["notification_channels"][0].last_success_at is not None
    # one dispatch-log row, success
    logs = db.rows.get("notification_dispatch_log", [])
    assert len(logs) == 1 and logs[0].success is True and logs[0].channel_id == "ncl_a"


@pytest.mark.asyncio
async def test_dispatch_disabled_marks_without_sending() -> None:
    db = FakeSession()
    db.rows["events"] = [Event(id="evt_1", event_type="rip.completed", emitted_at=datetime.now(UTC), payload_json={})]
    db.rows["config"] = [Config(id=1, notifications_enabled=False)]
    notifier = _FakeNotifier()
    d = NotificationDispatcher(settings=_settings(), db_factory=_db_factory(db), notifier=notifier)
    await d._tick()
    assert notifier.calls == []
    assert db.rows["events"][0].notified_at is not None


@pytest.mark.asyncio
async def test_dispatch_channel_failure_isolated_and_logged() -> None:
    db = FakeSession()
    db.rows["events"] = [Event(id="evt_1", event_type="rip.completed", emitted_at=datetime.now(UTC), payload_json={})]
    db.rows["config"] = [Config(id=1, notifications_enabled=True)]
    db.rows["notification_channels"] = [
        NotificationChannel(id="ncl_a", type="apprise", name="A", enabled=True,
                            config={"type": "apprise", "url": "json://a/x"}, subscribed_events=["rip.completed"]),
    ]
    notifier = _FakeNotifier()
    notifier.fail_urls = {"json://a/x"}
    d = NotificationDispatcher(settings=_settings(), db_factory=_db_factory(db), notifier=notifier)
    await d._tick()
    assert db.rows["events"][0].notified_at is not None  # still marked
    ch = db.rows["notification_channels"][0]
    assert ch.last_error is not None and ch.last_success_at is None
    assert db.rows["notification_dispatch_log"][0].success is False
