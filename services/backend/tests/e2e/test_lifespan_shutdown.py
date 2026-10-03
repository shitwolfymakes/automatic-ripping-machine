"""The lifespan always clears the active-dispatcher holder, whether startup
or shutdown fails, and one failing shutdown step does not skip the rest: a
stale holder would keep answering `gpu_awaiting_probe` from a stopped
dispatcher."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

import arm_backend.main as main_mod
from arm_backend import transcode_dispatcher as td

from .conftest import dispose_on_client_loop


def test_a_failing_shutdown_step_does_not_skip_the_rest(
    e2e_app: tuple[FastAPI, AsyncEngine], monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    app, engine = e2e_app

    async def _boom(_self: object) -> None:
        raise RuntimeError("probe runner shutdown failed")

    monkeypatch.setattr(main_mod.GpuProbeRunner, "shutdown", _boom)

    with caplog.at_level("ERROR", logger="arm_backend"), TestClient(app) as client:
        assert td._active_dispatcher is app.state.transcode_dispatcher
        dispose_on_client_loop(client, engine)

    assert "stopping the gpu probe runner failed" in caplog.text
    assert "probe runner shutdown failed" in caplog.text
    # The steps after the failing one still ran.
    assert app.state.transcode_dispatcher._stop.is_set()
    assert app.state.http.is_closed
    assert td._active_dispatcher is None


def test_a_startup_failure_after_the_dispatcher_is_set_clears_the_holder(
    e2e_app: tuple[FastAPI, AsyncEngine], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, _engine = e2e_app
    seen: list[object] = []

    def _boom(_self: object) -> None:
        seen.append(td._active_dispatcher)
        raise RuntimeError("boot pass failed to start")

    monkeypatch.setattr(main_mod.GpuProbeRunner, "start_boot_pass", _boom)

    with pytest.raises(RuntimeError, match="boot pass failed to start"), TestClient(app):
        pass

    assert seen == [app.state.transcode_dispatcher]
    assert td._active_dispatcher is None


def test_disk_refresher_stop_timeout_falls_back_to_cancel(
    e2e_app: tuple[FastAPI, AsyncEngine], monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the disk refresher doesn't wind down within the grace period, the
    lifespan cancels its task outright and still finishes the remaining
    shutdown steps."""
    import asyncio

    app, engine = e2e_app
    real_wait_for = asyncio.wait_for
    timed_out: list[str] = []

    async def _wait_for(fut: object, timeout: float | None = None) -> object:
        get_coro = getattr(fut, "get_coro", None)
        if get_coro is not None and getattr(get_coro(), "__qualname__", "") == "DiskRefresher.run":
            timed_out.append("disk_refresher")
            raise TimeoutError
        return await real_wait_for(fut, timeout=timeout)  # type: ignore[arg-type]

    monkeypatch.setattr(main_mod.asyncio, "wait_for", _wait_for)

    with TestClient(app) as client:
        dispose_on_client_loop(client, engine)

    assert timed_out == ["disk_refresher"]
    assert app.state.transcode_dispatcher._stop.is_set()
    assert app.state.http.is_closed
    assert td._active_dispatcher is None
