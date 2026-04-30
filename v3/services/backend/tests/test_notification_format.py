"""Phase 11 — pure-function tests for `format_event`."""

from __future__ import annotations

from datetime import UTC, datetime

from arm_backend.notification_format import format_event
from arm_common import DiscType, Event, Job, JobStatus


def _job(title: str | None = "Iron Man", year: int | None = 2008) -> Job:
    return Job(
        id="job_x",
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
        job_id="job_x",
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
    assert title == "ARM: rip completed"
    assert "Iron Man (2008)" in body
    assert "drive=drv_x" in body
    assert "3/3 tracks" in body


def test_rip_partial_lists_failed_count() -> None:
    event = _event(
        "rip.partial",
        {"drive_id": "drv_x", "tracks_done": 2, "tracks_failed": 1, "tracks_total": 3},
    )
    title, body = format_event(event, _job())
    assert title == "ARM: rip partial"
    assert "2/3 tracks done, 1 failed" in body


def test_session_completed_includes_session_id_and_status() -> None:
    event = _event(
        "session.completed",
        {"session_id": "ses_x", "session_application_id": "sap_x", "job_id": "job_x", "status": "done"},
    )
    title, body = format_event(event, _job())
    assert title == "ARM: session completed"
    assert "session=ses_x" in body
    assert "status=done" in body


def test_falls_back_to_payload_when_job_is_none() -> None:
    event = _event(
        "rip.completed",
        {"drive_id": "drv_x", "tracks_done": 1, "tracks_total": 1},
    )
    title, body = format_event(event, None)
    assert title == "ARM: rip completed"
    # No job → use the job_id stamped on the event row.
    assert "job=job_x" in body


def test_year_omitted_when_none() -> None:
    event = _event(
        "rip.completed",
        {"drive_id": "drv_x", "tracks_done": 1, "tracks_total": 1},
    )
    title, body = format_event(event, _job(title="My Home Movie", year=None))
    assert title == "ARM: rip completed"
    assert "My Home Movie" in body
    assert "(None)" not in body
