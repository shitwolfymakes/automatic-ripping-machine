"""Service utils.

Functions that need to be called from anywhere in the service should go here.
"""

import logging
import os

from arm_backend.config import settings, staging_root


logger = logging.getLogger(__name__)


def default_roots() -> dict[str, str]:
    # LOG_DIR is the fixed `/logs` mount throughout v3 (see logs.py /
    # log_tailer.py) — convention-over-config, not a Settings field.
    return {
        "MEDIA_ROOT": settings.MEDIA_ROOT,
        "RAW_ROOT": settings.RAW_ROOT,
        "LOG_DIR": "/logs",
        "STAGING_ROOT": str(staging_root(settings)),
    }


def disk_refresh_roots(injected: dict[str, str] | None) -> list[str]:
    """The folders whose disk usage the refresher caches: the injected roots when given,
    else the default roots plus the ISO ingress folder."""
    if injected:
        return list(injected.values())
    return [*default_roots().values(), settings.ISO_INGRESS_ROOT]


def ensure_roots(roots: dict[str, str]) -> None:
    """Silently create any missing root dir. Never raises: a broken mount
    must not crash-loop the API (the container entrypoint's writability
    guard owns the fatal cases); the failure stays visible as
    exists=False in the diagnostics report."""
    for name, path in roots.items():
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as exc:
            logger.warning("cannot create %s (%s): %s", name, path, exc)
