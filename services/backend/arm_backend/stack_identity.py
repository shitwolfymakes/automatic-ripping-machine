"""The uid/gid a spawned container drops to: the stack's own PUID/PGID (and
CDROM_GID for a ripper), each replaced by a non-empty override."""

from __future__ import annotations

from collections.abc import Mapping

from arm_backend.config import Settings


def stack_identity_env(
    settings: Settings, *, include_cdrom: bool = False, overrides: Mapping[str, str] | None = None
) -> dict[str, str]:
    """The identity env for a spawned container; an empty value is left out so
    the entrypoint's own default applies."""
    keys = ("PUID", "PGID", "CDROM_GID") if include_cdrom else ("PUID", "PGID")
    chosen = overrides or {}
    env: dict[str, str] = {}
    for key in keys:
        value = chosen.get(key) or getattr(settings, key)
        if value:
            env[key] = value
    return env
