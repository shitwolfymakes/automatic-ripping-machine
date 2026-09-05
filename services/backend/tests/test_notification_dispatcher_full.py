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
    MessageDispatcher,
    _RealAppriseNotifier,
)
from arm_backend.notifications.apprise_listener import AppriseListener  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


class _FakeApprise:
    def __init__(self, asset: Any = None) -> None:
        self.asset = asset
        self.added: list[str] = []
        self.notified: list[dict[str, Any]] = []

    def add(self, url: str) -> bool:
        self.added.append(url)
        return True

    async def async_notify(self, *, title: str, body: str) -> bool:
        self.notified.append({"title": title, "body": body})
        return True


def _patch_apprise(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch nd.apprise so Apprise(asset=...) records the asset it was built
    with. Returns a holder dict whose 'instance' is the _FakeApprise created."""
    holder: dict[str, Any] = {}

    def _make(asset: Any = None) -> _FakeApprise:
        fake = _FakeApprise(asset=asset)
        holder["instance"] = fake
        return fake

    # keep the real AppriseAsset so the notifier builds a genuine asset object
    import apprise as _real_apprise

    monkeypatch.setattr(nd, "apprise", type("M", (), {"Apprise": _make, "AppriseAsset": _real_apprise.AppriseAsset}))
    return holder


async def test_real_apprise_notifier_no_image(monkeypatch: pytest.MonkeyPatch) -> None:
    holder = _patch_apprise(monkeypatch)
    await _RealAppriseNotifier("").notify(["json://localhost", "mailto://x"], "Title", "Body")
    fake = holder["instance"]
    assert fake.added == ["json://localhost", "mailto://x"]
    assert fake.notified == [{"title": "Title", "body": "Body"}]
    # Even with no image URL the sender is branded "ARM".
    assert fake.asset is not None
    assert fake.asset.app_id == "ARM"
    # No image override applied — mask stays apprise's default (not our URL).
    assert "arm" not in (fake.asset.image_url_mask or "").lower()


async def test_real_apprise_notifier_with_image(monkeypatch: pytest.MonkeyPatch) -> None:
    holder = _patch_apprise(monkeypatch)
    url = "https://example.com/arm-logo.png"
    await _RealAppriseNotifier(url).notify(["json://localhost"], "T", "B")
    fake = holder["instance"]
    assert fake.asset.app_id == "ARM"
    assert fake.asset.image_url_mask == url
    assert fake.asset.image_url_logo == url


async def test_load_job_none_returns_none() -> None:
    d = MessageDispatcher(settings, db_factory=lambda: None, listeners=[AppriseListener(_RealAppriseNotifier())])  # type: ignore[arg-type]
    assert await d._load_job(FakeSession(), None) is None  # type: ignore[arg-type]


async def test_run_loop_swallows_tick_error_then_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    """run() catches a _tick exception (132-133), the wait_for times out so
    the loop spins again (136-137), then stop() ends it cleanly."""
    monkeypatch.setattr(settings, "ARM_NOTIFICATION_DISPATCH_INTERVAL_SECONDS", 0.01)
    d = MessageDispatcher(settings, db_factory=lambda: None, listeners=[AppriseListener(_RealAppriseNotifier())])  # type: ignore[arg-type]

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


async def test_real_notifier_raises_when_async_notify_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """apprise signals failure by RETURN VALUE (False/None), never raising —
    the notifier must convert that into an exception or failures are
    unrecordable (last_success_at/dispatch_log lie)."""

    class _FailingNotify(_FakeApprise):
        async def async_notify(self, *, title: str, body: str) -> bool:
            return False

    import apprise as _real_apprise

    monkeypatch.setattr(
        nd, "apprise", type("M", (), {"Apprise": _FailingNotify, "AppriseAsset": _real_apprise.AppriseAsset})
    )
    with pytest.raises(nd.AppriseDeliveryError):
        await _RealAppriseNotifier("").notify(["json://localhost"], "T", "B")


async def test_real_notifier_raises_on_invalid_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """ap.add() returns False for a URL apprise can't parse; an empty bag
    makes async_notify return None. Both must surface as failures."""

    class _RejectingAdd(_FakeApprise):
        def add(self, url: str) -> bool:
            return False

    import apprise as _real_apprise

    monkeypatch.setattr(
        nd, "apprise", type("M", (), {"Apprise": _RejectingAdd, "AppriseAsset": _real_apprise.AppriseAsset})
    )
    with pytest.raises(nd.AppriseDeliveryError):
        await _RealAppriseNotifier("").notify(["garbage"], "T", "B")
