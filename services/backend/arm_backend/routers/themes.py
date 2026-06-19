"""Theme management endpoints.

Built-ins serve read-only from the package; user themes round-trip through
settings.ARM_THEMES_PATH. /css is intentionally unauthenticated (the UI fetches
it with a bare <link>/fetch, no bearer); all other routes are JWT-gated.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse

from arm_backend import theme_service
from arm_backend.auth import require_jwt
from arm_common import User

router = APIRouter(prefix="/api/themes", tags=["themes"])

_404: dict[int | str, dict[str, Any]] = {404: {"description": "Theme not found"}}
_400: dict[int | str, dict[str, Any]] = {400: {"description": "Invalid request"}}


@router.get("")
async def list_themes(_: User = Depends(require_jwt)) -> list[dict[str, Any]]:
    """List all themes (metadata only, no CSS)."""
    return theme_service.get_all_themes()


@router.get("/{theme_id}", responses=_404)
async def get_theme(theme_id: str, _: User = Depends(require_jwt)) -> dict[str, Any]:
    """Full theme data including CSS."""
    theme = theme_service.get_theme(theme_id)
    if not theme:
        raise HTTPException(status_code=404, detail=f"Theme '{theme_id}' not found")
    return theme


# Intentionally unauthenticated: fetched by the UI with a bare fetch (no bearer
# header possible), like routers/images.py's proxy. Returns only CSS text.
@router.get("/{theme_id}/css", responses=_404)
async def get_theme_css(theme_id: str) -> PlainTextResponse:
    """Theme CSS as text/css. 404 if the theme is unknown or has no CSS."""
    theme = theme_service.get_theme(theme_id)
    if not theme:
        raise HTTPException(status_code=404, detail=f"Theme '{theme_id}' not found")
    css = theme.get("css", "")
    if not css.strip():
        raise HTTPException(status_code=404, detail=f"Theme '{theme_id}' has no custom CSS")
    return PlainTextResponse(content=css, media_type="text/css")


@router.post("", status_code=201, responses=_400)
async def upload_theme(
    theme_json: Annotated[UploadFile, File(description="Theme JSON file")],
    theme_css: Annotated[str, Form(description="Optional custom CSS")] = "",
    _: User = Depends(require_jwt),
) -> dict[str, Any]:
    """Upload a user theme (JSON file + optional CSS)."""
    try:
        data = json.loads(await theme_json.read())
    except json.JSONDecodeError, UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file") from None
    try:
        return theme_service.save_user_theme(data, css=theme_css)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"Could not write theme: {exc.strerror or exc}") from exc


@router.delete("/{theme_id}", responses=_400)
async def delete_theme(theme_id: str, _: User = Depends(require_jwt)) -> dict[str, Any]:
    """Delete a user theme. Built-ins cannot be deleted."""
    try:
        deleted = theme_service.delete_user_theme(theme_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete '{theme_id}': built-in theme or not found",
        )
    return {"detail": f"Theme '{theme_id}' deleted"}
