from __future__ import annotations

import pytest

from arm_backend.notifications.inbox_listener import INBOX_CHANNEL_ID, InboxListener
from arm_backend.notifications.message import Message
from arm_common import DiscType, Job, JobStatus, NotificationChannel

from tests._fakes import FakeSession


def _job(title="Iron Man") -> Job:
    return Job(
        id="job_1",
        drive_id="sr0",
        disc_type=DiscType.DVD,
        title=title,
        year=2008,
        status=JobStatus.RIPPED,
        metadata_json={},
        resumed_from_crash=False,
    )


def _msg(event_type="rip.completed", job_id=None, *, job=None, payload=None) -> Message:
    return Message(
        event_id="evt_1",
        event_type=event_type,
        job_id=job_id,
        default_title="ARM: rip completed",
        default_body="Iron Man",
        job=job,
        payload=payload or {},
    )


def _inapp(enabled=True, events=("rip.completed",), templates=None) -> NotificationChannel:
    return NotificationChannel(
        id=INBOX_CHANNEL_ID,
        type="inapp",
        name="bell",
        enabled=enabled,
        config={"type": "inapp"},
        subscribed_events=list(events),
        templates=templates or {},
    )


@pytest.mark.asyncio
async def test_inbox_listener_writes_row_for_subscribed_event() -> None:
    db = FakeSession()
    db.rows["notification_channels"] = [_inapp()]
    await InboxListener().handle(db, _msg(job_id="job_1"))
    rows = db.rows.get("notification_inbox", [])
    assert len(rows) == 1
    r = rows[0]
    assert r.event_type == "rip.completed"
    assert r.title == "ARM: rip completed" and r.message == "Iron Man"
    assert r.channel_id == INBOX_CHANNEL_ID
    assert r.event_id == "evt_1" and r.job_id == "job_1"
    assert r.seen is False and r.cleared is False


@pytest.mark.asyncio
async def test_inbox_listener_noop_when_unsubscribed() -> None:
    db = FakeSession()
    db.rows["notification_channels"] = [_inapp(events=("rip.failed",))]
    await InboxListener().handle(db, _msg(event_type="rip.completed"))
    assert db.rows.get("notification_inbox", []) == []


@pytest.mark.asyncio
async def test_inbox_listener_noop_when_disabled_or_absent() -> None:
    db = FakeSession()
    db.rows["notification_channels"] = [_inapp(enabled=False)]
    await InboxListener().handle(db, _msg())
    assert db.rows.get("notification_inbox", []) == []
    # absent entirely
    db2 = FakeSession()
    await InboxListener().handle(db2, _msg())
    assert db2.rows.get("notification_inbox", []) == []


@pytest.mark.asyncio
async def test_inbox_listener_applies_template_override() -> None:
    db = FakeSession()
    db.rows["notification_channels"] = [_inapp(templates={"rip.completed": {"title": "Done!"}})]
    await InboxListener().handle(db, _msg())
    assert db.rows["notification_inbox"][0].title == "Done!"
    assert db.rows["notification_inbox"][0].message == "Iron Man"


@pytest.mark.asyncio
async def test_inbox_interpolates_custom_template() -> None:
    db = FakeSession()
    db.rows["notification_channels"] = [_inapp(templates={"rip.completed": {"body": "{job_title} done"}})]
    await InboxListener().handle(db, _msg(job_id="job_1", job=_job("Dune"), payload={}))
    rows = db.rows.get("notification_inbox", [])
    assert len(rows) == 1
    r = rows[0]
    assert r.message == "Dune done"


@pytest.mark.asyncio
async def test_inbox_bad_template_var_skips_no_raise() -> None:
    db = FakeSession()
    db.rows["notification_channels"] = [_inapp(templates={"rip.completed": {"body": "{nope}"}})]
    await InboxListener().handle(db, _msg(job_id="job_1", job=_job(), payload={}))
    # must not raise and must NOT add an inbox row
    assert db.rows.get("notification_inbox", []) == []
