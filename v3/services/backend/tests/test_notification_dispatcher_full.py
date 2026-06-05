"""Residual notification_dispatcher coverage: the real Apprise notifier,
the run-loop exception + tick-timeout paths, and _load_job(None).
"""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from typing import Any  # noqa: E402

import pytest  # noqa: E402

from arm_backend import notification_dispatcher as nd  # noqa: E402
from arm_backend.config import settings  # noqa: E402
from arm_backend.notification_dispatcher import (  # noqa: E402
    NotificationDispatcher,
    _RealAppriseNotifier,
)

from tests._fakes import FakeSession  # noqa: E402


class _FakeApprise:
    def __init__(self) -> None:
        self.added: list[str] = []
        self.notified: list[dict[str, Any]] = []

    def add(self, url: str) -> bool:
        self.added.append(url)
        return True

    async def async_notify(self, *, title: str, body: str) -> bool:
        self.notified.append({"title": title, "body": body})
        return True


async def test_real_apprise_notifier(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeApprise()
    monkeypatch.setattr(nd, "apprise", type("M", (), {"Apprise": lambda: fake}))
    await _RealAppriseNotifier().notify(["json://localhost", "mailto://x"], "Title", "Body")
    assert fake.added == ["json://localhost", "mailto://x"]
    assert fake.notified == [{"title": "Title", "body": "Body"}]


async def test_load_job_none_returns_none() -> None:
    d = NotificationDispatcher(settings, db_factory=lambda: None, notifier=_FakeApprise())  # type: ignore[arg-type]
    assert await d._load_job(FakeSession(), None) is None  # type: ignore[arg-type]


async def test_run_loop_swallows_tick_error_then_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    """run() catches a _tick exception (132-133), the wait_for times out so
    the loop spins again (136-137), then stop() ends it cleanly."""
    monkeypatch.setattr(settings, "ARM_NOTIFICATION_DISPATCH_INTERVAL_SECONDS", 0.01)
    d = NotificationDispatcher(settings, db_factory=lambda: None, notifier=_FakeApprise())  # type: ignore[arg-type]

    calls = 0

    async def _boom() -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("tick failed")

    monkeypatch.setattr(d, "_tick", _boom)

    task = asyncio.create_task(d.run())
    await asyncio.sleep(0.05)
    d.stop()
    await asyncio.wait_for(task, timeout=2.0)
    assert calls >= 1  # loop ran, exception was swallowed, loop exited on stop
