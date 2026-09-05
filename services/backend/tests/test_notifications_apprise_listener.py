from __future__ import annotations

import os

# The listener imports `notification_dispatcher`, which imports `config`'s
# module-level `settings = Settings()`; pydantic-settings requires these
# env vars at import time. Mirrors the sibling dispatcher tests.
os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

from arm_backend.notifications.apprise_listener import AppriseListener  # noqa: E402
from arm_backend.notifications.message import Message  # noqa: E402
from arm_common import DiscType, Job, JobStatus, NotificationChannel  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


class _FakeNotifier:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.fail_urls: set[str] = set()

    async def notify(self, urls, title, body) -> None:
        self.calls.append((list(urls), title, body))
        if any(u in self.fail_urls for u in urls):
            raise RuntimeError("boom")


def _job(title="Dune") -> Job:
    return Job(
        id="job_1",
        drive_id="sr0",
        disc_type=DiscType.DVD,
        title=title,
        year=2010,
        status=JobStatus.RIPPED,
        metadata_json={},
        resumed_from_crash=False,
    )


def _msg(event_type="rip.completed", *, job=None, payload=None) -> Message:
    return Message(
        event_id="evt_1",
        event_type=event_type,
        job_id="job_1",
        default_title="ARM: rip completed",
        default_body="disc",
        job=job,
        payload=payload or {},
    )


@pytest.mark.asyncio
async def test_apprise_listener_routes_to_subscribed_apprise_channels() -> None:
    db = FakeSession()
    db.rows["notification_channels"] = [
        NotificationChannel(
            id="ncl_a",
            type="apprise",
            name="A",
            enabled=True,
            config={"type": "apprise", "url": "json://a/x"},
            subscribed_events=["rip.completed"],
        ),
        NotificationChannel(
            id="ncl_b",
            type="apprise",
            name="B",
            enabled=True,
            config={"type": "apprise", "url": "json://b/x"},
            subscribed_events=["rip.failed"],
        ),
        NotificationChannel(
            id="ncl_off",
            type="apprise",
            name="C",
            enabled=False,
            config={"type": "apprise", "url": "json://c/x"},
            subscribed_events=["rip.completed"],
        ),
        NotificationChannel(
            id="ncl_inbox",
            type="inapp",
            name="bell",
            enabled=True,
            config={"type": "inapp"},
            subscribed_events=["rip.completed"],
        ),
    ]
    notifier = _FakeNotifier()
    await AppriseListener(notifier).handle(db, _msg())
    # only the enabled apprise channel subscribed to rip.completed; inapp ignored
    assert notifier.calls == [(["json://a/x"], "ARM: rip completed", "disc")]
    a = db.rows["notification_channels"][0]
    assert a.last_success_at is not None and a.last_error is None
    logs = db.rows.get("notification_dispatch_log", [])
    assert len(logs) == 1 and logs[0].success is True and logs[0].channel_id == "ncl_a"


@pytest.mark.asyncio
async def test_apprise_listener_isolates_failure_and_logs() -> None:
    db = FakeSession()
    db.rows["notification_channels"] = [
        NotificationChannel(
            id="ncl_a",
            type="apprise",
            name="A",
            enabled=True,
            config={"type": "apprise", "url": "json://a/x"},
            subscribed_events=["rip.completed"],
        ),
    ]
    notifier = _FakeNotifier()
    notifier.fail_urls = {"json://a/x"}
    await AppriseListener(notifier).handle(db, _msg())
    a = db.rows["notification_channels"][0]
    assert a.last_error is not None and a.last_success_at is None
    assert db.rows["notification_dispatch_log"][0].success is False


@pytest.mark.asyncio
async def test_apprise_listener_applies_template_override() -> None:
    db = FakeSession()
    db.rows["notification_channels"] = [
        NotificationChannel(
            id="ncl_a",
            type="apprise",
            name="A",
            enabled=True,
            config={"type": "apprise", "url": "json://a/x"},
            subscribed_events=["rip.completed"],
            templates={"rip.completed": {"title": "Custom"}},
        ),
    ]
    notifier = _FakeNotifier()
    await AppriseListener(notifier).handle(db, _msg())
    assert notifier.calls[0][1] == "Custom"  # title overridden, body falls back to default
    assert notifier.calls[0][2] == "disc"


@pytest.mark.asyncio
async def test_apprise_renders_custom_template_with_vars() -> None:
    db = FakeSession()
    db.rows["notification_channels"] = [
        NotificationChannel(
            id="ncl_a",
            type="apprise",
            name="A",
            enabled=True,
            config={"type": "apprise", "url": "json://a/x"},
            subscribed_events=["rip.completed"],
            templates={
                "rip.completed": {"title": "Done: {job_title}", "body": "{tracks_done}/{tracks_total} on {drive_id}"}
            },
        )
    ]
    notifier = _FakeNotifier()
    msg = _msg(job=_job("Dune"), payload={"drive_id": "sr0", "tracks_done": 2, "tracks_failed": 0, "tracks_total": 2})
    await AppriseListener(notifier).handle(db, msg)
    assert notifier.calls, "notifier not called"
    _urls, title, body = notifier.calls[0]
    assert title == "Done: Dune"
    assert body == "2/2 on sr0"


@pytest.mark.asyncio
async def test_apprise_bad_template_var_records_error_not_raise() -> None:
    ch = NotificationChannel(
        id="ncl_a",
        type="apprise",
        name="A",
        enabled=True,
        config={"type": "apprise", "url": "json://a/x"},
        subscribed_events=["rip.completed"],
        templates={"rip.completed": {"title": "t", "body": "{nope}"}},
    )
    db = FakeSession()
    db.rows["notification_channels"] = [ch]
    notifier = _FakeNotifier()
    await AppriseListener(notifier).handle(db, _msg(job=_job(), payload={}))  # must not raise
    assert notifier.calls == [], "should not fire apprise on a render error"
    assert ch.last_error and "nope" in ch.last_error
