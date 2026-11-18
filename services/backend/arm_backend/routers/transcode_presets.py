"""Transcode preset CRUD. Built-in protection mirrors sessions.py and rip_presets.py."""

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_backend.auth import require_jwt, require_writer
from arm_backend.db import get_session
from arm_backend.handbrake_schema_store import SchemaStore, get_schema_store
from arm_backend.preset_views import normalise_settings, preset_view
from arm_common import ContainerFormat, Gpu, MediaType, Session, TranscodePreset, TranscodeTool, User
from arm_common.encoders import encoder_allowed_for_tool, encoder_supports_container, get_encoder
from arm_common.handbrake_schema.importer import ExportNotRecognised, import_export
from arm_common.handbrake_schema.types import HandbrakeSchema
from arm_common.handbrake_schema.validate import validate_settings
from arm_common.schemas.handbrake import ImportParseResponse
from arm_common.schemas import (
    HandbrakeSettings,
    TranscodePresetCreateRequest,
    TranscodePresetUpdateRequest,
    TranscodePresetView,
)

router = APIRouter(prefix="/api/transcode-presets", tags=["transcode-presets"])

_NO_SCHEMA = "No HandBrake schema loaded yet"
_MAX_IMPORT_BYTES = 1_048_576
# A patch touching one of these can change what the settings mean, so it re-validates them.
_SETTINGS_INPUTS = frozenset({"handbrake_settings", "tool", "encoder", "preset_ref"})
# Fields whose post-patch combination `_validate_encoder` checks.
_ENCODER_INPUTS = frozenset({"encoder", "tool", "container"})

# NOT NULL columns (name, tool, container, encoder): the update schema lets a
# client send null for them, which means "leave it as is".
_NOT_NULL_FIELDS = frozenset(c.key for c in inspect(TranscodePreset).columns if not c.nullable)


def _validate_encoder(encoder: str, tool: TranscodeTool, container: ContainerFormat) -> None:
    """422 unless `encoder` is a catalog id the preset's tool can run and its
    engine can write `container`."""
    try:
        get_encoder(encoder)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    if not encoder_allowed_for_tool(encoder, tool):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"encoder {encoder!r} is not valid for tool {tool.value}; only 'preset' is",
        )
    if not encoder_supports_container(encoder, container):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"encoder {encoder!r} cannot write {container.value}; AMD VAAPI encoders write mkv or mp4",
        )


def _check_settings(
    store: SchemaStore,
    *,
    tool: TranscodeTool,
    encoder: str,
    preset_ref: str | None,
    settings: dict[str, Any] | None,
) -> None:
    """422 with the issue list unless the settings a row will hold are valid; 503 when there are settings and
    no schema to check them against. A row without settings needs neither."""
    parsed = HandbrakeSettings.model_validate(settings) if settings else None
    if parsed is None or parsed.is_empty():
        return
    issues = validate_settings(_loaded(store), tool=tool, encoder_id=encoder, preset_ref=preset_ref, settings=parsed)
    if issues:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            {"issues": [issue.model_dump(mode="json") for issue in issues]},
        )


def _loaded(store: SchemaStore) -> HandbrakeSchema:
    schema = store.current()
    if schema is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, _NO_SCHEMA)
    return schema


async def _load_gpus(db: AsyncSession) -> list[Gpu]:
    return list((await db.execute(select(Gpu))).scalars().all())


def _decode_export(raw: bytes) -> Any:
    """The export's JSON, or 413 when the file is over 1 MB and 422 when it is not JSON."""
    if len(raw) > _MAX_IMPORT_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "The file is larger than 1 MB")
    try:
        return json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The file is not valid JSON") from exc


@router.post(
    "/import/parse",
    response_model=ImportParseResponse,
    openapi_extra={"requestBody": {"required": True, "content": {"application/json": {"schema": {}}}}},
)
async def parse_handbrake_export(
    request: Request,
    _: User = Depends(require_writer),
    store: SchemaStore = Depends(get_schema_store),
) -> ImportParseResponse:
    """Turn a HandBrake GUI export into preset proposals. Stores nothing."""
    body = _decode_export(await request.body())
    schema = _loaded(store)
    try:
        return import_export(schema, body)
    except ExportNotRecognised as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.get("", response_model=list[TranscodePresetView])
async def list_transcode_presets(
    media_type: MediaType | None = Query(default=None),
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
    store: SchemaStore = Depends(get_schema_store),
) -> list[TranscodePresetView]:
    stmt = select(TranscodePreset).order_by(col(TranscodePreset.name).asc())
    if media_type is not None:
        stmt = stmt.where(col(TranscodePreset.media_type) == media_type)
    result = await db.execute(stmt)
    gpus = await _load_gpus(db)
    schema = store.current()
    return [preset_view(row, schema, gpus) for row in result.scalars().all()]


@router.get("/{preset_id}", response_model=TranscodePresetView)
async def get_transcode_preset(
    preset_id: str,
    _: User = Depends(require_jwt),
    db: AsyncSession = Depends(get_session),
    store: SchemaStore = Depends(get_schema_store),
) -> TranscodePresetView:
    row = (await db.execute(select(TranscodePreset).where(col(TranscodePreset.id) == preset_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown transcode_preset_id: {preset_id}")
    return preset_view(row, store.current(), await _load_gpus(db))


@router.post("", response_model=TranscodePresetView, status_code=status.HTTP_201_CREATED)
async def create_transcode_preset(
    req: TranscodePresetCreateRequest,
    user: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
    store: SchemaStore = Depends(get_schema_store),
) -> TranscodePresetView:
    _validate_encoder(req.encoder, req.tool, req.container)
    settings = normalise_settings(req.handbrake_settings)
    _check_settings(store, tool=req.tool, encoder=req.encoder, preset_ref=req.preset_ref, settings=settings)
    row = TranscodePreset(
        name=req.name,
        media_type=req.media_type,
        is_builtin=False,
        tool=req.tool,
        preset_ref=req.preset_ref,
        handbrake_settings=settings,
        container=req.container,
        encoder=req.encoder,
        extra_args=req.extra_args,
        created_by_user_id=user.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return preset_view(row, store.current(), await _load_gpus(db))


def _patch_fields(req: TranscodePresetUpdateRequest) -> dict[str, Any]:
    """The fields the patch sets: null for a NOT NULL column means "leave it as is"; settings normalised."""
    fields = {k: v for k, v in req.model_dump(exclude_unset=True).items() if not (k in _NOT_NULL_FIELDS and v is None)}
    if "handbrake_settings" in fields:
        fields["handbrake_settings"] = normalise_settings(req.handbrake_settings)
    return fields


def _patched(fields: dict[str, Any], row: TranscodePreset, key: str) -> Any:
    """What the row will hold for `key` after the patch."""
    return fields.get(key, getattr(row, key))


def _validate_patch(store: SchemaStore, fields: dict[str, Any], row: TranscodePreset) -> None:
    """Validate what the row will hold after the patch, so switching the tool away from HandBrake cannot
    strand a codec encoder on it, a container change cannot pair a VAAPI encoder with WebM, and the
    settings are checked against the post-patch tool, encoder and base preset."""
    if fields.keys() & _ENCODER_INPUTS:
        _validate_encoder(
            _patched(fields, row, "encoder"), _patched(fields, row, "tool"), _patched(fields, row, "container")
        )
    if fields.keys() & _SETTINGS_INPUTS:
        _check_settings(
            store,
            tool=_patched(fields, row, "tool"),
            encoder=_patched(fields, row, "encoder"),
            preset_ref=_patched(fields, row, "preset_ref"),
            settings=_patched(fields, row, "handbrake_settings"),
        )


@router.patch("/{preset_id}", response_model=TranscodePresetView)
async def update_transcode_preset(
    preset_id: str,
    req: TranscodePresetUpdateRequest,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
    store: SchemaStore = Depends(get_schema_store),
) -> TranscodePresetView:
    row = (await db.execute(select(TranscodePreset).where(col(TranscodePreset.id) == preset_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown transcode_preset_id: {preset_id}")

    fields = _patch_fields(req)
    if row.is_builtin and fields:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="built-in transcode preset is read-only; create a new preset to customise",
        )
    _validate_patch(store, fields, row)

    for key, value in fields.items():
        setattr(row, key, value)
    await db.commit()
    await db.refresh(row)
    return preset_view(row, store.current(), await _load_gpus(db))


@router.delete("/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_transcode_preset(
    preset_id: str,
    _: User = Depends(require_writer),
    db: AsyncSession = Depends(get_session),
) -> None:
    row = (await db.execute(select(TranscodePreset).where(col(TranscodePreset.id) == preset_id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown transcode_preset_id: {preset_id}")
    if row.is_builtin:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="cannot delete built-in transcode preset",
        )

    refs = (
        await db.execute(select(Session.id, Session.name).where(col(Session.transcode_preset_id) == preset_id))
    ).all()
    if refs:
        names = ", ".join(r.name for r in refs)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"transcode preset is referenced by session(s): {names}",
        )

    await db.delete(row)
    await db.commit()
