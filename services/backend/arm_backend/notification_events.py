"""The single source of truth for the notification event vocabulary.

Each real event key (rip.*/session.*) maps to its human label, default
title/body templates (rendered through `event_context` like any override),
and the variable names a template may inject for that event. `event_context`
(notification_format) and the `/event-types` catalog both derive from here so
the advertised fields, the defaults, and what an override can use cannot drift.
"""

from __future__ import annotations

from typing import NamedTuple

# Variables present on every event (from the loaded Job + the Event envelope).
_COMMON = ("job_title", "job_year", "job_disc_type", "drive_id", "job_id", "event_type", "occurred_at")


class EventSpec(NamedTuple):
    label: str
    default_title: str
    default_body: str
    variables: tuple[str, ...]


def _rip(label: str, title: str, body: str) -> EventSpec:
    return EventSpec(label, title, body, _COMMON + ("status", "tracks_done", "tracks_failed", "tracks_total"))


def _session(label: str, title: str, body: str) -> EventSpec:
    return EventSpec(label, title, body, _COMMON + ("status", "session_id", "session_application_id"))


EVENT_VOCAB: dict[str, EventSpec] = {
    "rip.completed": _rip(
        "Rip completed",
        "ARM: rip completed - {job_title}",
        "{job_title} finished ripping on drive {drive_id} ({tracks_done}/{tracks_total} tracks).",
    ),
    "rip.partial": _rip(
        "Rip partial",
        "ARM: rip partial - {job_title}",
        "{job_title} ripped partially on drive {drive_id} ({tracks_done}/{tracks_total} done, {tracks_failed} failed).",
    ),
    "rip.failed": _rip(
        "Rip failed",
        "ARM: rip failed - {job_title}",
        "{job_title} failed to rip on drive {drive_id} ({tracks_done}/{tracks_total} done, {tracks_failed} failed).",
    ),
    "rip.needs_user_input": EventSpec(
        "Needs user input",
        "ARM: needs user input - {job_title}",
        "{job_title} on drive {drive_id} needs identification before ripping can continue.",
        _COMMON + ("volume_label", "disc_type"),
    ),
    "session.completed": _session(
        "Session completed",
        "ARM: session completed - {job_title}",
        "{job_title} transcode session completed (status {status}).",
    ),
    "session.partial": _session(
        "Session partial",
        "ARM: session partial - {job_title}",
        "{job_title} transcode session finished partially (status {status}).",
    ),
    "session.failed": _session(
        "Session failed",
        "ARM: session failed - {job_title}",
        "{job_title} transcode session failed (status {status}).",
    ),
}


def event_keys() -> list[str]:
    return sorted(EVENT_VOCAB)
