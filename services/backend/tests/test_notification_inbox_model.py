"""Unit test for the NotificationInbox model."""

from __future__ import annotations

from arm_common import NotificationInbox


def test_notification_inbox_defaults() -> None:
    row = NotificationInbox(
        event_type="rip.completed",
        title="ARM: rip completed",
        message="Iron Man (2008)",
    )
    assert row.id.startswith("nin_")
    assert row.event_id is None
    assert row.channel_id is None
    assert row.job_id is None
    assert row.seen is False
    assert row.cleared is False
    assert row.seen_at is None
    assert row.cleared_at is None
    assert row.__tablename__ == "notification_inbox"
