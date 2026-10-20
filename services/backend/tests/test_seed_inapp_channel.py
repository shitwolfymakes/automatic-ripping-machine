from __future__ import annotations


import pytest

from arm_backend.seeders import _seed_inapp_channel
from arm_backend.notifications.inbox_listener import INBOX_CHANNEL_ID
from arm_backend.notification_dispatcher import DEFAULT_INBOX_EVENT_TYPES

from tests._fakes import FakeSession


@pytest.mark.asyncio
async def test_seed_inapp_channel_creates_once() -> None:
    db = FakeSession()
    await _seed_inapp_channel(db)
    rows = db.rows.get("notification_channels", [])
    assert len(rows) == 1
    ch = rows[0]
    assert ch.id == INBOX_CHANNEL_ID
    assert ch.type == "inapp"
    assert ch.enabled is True
    assert ch.config == {"type": "inapp"}
    assert "rip.completed" in ch.subscribed_events
    assert ch.name == "In-app notifications"
    assert ch.templates == {}
    assert ch.subscribed_events == sorted(DEFAULT_INBOX_EVENT_TYPES)


@pytest.mark.asyncio
async def test_seed_inapp_channel_idempotent() -> None:
    db = FakeSession()
    await _seed_inapp_channel(db)
    await _seed_inapp_channel(db)
    assert len(db.rows.get("notification_channels", [])) == 1
