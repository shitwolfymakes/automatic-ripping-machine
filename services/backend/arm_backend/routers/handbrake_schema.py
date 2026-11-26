"""HandBrake schema endpoints: the slim view for the UI, one built-in preset, and a refresh.

Both reads carry `ETag` = the schema's `content_hash`; the full dump never leaves the Backend.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel

from arm_backend.auth import require_jwt, require_writer
from arm_backend.handbrake_schema_runner import HandbrakeSchemaRunner
from arm_backend.handbrake_schema_store import SchemaStore, get_schema_store
from arm_backend.routers._deps import get_schema_runner
from arm_common import User
from arm_common.handbrake_schema.slim import slim_view
from arm_common.handbrake_schema.types import HandbrakeSchema
from arm_common.schemas import HandbrakeSchemaSlimView

router = APIRouter(prefix="/api/handbrake-schema", tags=["handbrake-schema"])


class HandbrakeSchemaRefreshResult(BaseModel):
    ok: bool
    error: str | None = None


def _loaded(store: SchemaStore) -> HandbrakeSchema:
    schema = store.current()
    if schema is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No HandBrake schema loaded yet")
    return schema


def _etag(schema: HandbrakeSchema) -> str:
    return f'"{schema.content_hash}"'


def _matches(if_none_match: str | None, schema: HandbrakeSchema) -> bool:
    """Does the client's `If-None-Match` name this schema (with or without quotes)?"""
    if if_none_match is None:
        return False
    candidates = {part.strip().removeprefix("W/").strip('"') for part in if_none_match.split(",")}
    return schema.content_hash in candidates


@router.get("", response_model=HandbrakeSchemaSlimView)
async def get_slim_view(
    response: Response,
    if_none_match: str | None = Header(default=None),
    _user: User = Depends(require_jwt),
    store: SchemaStore = Depends(get_schema_store),
) -> Any:
    schema = _loaded(store)
    if _matches(if_none_match, schema):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": _etag(schema)})
    response.headers["ETag"] = _etag(schema)
    return slim_view(schema)


@router.get("/builtin/{name}", response_model=dict[str, Any])
async def get_builtin(
    name: str,
    response: Response,
    _user: User = Depends(require_jwt),
    store: SchemaStore = Depends(get_schema_store),
) -> dict[str, Any]:
    schema = _loaded(store)
    preset = schema.builtin_presets.get(name)
    if preset is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, f"HandBrake {schema.handbrake_tag} has no built-in preset named '{name}'"
        )
    response.headers["ETag"] = _etag(schema)
    return preset


@router.post("/refresh", response_model=HandbrakeSchemaRefreshResult)
async def refresh(
    _user: User = Depends(require_writer),
    runner: HandbrakeSchemaRunner | None = Depends(get_schema_runner),
) -> HandbrakeSchemaRefreshResult:
    if runner is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "No HandBrake schema runner in this Backend")
    error = await runner.refresh()
    return HandbrakeSchemaRefreshResult(ok=error is None, error=error)
