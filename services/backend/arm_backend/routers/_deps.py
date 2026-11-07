"""Shared FastAPI dependencies that hand a router the app's WS hub and stage runner."""

from __future__ import annotations

from fastapi import Request

from arm_backend.identity.stage_runner import EpisodeStageRunner
from arm_backend.ws import WSHub


def get_hub(request: Request) -> WSHub:
    hub: WSHub = request.app.state.ws_hub
    return hub


def get_stage_runner(request: Request) -> EpisodeStageRunner | None:
    """None when `app.state` carries no runner (e.g. an existing router test
    that never set one up) — callers then just skip scheduling."""
    return getattr(request.app.state, "episode_stage", None)
