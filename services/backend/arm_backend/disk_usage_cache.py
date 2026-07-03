"""Cached disk usage via subprocess-based refresh (ported from neu).

statvfs() blocks indefinitely on NFS mounts in kernel D-state. This module
refreshes disk usage in a SUBPROCESS with a hard timeout; a stalled subprocess
is abandoned (unlike a thread, a D-state subprocess does not block the parent).
The endpoint reads only the cache and never calls statvfs() directly.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import threading
import time

log = logging.getLogger("arm_backend")

# path -> {"total","used","free","percent","ts"}
_cache: dict[str, dict[str, float]] = {}
_cache_lock = threading.Lock()

SUBPROCESS_TIMEOUT = 5  # seconds before abandoning a stalled statvfs subprocess
REFRESH_INTERVAL = 30  # seconds between background refreshes

_PROBE_SCRIPT = (
    "import os, json, sys\n"
    "p = sys.argv[1]\n"
    "s = os.statvfs(p)\n"
    "total = s.f_frsize * s.f_blocks\n"
    "free = s.f_frsize * s.f_bavail\n"
    "used = total - (s.f_frsize * s.f_bfree)\n"
    "pct = round(used / total * 100, 1) if total else 0.0\n"
    "print(json.dumps({'total': total, 'free': free, 'used': used, 'percent': pct}))\n"
)


def refresh_path(path: str) -> None:
    """Probe *path* in a subprocess and update the cache. Never raises."""
    try:
        result = subprocess.run(
            [sys.executable, "-c", _PROBE_SCRIPT, path],
            capture_output=True,
            text=True,
            timeout=SUBPROCESS_TIMEOUT,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.warning("disk usage probe failed for %s: %s", path, exc)
        return
    if result.returncode != 0 or not result.stdout.strip():
        return
    try:
        data = json.loads(result.stdout)
    except ValueError, TypeError:
        return
    data["ts"] = time.time()
    with _cache_lock:
        _cache[path] = data


def get_disk_usage(path: str) -> dict[str, float] | None:
    """Return cached disk usage for *path*, or None on a cache miss.

    Never blocks on NFS — reads only the in-process cache and returns
    immediately. The DiskRefresher background task is the sole writer;
    callers must not assume a value is available before the first refresh
    cycle completes.
    """
    with _cache_lock:
        entry = _cache.get(path)
    if entry and "total" in entry:
        return {k: entry[k] for k in ("total", "used", "free", "percent")}
    return None
