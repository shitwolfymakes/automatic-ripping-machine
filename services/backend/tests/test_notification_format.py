"""Phase 11 — pure-function tests for `format_event`."""

from __future__ import annotations

from datetime import UTC, datetime

from arm_backend.notification_format import format_event
from arm_common import DiscType, Event, Job, JobStatus


def _job(title: str | None = "Iron Man", year: int | None = 2008) -> Job:
    return Job(
        id="job_01JZXR7K3M5Q8N4VWA00000001",
        drive_id="drv_x",
        disc_type=DiscType.DVD,
        title=title,
        year=year,
        status=JobStatus.RIPPED,
        metadata_json={},
        resumed_from_crash=False,
    )


def _event(event_type: str, payload: dict[str, object]) -> Event:
    return Event(
        id="evt_x",
        event_type=event_type,
        emitted_at=datetime.now(UTC),
        job_id="job_01JZXR7K3M5Q8N4VWA00000001",
        track_id=None,
        session_application_id=None,
        payload_json=payload,
        notified_at=None,
    )


def test_rip_completed_title_and_body() -> None:
    event = _event(
        "rip.completed",
        {"drive_id": "drv_x", "tracks_done": 3, "tracks_failed": 0, "tracks_total": 3},
    )
    title, body = format_event(event, _job())
    # New vocab default: title includes job_title; body is a rendered sentence.
    assert title == "ARM: rip completed — Iron Man"
    assert "Iron Man" in body
    assert "drv_x" in body
    assert "3/3" in body


def test_rip_partial_lists_failed_count() -> None:
    event = _event(
        "rip.partial",
        {"drive_id": "drv_x", "tracks_done": 2, "tracks_failed": 1, "tracks_total": 3},
    )
    title, body = format_event(event, _job())
    # New vocab default: title includes job_title.
    assert title == "ARM: rip partial — Iron Man"
    assert "2/3" in body and "1 failed" in body


def test_session_completed_includes_session_id_and_status() -> None:
    event = _event(
        "session.completed",
        {
            "session_id": "ses_x",
            "session_application_id": "sap_x",
            "job_id": "job_01JZXR7K3M5Q8N4VWA00000001",
            "status": "done",
        },
    )
    title, body = format_event(event, _job())
    # New vocab default: title includes job_title; body contains status.
    assert title == "ARM: session completed — Iron Man"
    assert "done" in body


def test_falls_back_to_payload_when_job_is_none() -> None:
    event = _event(
        "rip.completed",
        {"drive_id": "drv_x", "tracks_done": 1, "tracks_total": 1},
    )
    title, body = format_event(event, None)
    # New vocab default: job_title is "" when no job, title ends with " — ".
    assert title == "ARM: rip completed — "
    # No job title in body, but drive is still present.
    assert "drv_x" in body
    assert "1/1" in body


def test_year_omitted_when_none() -> None:
    event = _event(
        "rip.completed",
        {"drive_id": "drv_x", "tracks_done": 1, "tracks_total": 1},
    )
    title, body = format_event(event, _job(title="My Home Movie", year=None))
    # New vocab default: title includes job_title without year.
    assert title == "ARM: rip completed — My Home Movie"
    assert "My Home Movie" in body
    assert "(None)" not in body


def test_resolve_title_body_uses_override() -> None:
    from arm_backend.notification_format import resolve_title_body

    # Use a context with known keys; the title override uses a known var.
    ctx = {"job_title": "Dune", "drive_id": "sr0"}
    title, body = resolve_title_body(
        event_type="rip.completed",
        default_title="ARM: rip completed",
        default_body="disc",
        template={"title": "Custom {job_title}", "body": None},
        context=ctx,
    )
    assert title == "Custom Dune"
    assert body == "disc"  # body falls back to default when override is None


def test_resolve_title_body_no_template() -> None:
    from arm_backend.notification_format import resolve_title_body

    ctx: dict[str, str] = {}
    title, body = resolve_title_body(
        event_type="rip.completed", default_title="T", default_body="B", template=None, context=ctx
    )
    assert (title, body) == ("T", "B")


def test_synthetic_test_message() -> None:
    from arm_backend.notification_format import synthetic_test_message

    title, body = synthetic_test_message("rip.completed")
    assert "test" in title.lower() or "test" in body.lower()


def test_synthetic_test_message_unknown_type() -> None:
    from arm_backend.notification_format import synthetic_test_message

    title, body = synthetic_test_message("totally.unknown.event")
    assert title == "ARM: test notification"
    assert "totally.unknown.event" in body


# --- event_context + interpolation (Task 2) -------------------------------
from arm_backend.notification_format import (  # noqa: E402
    TemplateRenderError,
    event_context,
    resolve_title_body,
)


def test_event_context_rip_has_common_and_payload_vars():
    ev = _event(
        "rip.completed",
        {"drive_id": "sr0", "status": "ripped", "tracks_done": 3, "tracks_failed": 0, "tracks_total": 3},
    )
    ctx = event_context(ev, _job(title="Iron Man", year=2008))
    assert ctx["job_title"] == "Iron Man"
    assert ctx["job_year"] == "2008"
    assert ctx["drive_id"] == "sr0"
    assert ctx["tracks_done"] == "3" and ctx["tracks_total"] == "3"
    assert ctx["event_type"] == "rip.completed"
    assert ctx["occurred_at"]  # non-empty ISO


def test_event_context_missing_job_and_payload_are_empty_strings():
    ev = _event("rip.completed", {})
    ctx = event_context(ev, None)
    assert ctx["job_title"] == ""
    assert ctx["tracks_total"] == ""
    assert ctx["drive_id"] == ""


def test_resolve_title_body_renders_override_with_vars():
    ev = _event("rip.completed", {"drive_id": "sr0", "tracks_done": 2, "tracks_failed": 0, "tracks_total": 2})
    ctx = event_context(ev, _job(title="Dune"))
    title, body = resolve_title_body(
        event_type="rip.completed",
        default_title="d-title",
        default_body="d-body",
        template={"title": "Done: {job_title}", "body": "{tracks_done}/{tracks_total} on {drive_id}"},
        context=ctx,
    )
    assert title == "Done: Dune"
    assert body == "2/2 on sr0"


def test_resolve_title_body_falls_back_to_default_per_field():
    ctx = event_context(_event("rip.completed", {}), _job(title="Dune"))
    title, body = resolve_title_body(
        event_type="rip.completed",
        default_title="default {job_title}",
        default_body="default body",
        template={"title": None, "body": "custom"},
        context=ctx,
    )
    assert title == "default Dune"
    assert body == "custom"


def test_resolve_title_body_unknown_variable_raises():
    ctx = event_context(_event("rip.completed", {}), _job())
    try:
        resolve_title_body(
            event_type="rip.completed",
            default_title="t",
            default_body="{nope}",
            template=None,
            context=ctx,
        )
        raised = False
    except TemplateRenderError:
        raised = True
    assert raised


def test_format_event_renders_vocab_default():
    ev = _event("rip.completed", {"drive_id": "sr0", "tracks_done": 3, "tracks_failed": 0, "tracks_total": 3})
    title, body = format_event(ev, _job(title="Iron Man"))
    assert "rip completed" in title.lower()
    assert "Iron Man" in body and "sr0" in body and "3/3" in body


def test_context_from_message_matches_event_context():
    from arm_backend.notification_format import context_from_message

    ev = _event("rip.completed", {"drive_id": "sr0", "tracks_total": 2, "tracks_done": 2, "tracks_failed": 0})
    job = _job(title="Dune")
    a = event_context(ev, job)
    b = context_from_message(
        event_type="rip.completed",
        job=job,
        job_id=ev.job_id,
        payload=ev.payload_json,
        occurred_at=ev.emitted_at,
    )
    assert a == b


def test_resolve_title_body_caps_width_spec_amplification() -> None:
    """A width-spec format like {job_title:>50000} must not produce a giant string."""
    from arm_backend.notification_format import resolve_title_body

    ctx = {"job_title": "X"}
    title, body = resolve_title_body(
        event_type="rip.completed",
        default_title="{job_title:>50000}",
        default_body="{job_title:>200000}",
        template=None,
        context=ctx,
    )
    assert len(title) <= 4001  # cap is 4000 chars + 1 ellipsis
    assert len(body) <= 16001  # cap is 16000 chars + 1 ellipsis
