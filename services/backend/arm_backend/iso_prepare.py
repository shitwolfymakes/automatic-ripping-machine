"""What each ISO ripper is doing before identify creates its job.

An ISO rip has no job while its ripper scans the image or unpacks it for
MakeMKV (`arm_ripper.iso_extract`), which can take half an hour for a
Blu-ray over a network share. The ripper reports its phase here
(`POST /api/ripper/iso-prepare`) and the dashboard lists it
(`GET /api/iso/rips/preparing`).

Held in memory on purpose: it is transient, the backend is one process, and
the ripper re-sends its current phase as a keepalive, so a backend restart
loses it for one interval at most. A status the ripper stopped refreshing
ages out after `STALE_SECONDS`; identify (the job exists now) and retire
(the rip is over) drop it explicitly. Dependency-free, so routers and
`iso_rips` can import it without a cycle.
"""

from __future__ import annotations

from datetime import UTC, datetime

from arm_common.schemas import IsoPrepareReport, IsoPrepareView

# The ripper's keepalive is 15 s; four missed beats means it is gone.
STALE_SECONDS = 60

_views: dict[str, IsoPrepareView] = {}


def record(report: IsoPrepareReport) -> IsoPrepareView:
    view = IsoPrepareView(**report.model_dump(), updated_at=datetime.now(UTC))
    _views[report.drive_id] = view
    return view


def clear(drive_id: str) -> None:
    _views.pop(drive_id, None)


def clear_all() -> None:
    _views.clear()


def views() -> list[IsoPrepareView]:
    """Every live status, oldest first; stale ones are dropped on the way."""
    now = datetime.now(UTC)
    for drive_id, view in list(_views.items()):
        if (now - view.updated_at).total_seconds() > STALE_SECONDS:
            del _views[drive_id]
    return sorted(_views.values(), key=lambda v: v.updated_at)
