"""Lifespan wiring for the track stager: start gating, the shutdown step and the boot sweep."""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI

from arm_backend import main as main_mod
from arm_backend import stager
from arm_common import StageStatus, TrackStage
from tests._stage_env import Env, seed_stage


class _FakeStager:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.ran = asyncio.Event()
        self.stopped = False
        self.hang = False

    async def run(self) -> None:
        self.ran.set()
        await asyncio.sleep(3600)

    async def stop(self) -> None:
        self.stopped = True
        if self.hang:
            await asyncio.sleep(3600)


def _services(host_paths_set: bool) -> main_mod._BackendServices:
    app = FastAPI()
    app.state.ws_hub = object()
    services = main_mod._BackendServices(app)
    services._transcode_dispatcher = SimpleNamespace(host_paths_set=lambda: host_paths_set)  # type: ignore[assignment]
    return services


@pytest.fixture(autouse=True)
def _clear_active_stager() -> Any:
    yield
    stager.set_active_stager(None)


async def test_the_stager_starts_when_the_host_paths_are_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main_mod, "TrackStager", _FakeStager)
    services = _services(True)
    services._start_stager()
    try:
        assert isinstance(services._stager, _FakeStager)
        await asyncio.wait_for(services._stager.ran.wait(), 1)
        assert services._app.state.stager is services._stager
        assert stager._active_stager is services._stager
        assert services._stager.args[0] is main_mod.settings
        assert services._stager.args[2] is main_mod.SessionLocal
    finally:
        services._stager_task.cancel()


async def test_the_stager_is_not_started_without_host_paths(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(main_mod, "TrackStager", _FakeStager)
    services = _services(False)
    with caplog.at_level(logging.INFO, logger="arm_backend"):
        services._start_stager()
    assert services._stager is None
    assert stager._active_stager is None
    assert "track stager is not started" in caplog.text


async def test_stopping_without_a_stager_is_a_no_op() -> None:
    await _services(False)._stop_stager()


async def test_stopping_asks_the_stager_to_stop_and_unpublishes_it(monkeypatch: pytest.MonkeyPatch) -> None:
    services = _services(True)
    fake = _FakeStager()
    services._stager = fake  # type: ignore[assignment]
    stager.set_active_stager(fake)  # type: ignore[arg-type]
    await services._stop_stager()
    assert fake.stopped and stager._active_stager is None


async def test_a_stager_that_will_not_stop_is_cancelled_after_the_timeout(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(main_mod, "STAGER_STOP_TIMEOUT_SECONDS", 0.01)
    services = _services(True)
    fake = _FakeStager()
    fake.hang = True
    services._stager = fake  # type: ignore[assignment]
    services._stager_task = asyncio.ensure_future(fake.run())
    with caplog.at_level(logging.WARNING, logger="arm_backend"):
        await services._stop_stager()
    await asyncio.sleep(0)
    assert services._stager_task.cancelled()
    assert "did not stop" in caplog.text


async def test_the_boot_sweep_commits_on_its_own_session(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    stage_id = await seed_stage(env, status=StageStatus.COPYING)
    monkeypatch.setattr(main_mod, "SessionLocal", env.factory)
    monkeypatch.setattr(main_mod, "settings", env.settings)
    assert await main_mod._sweep_track_stages() == 1
    async with env.factory() as db:
        assert (await db.get(TrackStage, stage_id)).status == StageStatus.PENDING  # type: ignore[union-attr]
