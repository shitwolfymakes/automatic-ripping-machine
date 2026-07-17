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
    assert l1.seen[0].default_title == "ARM: rip completed — "
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
async def test_core_disabled_still_feeds_listeners_with_gate_flag() -> None:
    """The global toggle gates apprise only: listeners are still fed (the
    inbox must work out of the box) with apprise_enabled=False on the message."""
    db = FakeSession()
    db.rows["events"] = [Event(id="evt_1", event_type="rip.completed", emitted_at=datetime.now(UTC), payload_json={})]
    db.rows["config"] = [Config(id=1, notifications_enabled=False)]
    l1 = _RecordingListener()
    d = MessageDispatcher(settings=_settings(), db_factory=_db_factory(db), listeners=[l1])
    await d._tick()
    assert len(l1.seen) == 1 and l1.seen[0].apprise_enabled is False
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


@pytest.mark.asyncio
async def test_disabled_toggle_still_feeds_listeners_with_apprise_gated() -> None:
    """notifications_enabled=False must NOT starve the in-app inbox: listeners
    still run (message.apprise_enabled=False gates only external sends) and
    the watermark is stamped."""
    db = FakeSession()
    db.rows["events"] = [
        Event(id="evt_gate", event_type="rip.needs_user_input", emitted_at=datetime.now(UTC), payload_json={})
    ]
    db.rows["config"] = [Config(id=1, notifications_enabled=False)]
    listener = _RecordingListener()
    d = MessageDispatcher(settings=_settings(), db_factory=_db_factory(db), listeners=[listener])
    await d._tick()
    assert len(listener.seen) == 1
    assert listener.seen[0].apprise_enabled is False
    assert db.rows["events"][0].notified_at is not None


@pytest.mark.asyncio
async def test_enabled_toggle_marks_message_apprise_enabled() -> None:
    db = FakeSession()
    db.rows["events"] = [Event(id="evt_on", event_type="rip.completed", emitted_at=datetime.now(UTC), payload_json={})]
    db.rows["config"] = [Config(id=1, notifications_enabled=True)]
    listener = _RecordingListener()
    d = MessageDispatcher(settings=_settings(), db_factory=_db_factory(db), listeners=[listener])
    await d._tick()
    assert listener.seen[0].apprise_enabled is True


@pytest.mark.asyncio
async def test_watermark_commits_per_event_not_per_batch() -> None:
    """External sends happen mid-tick; a batch-wide commit re-sends the whole
    batch if anything later fails. The watermark must commit per event."""

    class _CountingSession(FakeSession):
        def __init__(self) -> None:
            super().__init__()
            self.commits = 0

        async def commit(self) -> None:
            self.commits += 1
            await super().commit()

    db = _CountingSession()
    db.rows["events"] = [
        Event(id="evt_a", event_type="rip.completed", emitted_at=datetime.now(UTC), payload_json={}),
        Event(id="evt_b", event_type="rip.failed", emitted_at=datetime.now(UTC), payload_json={}),
    ]
    db.rows["config"] = [Config(id=1, notifications_enabled=True)]
    d = MessageDispatcher(settings=_settings(), db_factory=_db_factory(db), listeners=[_RecordingListener()])
    await d._tick()
    assert db.commits >= 2
