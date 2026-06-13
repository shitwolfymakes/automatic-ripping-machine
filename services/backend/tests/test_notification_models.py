"""Unit tests for the notification channel + dispatch-log models."""

from __future__ import annotations

from arm_common import NotificationChannel


def test_notification_channel_defaults() -> None:
    ch = NotificationChannel(
        type="apprise",
        name="Discord",
        config={"type": "apprise", "url": "discord://1/2"},
    )
    assert ch.id.startswith("ncl_")
    assert ch.enabled is True
    assert ch.type == "apprise"
    assert ch.subscribed_events == []
    assert ch.templates == {}
    assert ch.last_fired_at is None
    assert ch.last_success_at is None
    assert ch.last_error is None
    assert ch.__tablename__ == "notification_channels"


def test_notification_dispatch_log_defaults() -> None:
    from arm_common import NotificationDispatchLog

    row = NotificationDispatchLog(
        event_type="rip.completed",
        title="t",
        body="b",
        success=True,
    )
    assert row.id.startswith("ndl_")
    assert row.channel_id is None
    assert row.event_id is None
    assert row.error is None
    assert row.__tablename__ == "notification_dispatch_log"
