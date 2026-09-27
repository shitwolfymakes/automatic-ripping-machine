"""The lifespan's shutdown always clears the active-dispatcher holder, even
when a shutdown step raises: a stale holder would keep answering
`gpu_awaiting_probe` from a stopped dispatcher."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

import arm_backend.main as main_mod
from arm_backend import transcode_dispatcher as td

from .conftest import dispose_on_client_loop


def test_shutdown_clears_the_active_dispatcher_when_a_step_raises(
    e2e_app: tuple[FastAPI, AsyncEngine], monkeypatch: pytest.MonkeyPatch
) -> None:
    app, engine = e2e_app

    async def _boom(_self: object) -> None:
        raise RuntimeError("probe runner shutdown failed")

    monkeypatch.setattr(main_mod.GpuProbeRunner, "shutdown", _boom)

    with pytest.raises(RuntimeError, match="probe runner shutdown failed"):  # noqa: PT012
        with TestClient(app) as client:
            assert td._active_dispatcher is app.state.transcode_dispatcher
            dispose_on_client_loop(client, engine)

    assert td._active_dispatcher is None
