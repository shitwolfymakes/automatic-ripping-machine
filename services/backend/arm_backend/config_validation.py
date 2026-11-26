"""Checks a config PATCH body, before anything is written."""

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import inspect as sa_inspect

from arm_common import Config
from arm_common.config_metadata import CONFIG_FIELD_META, ConfigFieldMeta


_NON_EDITABLE_KEYS = frozenset(m.key for m in CONFIG_FIELD_META if not m.editable)

_RANKED_META = {m.key: m for m in CONFIG_FIELD_META if m.type == "ranked"}
_ENUM_META = {m.key: m for m in CONFIG_FIELD_META if m.type == "enum" and m.key != "on_previously_ripped"}


def reject_non_editable_keys(raw: dict[str, Any]) -> None:
    forbidden = _NON_EDITABLE_KEYS & set(raw.keys())
    if forbidden:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"non-editable settings cannot be patched: {sorted(forbidden)}",
        )


def _validate_enum_field(key: str, meta: ConfigFieldMeta, fields: dict[str, Any], cfg: Config) -> None:
    if key not in fields:
        return
    value = fields[key]
    allowed = meta.enum_values or []
    if value is None or value not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} must be one of {', '.join(allowed)}"
        )
    required = (meta.enum_requires or {}).get(value)
    if required:
        # The key sent in this body counts; otherwise the stored one.
        present = fields[required] if required in fields else getattr(cfg, required, None)
        if not (present or "").strip():
            label = (meta.enum_labels or {}).get(value, value)
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key}: {label} needs its API key")


def _validate_enum_fields(fields: dict[str, Any], cfg: Config) -> None:
    for key, meta in _ENUM_META.items():
        _validate_enum_field(key, meta, fields, cfg)


def _validate_positive_ints(fields: dict[str, Any]) -> None:
    # The number inputs send null for an emptied box; these columns are NOT
    # NULL, so refuse it here rather than 500 on the commit.
    for key in (
        "drive_scan_interval_seconds",
        "drive_detected_prune_days",
        "max_parallel_transcodes",
        "thediscdb_refresh_days",
    ):
        if key in fields and (fields[key] is None or fields[key] < 1):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} must be a positive integer")


def _validate_manual_wait(fields: dict[str, Any]) -> None:
    if "manual_wait_seconds" in fields and (fields["manual_wait_seconds"] is None or fields["manual_wait_seconds"] < 0):
        # 0 is a real choice: no countdown, the held disc starts at once.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="manual_wait_seconds must be 0 or a positive integer"
        )


def _validate_on_previously_ripped(fields: dict[str, Any]) -> None:
    if "on_previously_ripped" in fields and fields["on_previously_ripped"] is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="on_previously_ripped must be hold, reject or rip"
        )


def _validate_iso_rip_cap(fields: dict[str, Any]) -> None:
    if "max_parallel_iso_rips" in fields:
        cap = fields["max_parallel_iso_rips"]
        if cap is None or isinstance(cap, bool) or not 1 <= cap <= 8:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="max_parallel_iso_rips must be 1 to 8")


def _validate_transcode_enabled_not_null(fields: dict[str, Any]) -> None:
    if "transcode_enabled" in fields and fields["transcode_enabled"] is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="transcode_enabled must be a boolean")


def _validate_ranked_fields(fields: dict[str, Any]) -> None:
    for key, meta in _RANKED_META.items():
        if key not in fields:
            continue
        values = fields[key]
        if values is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} must be a list")
        unknown = [v for v in values if v not in (meta.enum_values or [])]
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{key}: unknown value(s) {', '.join(unknown)}",
            )
        if len(set(values)) != len(values):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key}: duplicate values")


def _validate_episode_tolerance(fields: dict[str, Any], raw: dict[str, Any]) -> None:
    if "episode_match_tolerance_seconds" in fields:
        tol = fields["episode_match_tolerance_seconds"]
        # Pydantic's lax int validator accepts a JSON bool (bool is an int
        # subclass) and coerces it to 0/1 before `fields` sees it, so the
        # bool-ness check has to read the raw wire value, not `tol`.
        raw_tol = raw.get("episode_match_tolerance_seconds")
        if tol is None or isinstance(raw_tol, bool) or not 1 <= tol <= 1800:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="episode_match_tolerance_seconds must be 1 to 1800"
            )


def _validate_auto_apply_flags(fields: dict[str, Any]) -> None:
    # The checkbox inputs send null for a cleared tri-state; these columns are
    # NOT NULL, so refuse it here rather than 500 on the commit.
    for key in ("episode_auto_apply", "movie_auto_apply", "music_auto_apply", "crc64service_enabled"):
        if key in fields and fields[key] is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} must be true or false")


def _validate_not_null_columns(fields: dict[str, Any]) -> None:
    # Catch-all for the rest of the NOT NULL columns: a JSON null would
    # otherwise reach the commit and 500. The checks above keep their
    # field-specific messages.
    columns = sa_inspect(Config).columns
    for key, value in fields.items():
        if value is None and key in columns and not columns[key].nullable:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{key} must not be null")


def validate_config_update(fields: dict[str, Any], raw: dict[str, Any], cfg: Config) -> None:
    _validate_enum_fields(fields, cfg)
    _validate_positive_ints(fields)
    _validate_manual_wait(fields)
    _validate_on_previously_ripped(fields)
    _validate_iso_rip_cap(fields)
    _validate_transcode_enabled_not_null(fields)
    _validate_ranked_fields(fields)
    _validate_episode_tolerance(fields, raw)
    _validate_auto_apply_flags(fields)
    _validate_not_null_columns(fields)
