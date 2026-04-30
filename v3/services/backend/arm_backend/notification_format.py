"""Phase 11 — title/body formatting for outbound notifications.

`format_event(event, job)` is a pure function that turns one persisted
`Event` row plus its (optional) `Job` into an Apprise (title, body) pair.
The dispatcher loads `Job` once per event so the formatter has access to
the human-readable disc title — but cascade-deletes can leave an event
with `job_id` pointing at nothing, so callers may pass `job=None` and
the formatter falls back to payload-only fields.
"""

from __future__ import annotations

from arm_common import Event, Job


def _disc_label(event: Event, job: Job | None) -> str:
    """Human label for the disc the event refers to."""
    if job is not None and job.title:
        return f"{job.title} ({job.year})" if job.year else job.title
    if event.job_id:
        return f"job={event.job_id}"
    return "(unknown disc)"


def _rip_body(event: Event, job: Job | None) -> str:
    payload = event.payload_json or {}
    drive_id = payload.get("drive_id")
    done = payload.get("tracks_done")
    failed = payload.get("tracks_failed")
    total = payload.get("tracks_total")
    parts: list[str] = [_disc_label(event, job)]
    if drive_id:
        parts.append(f"drive={drive_id}")
    if total is not None:
        if failed:
            parts.append(f"{done}/{total} tracks done, {failed} failed")
        else:
            parts.append(f"{done}/{total} tracks")
    return " — ".join(parts)


def _session_body(event: Event, job: Job | None) -> str:
    payload = event.payload_json or {}
    session_id = payload.get("session_id")
    app_id = payload.get("session_application_id")
    status = payload.get("status")
    parts: list[str] = [_disc_label(event, job)]
    if session_id:
        parts.append(f"session={session_id}")
    if app_id:
        parts.append(f"application={app_id}")
    if status:
        parts.append(f"status={status}")
    return " — ".join(parts)


_TITLES: dict[str, str] = {
    "rip.completed": "ARM: rip completed",
    "rip.failed": "ARM: rip failed",
    "rip.partial": "ARM: rip partial",
    "session.completed": "ARM: session completed",
    "session.failed": "ARM: session failed",
    "session.partial": "ARM: session partial",
}


def format_event(event: Event, job: Job | None) -> tuple[str, str]:
    """Return (title, body) for an outbound notification.

    Raises `KeyError` for unknown event types; the dispatcher only feeds
    types from `NOTIFIABLE_EVENT_TYPES`, so an unknown type here is a
    code bug, not user input.
    """
    title = _TITLES[event.event_type]
    if event.event_type.startswith("rip."):
        return title, _rip_body(event, job)
    return title, _session_body(event, job)
