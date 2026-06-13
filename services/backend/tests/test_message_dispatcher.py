from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

from datetime import UTC, datetime  # noqa: E402

import pytest  # noqa: E402

from arm_backend.config import Settings  # noqa: E402
from arm_backend.notification_dispatcher import MessageDispatcher  # noqa: E402
from arm_backend.notifications.message import Message  # noqa: E402
from arm_common import Config, Event  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


def _settings() -> Settings:
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


class _RecordingListener:
    def __init__(self, raises: bool = False) -> None:
        self.seen: list[Message] = []
        self.raises = raises

    async def handle(self, db, message: Message) -> None:
        self.seen.append(message)
        if self.raises:
            raise RuntimeError("listener boom")


@pytest.mark.asyncio
async def test_core_feeds_every_listener_and_sets_watermark() -> None:
    db = FakeSession()
    db.rows["events"] = [Event(id="evt_1", event_type="rip.completed", emitted_at=datetime.now(UTC), payload_json={})]
    db.rows["config"] = [Config(id=1, notifications_enabled=True)]
    l1, l2 = _RecordingListener(), _RecordingListener()
    d = MessageDispatcher(settings=_settings(), db_factory=_db_factory(db), listeners=[l1, l2])
    await d._tick()
    assert len(l1.seen) == 1 and len(l2.seen) == 1
    assert l1.seen[0].event_type == "rip.completed"
    assert l1.seen[0].default_title == "ARM: rip completed"
    assert db.rows["events"][0].notified_at is not None


@pytest.mark.asyncio
async def test_core_isolates_failing_listener() -> None:
    db = FakeSession()
    db.rows["events"] = [Event(id="evt_1", event_type="rip.completed", emitted_at=datetime.now(UTC), payload_json={})]
    db.rows["config"] = [Config(id=1, notifications_enabled=True)]
    bad, good = _RecordingListener(raises=True), _RecordingListener()
    d = MessageDispatcher(settings=_settings(), db_factory=_db_factory(db), listeners=[bad, good])
    await d._tick()
    # good listener still ran; watermark still set despite bad raising
    assert len(good.seen) == 1
    assert db.rows["events"][0].notified_at is not None


@pytest.mark.asyncio
async def test_core_disabled_marks_without_feeding() -> None:
    db = FakeSession()
    db.rows["events"] = [Event(id="evt_1", event_type="rip.completed", emitted_at=datetime.now(UTC), payload_json={})]
    db.rows["config"] = [Config(id=1, notifications_enabled=False)]
    l1 = _RecordingListener()
    d = MessageDispatcher(settings=_settings(), db_factory=_db_factory(db), listeners=[l1])
    await d._tick()
    assert l1.seen == []
    assert db.rows["events"][0].notified_at is not None


@pytest.mark.asyncio
async def test_core_selects_inbox_only_event_type() -> None:
    # rip.needs_user_input is inbox-default but NOT apprise-notifiable; the
    # core must still select it (NOTABLE = union) and feed listeners.
    db = FakeSession()
    db.rows["events"] = [
        Event(id="evt_1", event_type="rip.needs_user_input", emitted_at=datetime.now(UTC), payload_json={})
    ]
    db.rows["config"] = [Config(id=1, notifications_enabled=True)]
    l1 = _RecordingListener()
    d = MessageDispatcher(settings=_settings(), db_factory=_db_factory(db), listeners=[l1])
    await d._tick()
    assert len(l1.seen) == 1 and l1.seen[0].event_type == "rip.needs_user_input"
