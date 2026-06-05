"""Targeted unit coverage for small residual gaps across helper modules:
config validator, notification_format label/body branches, ws.authz._split
edge cases, WSHub unsubscribe/emit-without-session, and track_selection's
unsupported-disc-type raise.
"""

from __future__ import annotations

import logging
import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

from arm_backend.config import Settings  # noqa: E402
from arm_backend.notification_format import _disc_label, _rip_body  # noqa: E402
from arm_backend.track_selection import TrackSelectionError, select_tracks  # noqa: E402
from arm_backend.ws.authz import _split  # noqa: E402
from arm_backend.ws.hub import WSHub  # noqa: E402
from arm_common import DiscType, Event, Job, JobStatus, RipPreset, MediaType, TrackSelection  # noqa: E402
from arm_common.enums import IdentificationMode, OutputMode  # noqa: E402
from arm_common.schemas import ScanResult  # noqa: E402


# --- config validator --------------------------------------------------------


def test_split_origins_passes_through_non_str() -> None:
    """A non-str value (already a list) is returned unchanged (config.py:39)."""
    assert Settings._split_origins(["https://a", "https://b"]) == ["https://a", "https://b"]


def test_split_origins_parses_csv() -> None:
    assert Settings._split_origins(" a , b ,, c ") == ["a", "b", "c"]


# --- notification_format -----------------------------------------------------


def _job(title: str | None, year: int | None) -> Job:
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


def _event(**payload: object) -> Event:
    return Event(
        id="evt_1", event_type="rip.completed", job_id="job_01JZXR7K3M5Q8N4VWA00000001", payload_json=dict(payload)
    )


def test_disc_label_title_without_year() -> None:
    assert _disc_label(_event(), _job("Solaris", None)) == "Solaris"


def test_disc_label_title_with_year() -> None:
    assert _disc_label(_event(), _job("Solaris", 1972)) == "Solaris (1972)"


def test_disc_label_job_id_fallback() -> None:
    ev = Event(id="e", event_type="x", job_id="job_01JZXR7K3M5Q8N4VWA0000000C", payload_json={})
    assert _disc_label(ev, None) == "job=job_01JZXR7K3M5Q8N4VWA0000000C"


def test_disc_label_unknown() -> None:
    ev = Event(id="e", event_type="x", payload_json={})
    assert _disc_label(ev, None) == "(unknown disc)"


def test_rip_body_no_drive_no_totals() -> None:
    """drive_id falsy (32->34) and total None (34->39) — only the disc label."""
    assert _rip_body(_event(), _job("Solaris", 1972)) == "Solaris (1972)"


def test_rip_body_with_failures() -> None:
    body = _rip_body(_event(drive_id="drv_x", tracks_done=2, tracks_failed=1, tracks_total=3), _job("M", 2000))
    assert "drive=drv_x" in body
    assert "2/3 tracks done, 1 failed" in body


def test_rip_body_all_done() -> None:
    body = _rip_body(_event(tracks_done=3, tracks_failed=0, tracks_total=3), _job("M", 2000))
    assert "3/3 tracks" in body


# --- ws.authz._split ---------------------------------------------------------


def test_split_empty_topic() -> None:
    assert _split("") == ("", None)


def test_split_bare_topic_no_dot() -> None:
    assert _split("standalone") == ("standalone", None)


def test_split_known_no_scope() -> None:
    assert _split("ripper.events") == ("ripper.events", None)


def test_split_scoped() -> None:
    assert _split("ripper.progress.job_01JZXR7K3M5Q8N4VWA0000000D") == (
        "ripper.progress",
        "job_01JZXR7K3M5Q8N4VWA0000000D",
    )


# --- WSHub -------------------------------------------------------------------


async def test_hub_unsubscribe_unknown_topic_noop() -> None:
    hub = WSHub()
    await hub.unsubscribe(object(), "never.subscribed")  # subs is None → 48->exit


async def test_hub_unsubscribe_leaves_nonempty_set() -> None:
    hub = WSHub()
    ws_a, ws_b = object(), object()
    await hub.subscribe(ws_a, "t")
    await hub.subscribe(ws_b, "t")
    await hub.unsubscribe(ws_a, "t")  # set still non-empty → 50->exit (no pop)
    assert "t" in hub._subs and ws_b in hub._subs["t"]


async def test_hub_emit_persist_without_session_warns(caplog: pytest.LogCaptureFixture) -> None:
    hub = WSHub()
    with caplog.at_level(logging.WARNING, logger="arm_backend.ws.hub"):
        await hub.emit(topic="ripper.events", event_type="x", payload={}, persist=True, session=None)
    assert any("without session" in r.message for r in caplog.records)


# --- track_selection ---------------------------------------------------------


def _preset() -> RipPreset:
    return RipPreset(
        id="rpr_x",
        name="x",
        media_type=MediaType.MOVIE,
        is_builtin=True,
        track_selection=TrackSelection.ALL_TRACKS,
        identification_mode=IdentificationMode.SKIP,
        output_mode=OutputMode.TRACKS,
    )


def test_select_tracks_unsupported_disc_type_raises() -> None:
    scan = ScanResult(disc_type=DiscType.UNKNOWN, titles=[])
    with pytest.raises(TrackSelectionError, match="cannot select tracks for disc_type"):
        select_tracks("job_01JZXR7K3M5Q8N4VWA00000001", scan, _preset())
