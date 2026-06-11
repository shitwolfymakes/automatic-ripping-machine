"""Apprise-introspected service catalog.

Built at runtime from apprise's plugin metadata (``template_tokens`` =
URL path components incl. required/private; ``template_args`` = query
params with types/defaults/values). A blocklist drops operational args;
a featured list pins common services for the UI's primary picker.
"""

from __future__ import annotations

import functools
import logging
from typing import Any

from apprise.manager_plugins import NotificationManager

logger = logging.getLogger("arm_backend.notifications.catalog")

# Args every apprise plugin inherits — never user-facing. `format` is
# intentionally NOT blocked (text/html/markdown is a meaningful choice).
_BLOCKED_ARGS = frozenset({"verify", "rto", "cto", "store", "tz", "overflow", "emojis"})

FEATURED_SERVICES = [
    "discord", "slack", "tgram", "pbul", "pover",
    "ntfys", "mailtos", "ifttt", "gotifys", "matrixs",
]


def _get_manager() -> NotificationManager:  # pragma: no cover
    """Indirection so tests can patch the manager."""
    mgr = NotificationManager()  # type: ignore[no-untyped-call]
    mgr.load_modules()  # type: ignore[no-untyped-call]
    return mgr


def _normalize_type(template_type: str) -> str:
    if template_type.startswith("choice"):
        return "choice"
    return template_type


def _build_field(key: str, spec: dict[str, Any]) -> dict[str, Any]:
    field: dict[str, Any] = {
        "key": key,
        "label": str(spec.get("name", key)),
        "type": _normalize_type(spec.get("type", "string")),
        "private": bool(spec.get("private", False)),
        "required": bool(spec.get("required", False)),
    }
    if "default" in spec:
        default = spec["default"]
        if hasattr(default, "value"):
            default = default.value
        field["default"] = default
    if field["type"] == "choice" and "values" in spec:
        field["values"] = sorted(str(v) for v in spec["values"])
    return field


def _service_id(plugin_cls: Any) -> str | None:
    scheme = plugin_cls.secure_protocol or plugin_cls.protocol
    if scheme is None:
        return None
    if isinstance(scheme, (list, tuple)):
        return str(scheme[0])
    return str(scheme)


def _build_service_entry(plugin_cls: Any) -> dict[str, Any] | None:
    service_id = _service_id(plugin_cls)
    if not service_id:
        return None
    required_fields = [
        _build_field(key, spec)
        for key, spec in (plugin_cls.template_tokens or {}).items()
        if spec.get("required")
    ]
    advanced_fields = [
        _build_field(key, spec)
        for key, spec in (plugin_cls.template_args or {}).items()
        if key not in _BLOCKED_ARGS and "alias_of" not in spec
    ]
    return {
        "id": service_id,
        "name": str(plugin_cls.service_name),
        "docs_url": plugin_cls.service_url or "",
        "url_scheme": service_id,
        "required_fields": required_fields,
        "advanced_fields": advanced_fields,
    }


@functools.lru_cache(maxsize=1)
def build_catalog() -> dict[str, Any]:
    """Build the service catalog from the live apprise plugin manager.

    Shape: ``{"featured": [id, ...], "services": [{...}, ...]}``. Services
    sorted by name; ``featured`` is the curated subset that exists.
    """
    mgr = _get_manager()
    services: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for plugin_cls in mgr.plugins():  # type: ignore[no-untyped-call]
        try:
            entry = _build_service_entry(plugin_cls)
        except Exception as exc:
            logger.debug("catalog: skipping plugin %s: %s", getattr(plugin_cls, "__name__", "<?>"), exc)
            continue
        if entry is None or entry["id"] in seen_ids:
            continue
        seen_ids.add(entry["id"])
        services.append(entry)
    services.sort(key=lambda s: s["name"].lower())
    return {
        "featured": [s for s in FEATURED_SERVICES if s in seen_ids],
        "services": services,
    }
