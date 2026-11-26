"""Shared FastAPI dependencies that hand a router the app's WS hub and stage runner."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from arm_backend.handbrake_schema_runner import HandbrakeSchemaRunner
from arm_backend.identity.stage_runner import EpisodeStageRunner
from arm_backend.ripper_manager import RipperManager
from arm_backend.ws import WSHub


def get_hub(request: Request) -> WSHub:
    hub: WSHub = request.app.state.ws_hub
    return hub


def get_stage_runner(request: Request) -> EpisodeStageRunner | None:
    """None when `app.state` carries no runner (e.g. an existing router test
    that never set one up) — callers then just skip scheduling."""
    return getattr(request.app.state, "episode_stage", None)


def get_schema_runner(request: Request) -> HandbrakeSchemaRunner | None:
    """None when `app.state` carries no runner (e.g. a narrow router test) — callers then skip the refresh."""
    return getattr(request.app.state, "handbrake_schema_runner", None)


def require_ripper_manager(request: Request) -> RipperManager:
    """The app's ripper manager, or a 503 when it is missing or disabled."""
    manager: RipperManager | None = getattr(request.app.state, "ripper_manager", None)
    if manager is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ripper manager unavailable: docker socket not available",
        )
    if not manager.host_paths_set():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ripper manager disabled: ARM_HOST_*_PATH not set",
        )
    return manager
