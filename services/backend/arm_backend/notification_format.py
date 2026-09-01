"""Title/body formatting for outbound notifications.

`format_event(event, job)` renders the built-in default template for the
event (from `notification_events.EVENT_VOCAB`) through `event_context`.
`resolve_title_body(... context=...)` applies a channel's per-event override
through the same context. One renderer → the advertised variables, the
defaults, and what an override can inject are provably the same set.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from arm_backend.notification_events import EVENT_VOCAB
from arm_common import Event, Job


class TemplateRenderError(ValueError):
    """A template referenced a variable the event doesn't carry."""


def _str(value: object) -> str:
    return "" if value is None else str(value)


def context_from_message(
    *,
    event_type: str,
    job: Job | None,
    job_id: str | None,
    payload: dict[str, Any],
    occurred_at: datetime | None = None,
) -> dict[str, str]:
    """Flat, string-valued variable map for `str.format_map`.

    Common vars (always present, empty when unknown) + the event family's
    payload vars. Pre-stringified so templates need no format specs and a
    missing value renders as ''.

    Accepts primitive arguments so both the message path (listeners) and the
    event path (`event_context`) produce identical dicts.
    """
    payload = payload or {}
    ctx: dict[str, str] = {
        "job_title": _str(job.title if job else None),
        "job_year": _str(job.year if job else None),
        "job_disc_type": _str(job.disc_type.value if job and job.disc_type else None),
        "drive_id": _str(payload.get("drive_id") or (job.drive_id if job else None)),
        "job_id": _str(job_id),
        "event_type": _str(event_type),
        "occurred_at": occurred_at.isoformat() if occurred_at else "",
    }
    spec = EVENT_VOCAB.get(event_type)
    if spec is not None:
        for var in spec.variables:
            if var not in ctx:
                ctx[var] = _str(payload.get(var))
    return ctx


def event_context(event: Event, job: Job | None) -> dict[str, str]:
    """Render context for an event; delegates to `context_from_message`."""
    return context_from_message(
        event_type=event.event_type,
        job=job,
        job_id=event.job_id,
        payload=event.payload_json,
        occurred_at=event.emitted_at,
    )


def resolve_title_body(
    *,
    event_type: str,
    default_title: str,
    default_body: str,
    template: dict[str, str | None] | None,
    context: dict[str, str],
) -> tuple[str, str]:
    """Render (title, body) for an event, applying a per-field override.

    A template field that is missing/None falls back to the default. Both
    are interpolated via `str.format_map`. An unknown variable raises
    `TemplateRenderError` (never a silent partial render).
    """
    title_tmpl = (template or {}).get("title") or default_title
    body_tmpl = (template or {}).get("body") or default_body
    try:
        title = title_tmpl.format_map(context)
        body = body_tmpl.format_map(context)
    except (KeyError, IndexError, ValueError) as exc:
        raise TemplateRenderError(f"template for {event_type} references an unknown variable: {exc}") from exc
    # Cap output length to prevent width-spec amplification (e.g. {job_title:>999999}).
    _TITLE_CAP = 4000
    _BODY_CAP = 16000
    if len(title) > _TITLE_CAP:
        title = title[:_TITLE_CAP] + "…"
    if len(body) > _BODY_CAP:
        body = body[:_BODY_CAP] + "…"
    return title, body


def synthetic_test_message(event_type: str) -> tuple[str, str]:
    """A placeholder (title, body) for test-sends when no context is built."""
    spec = EVENT_VOCAB.get(event_type)
    if spec is None:
        return "ARM: test notification", f"ARM test notification ({event_type})"
    return spec.label, f"ARM test notification ({event_type})"


def format_event(event: Event, job: Job | None) -> tuple[str, str]:
    """Return the built-in default (title, body) for an event.

    Renders the vocab default templates through `event_context`. Raises
    `KeyError` for an unknown event type (the dispatcher only feeds
    `NOTABLE_EVENT_TYPES`, so that would be a code bug, not user input).
    """
    spec = EVENT_VOCAB[event.event_type]
    ctx = event_context(event, job)
    return resolve_title_body(
        event_type=event.event_type,
        default_title=spec.default_title,
        default_body=spec.default_body,
        template=None,
        context=ctx,
    )
