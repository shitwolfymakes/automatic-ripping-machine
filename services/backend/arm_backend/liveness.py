"""Single source of truth for host/drive staleness.

A drive or host whose last heartbeat is older than STALE_AFTER is considered
stale (its ripper likely stopped heart-beating). Deliberately looser than the
90s manual-trigger pre-check window (jobs.py `_MEDIA_STATUS_FRESHNESS`): that
gate fast-fails a rip on a momentarily-quiet drive, whereas this is an
operator-facing health/telemetry view that shouldn't flap on one missed beat.
"""

from datetime import timedelta

STALE_AFTER = timedelta(minutes=5)
