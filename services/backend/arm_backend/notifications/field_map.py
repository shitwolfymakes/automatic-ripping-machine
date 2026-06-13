"""Apprise per-field masking, merge, and compose helpers.

Secret (``private``) fields are masked with ``_HIDDEN_LITERAL`` on GET;
a PATCH that sends ``_HIDDEN_LITERAL`` for a private field preserves the
stored secret. The URL is recomposed server-side from the merged fields,
so the composer never sees a partial credential set.
"""

from __future__ import annotations

from typing import Any

from arm_common.secrets import HIDDEN_SECRET
from arm_backend.notifications.catalog import build_catalog
from arm_backend.notifications.url_composer import compose_apprise_url

_HIDDEN_LITERAL = HIDDEN_SECRET


def _service(service_id: str | None) -> dict[str, Any] | None:
    if not service_id:
        return None
    cat = build_catalog()
    return next((s for s in cat["services"] if s["id"] == service_id), None)


def apprise_field_is_private(service_id: str | None, key: str) -> bool | None:
    """True/False if the field is found in the catalog; None for unknown
    service or key."""
    svc = _service(service_id)
    if svc is None:
        return None
    for f in [*svc.get("required_fields", []), *svc.get("advanced_fields", [])]:
        if f["key"] == key:
            return bool(f.get("private"))
    return None


def compose_url_from_fields(service_id: str | None, fields: dict[str, Any]) -> str | None:
    """Compose an apprise url from a flat field map, partitioning into
    required vs advanced by the catalog. None if service unknown/missing."""
    svc = _service(service_id)
    if svc is None:
        return None
    required_keys = {f["key"] for f in svc.get("required_fields", [])}
    return compose_apprise_url(
        service_id=service_id,  # type: ignore[arg-type]  # _service guarantees non-None
        required={k: v for k, v in fields.items() if k in required_keys},
        advanced={k: v for k, v in fields.items() if k not in required_keys},
    )


def mask_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with private apprise field values replaced by the
    masked literal. Non-apprise / no-fields configs pass through."""
    if not cfg:
        return cfg
    if cfg.get("type") != "apprise" or not isinstance(cfg.get("fields"), dict):
        return cfg
    out = dict(cfg)
    service_id = cfg.get("service_id")
    masked: dict[str, Any] = {}
    for k, v in cfg["fields"].items():
        if v and apprise_field_is_private(service_id, k) is True:
            masked[k] = _HIDDEN_LITERAL
        else:
            masked[k] = v
    out["fields"] = masked
    return out


def merge_patch_config(existing: dict[str, Any], incoming: dict[str, Any] | None) -> dict[str, Any]:
    """Merge an incoming apprise config onto the stored one.

    For each incoming field: ``_HIDDEN_LITERAL`` on a private field keeps
    the stored value; anything else overwrites. Then recompose ``url``
    from the merged fields. Non-apprise or fields-less incoming is
    returned as-is.
    """
    if incoming is None:
        return existing
    if not (
        existing.get("type") == "apprise"
        and incoming.get("type") == "apprise"
        and isinstance(incoming.get("fields"), dict)
    ):
        return incoming
    merged = dict(incoming)
    service_id = incoming.get("service_id") or existing.get("service_id")
    merged_fields: dict[str, Any] = dict(existing.get("fields") or {})
    for k, v in incoming["fields"].items():
        if v == _HIDDEN_LITERAL and apprise_field_is_private(service_id, k) is True:
            continue  # keep stored secret
        merged_fields[k] = v
    merged["fields"] = merged_fields
    merged["service_id"] = service_id
    composed = compose_url_from_fields(service_id, merged_fields)
    if composed is not None:
        merged["url"] = composed
    return merged
