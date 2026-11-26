"""JobController behaviour with a fake BackendClient and stubbed scan."""

import asyncio
import errno
import logging
import os
from collections import deque
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import arm_ripper.backend_retry as backend_retry_module
import arm_ripper.eject as eject_module
import arm_ripper.disc_scan as disc_scan_module
import arm_ripper.disc_rip as disc_rip_module
import arm_ripper.job_controller as jc_module
import arm_ripper.raw_dir as raw_dir_module
import arm_ripper.resolution_wait as resolution_wait_module
import arm_ripper.makemkv_prep as makemkv_prep_module
from arm_common import MediaType, DiscType, Job, JobStatus
from arm_common.schemas import (
    JobView,
    RipperConfigView,
    RipStartResponse,
    ScanResult,
    ScanTitle,
    TrackView,
    WSEnvelope,
)
from arm_ripper.drive_poll import DriveState
from arm_ripper.eject import Ejector
from arm_ripper.job_controller import JobController
from arm_ripper.resolution_wait import ResolutionWaiter
from arm_ripper.makemkv_prep import MakeMKVPrep


def _job(status: JobStatus, *, title: str | None = None) -> Job:
    return Job(
        id="job_test",
        drive_id="drv_test",
        disc_type=DiscType.DVD,
        status=status,
        title=title,
        year=None,
        metadata_json={},
        resumed_from_crash=False,
        started_at=None,
        ripped_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _view(
    status: JobStatus,
    *,
    title: str | None = None,
    wait_start_time: datetime | None = None,
    manual_pause: bool = False,
    episodes_unsure: bool = False,
) -> JobView:
    return JobView(
        id="job_test",
        drive_id="drv_test",
        disc_type=DiscType.DVD,
        status=status,
        title=title,
        year=None,
        media_type=MediaType.TV if episodes_unsure else None,
        metadata_json={"identity_claims": {"unsure": True}} if episodes_unsure else {},
        resumed_from_crash=False,
        wait_start_time=wait_start_time,
        manual_pause=manual_pause,
    )


class FakeClient:
    def __init__(self) -> None:
        # A queued exception is raised instead of returned (identify refused).
        self.identify_responses: deque[Job | Exception] = deque()
        self.get_job_responses: deque[JobView] = deque()
        self.identify_calls: list[ScanResult] = []
        self.identify_pending_session_ids: list[str | None] = []
        self.get_job_calls: list[str] = []
        self.rip_start_calls: list[str] = []
        self.rip_complete_calls: list[str] = []
        self.resume_calls: list[str] = []
        self.auto_rip_on_insert: bool = True
        self.makemkv_key: str | None = None
        self.get_ripper_config_error: Exception | None = None
        self.get_ripper_config_calls: int = 0
        self.community_keydb_enabled: bool = True
        self.ripping_paused: bool = False
        self.manual_wait_seconds: int = 60
        self.keydb_reports: list = []
        self.sdf_reports: list = []
        self.makemkv_sdf_enabled: bool = True

    async def identify(
        self,
        *,
        drive_id: str,
        scan_result: ScanResult,
        pending_session_id: str | None = None,
    ) -> Job:
        self.identify_calls.append(scan_result)
        self.identify_pending_session_ids.append(pending_session_id)
        response = self.identify_responses.popleft()
        if isinstance(response, Exception):
            raise response
        return response

    async def get_job(self, job_id: str) -> JobView:
        self.get_job_calls.append(job_id)
        return self.get_job_responses.popleft()

    async def rip_start(self, job_id: str) -> RipStartResponse:
        self.rip_start_calls.append(job_id)
        return RipStartResponse(
            job_id=job_id,
            rip_preset_id="rpr_builtin_movie_archive",
            tracks=[],
        )

    async def update_track(self, track_id: str, **fields: object) -> TrackView:  # pragma: no cover
        raise AssertionError("update_track should not be called when track list is empty")

    async def resume(self, job_id: str) -> RipStartResponse:
        self.resume_calls.append(job_id)
        return RipStartResponse(
            job_id=job_id,
            rip_preset_id="rpr_builtin_movie_archive",
            tracks=[],
        )

    async def rip_complete(self, job_id: str) -> JobView:
        self.rip_complete_calls.append(job_id)
        return _view(JobStatus.RIPPED)

    async def get_ripper_config(self) -> RipperConfigView:
        self.get_ripper_config_calls += 1
        if self.get_ripper_config_error is not None:
            raise self.get_ripper_config_error
        return RipperConfigView(
            auto_rip_on_insert=self.auto_rip_on_insert,
            makemkv_key=self.makemkv_key,
            community_keydb_enabled=self.community_keydb_enabled,
            ripping_paused=self.ripping_paused,
            manual_wait_seconds=self.manual_wait_seconds,
            makemkv_sdf_enabled=self.makemkv_sdf_enabled,
        )

    async def report_keydb_status(self, *, state, vuk_count=None, age_days=None) -> None:
        self.keydb_reports.append((state, vuk_count, age_days))

    async def report_sdf_status(self, *, state, age_days=None) -> None:
        self.sdf_reports.append((state, age_days))


@pytest.fixture(autouse=True)
def fast_polls(monkeypatch, tmp_path):
    """Don't wait 5+ seconds between polls; write under tmp_path, not /raw."""
    monkeypatch.setattr(resolution_wait_module, "POLL_MAX_SECONDS", 0.01)
    monkeypatch.setattr(disc_rip_module, "EJECT_GRACE_SECONDS", 0.0)
    monkeypatch.setattr(raw_dir_module, "RAW_ROOT", tmp_path)
    # WS-driven resolution path: collapse the boot-race grace window so
    # tests fall straight through to the REST fallback path that the
    # FakeClient feeds.
    monkeypatch.setattr(resolution_wait_module, "RESOLUTION_WS_FIRST_WAIT_SECONDS", 0.0)
    monkeypatch.setattr(resolution_wait_module, "RESOLUTION_WAIT_TIMEOUT_SECONDS", 1.0)


@pytest.fixture
def stub_eject(monkeypatch):
    async def _noop_eject(self, device_path: str) -> None:
        return None

    monkeypatch.setattr(eject_module.Ejector, "eject", _noop_eject)


@pytest.fixture
def stub_scan(monkeypatch):
    async def _scan(_device_path: str) -> ScanResult:
        return ScanResult(
            disc_type=DiscType.DVD,
            volume_label="TEST",
            titles=[ScanTitle(index=0, duration_seconds=3600)],
        )

    monkeypatch.setattr(disc_scan_module, "scan_disc", _scan)


async def test_identified_runs_rip_with_empty_tracks(stub_scan, stub_eject):
    client = FakeClient()
    client.identify_responses.append(_job(JobStatus.IDENTIFIED, title="Test Movie"))
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert len(client.identify_calls) == 1
    assert client.rip_start_calls == ["job_test"]
    assert client.rip_complete_calls == ["job_test"]


async def test_awaiting_polls_until_resolved_then_rips(stub_scan, stub_eject):
    client = FakeClient()
    client.identify_responses.append(_job(JobStatus.AWAITING_USER_ID))
    client.get_job_responses.extend(
        [
            _view(JobStatus.AWAITING_USER_ID),
            _view(JobStatus.AWAITING_USER_ID),
            _view(JobStatus.IDENTIFIED, title="Resolved"),
        ]
    )
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert client.rip_start_calls == ["job_test"]
    assert client.rip_complete_calls == ["job_test"]


async def test_drive_vanishing_mid_scan_is_abandoned_cleanly(monkeypatch, caplog):
    """Power-off mid-scan raises OSError(ENXIO, …) from scan_disc. The pipeline
    must not propagate it — the poll loop's absence handling owns recovery —
    and must log exactly one warning about it."""

    async def _scan(_device_path: str) -> ScanResult:
        raise OSError(errno.ENXIO, "No such device or address")

    monkeypatch.setattr(disc_scan_module, "scan_disc", _scan)
    client = FakeClient()
    controller = JobController(client, "drv_test")

    with caplog.at_level(logging.WARNING, logger="arm_ripper.job_controller"):
        await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert client.identify_calls == []
    went_absent_records = [r for r in caplog.records if "went absent during scan" in r.message]
    assert len(went_absent_records) == 1


async def test_non_absent_oserror_during_scan_still_raises(monkeypatch):
    """Only the absence errnos (ENOENT/ENXIO/ENODEV) are swallowed. A genuine
    I/O error must keep propagating so it isn't silently lost."""

    async def _scan(_device_path: str) -> ScanResult:
        raise OSError(errno.EIO, "io")

    monkeypatch.setattr(disc_scan_module, "scan_disc", _scan)
    client = FakeClient()
    controller = JobController(client, "drv_test")

    with pytest.raises(OSError):
        await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)


async def test_unexpected_status_stops_without_rip(stub_scan, stub_eject):
    client = FakeClient()
    client.identify_responses.append(_job(JobStatus.AWAITING_USER_ID))
    client.get_job_responses.append(_view(JobStatus.ABANDONED))
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert client.rip_start_calls == []
    assert client.rip_complete_calls == []


# --- timed review gate: park on awaiting_review, resume on Start / auto-start ---


async def test_review_gate_parks_then_rips_on_start(stub_scan, stub_eject):
    """Identify lands the disc in awaiting_review (hold_for_review on). The
    controller parks; once the operator Starts, the job transitions to RIPPING
    and the rip proceeds — it is NOT self-abandoned while parked."""
    client = FakeClient()
    client.identify_responses.append(_job(JobStatus.AWAITING_REVIEW, title="Held Movie"))
    client.get_job_responses.extend(
        [
            _view(JobStatus.AWAITING_REVIEW),  # still parked on the first poll
            _view(JobStatus.AWAITING_REVIEW),  # still parked
            _view(JobStatus.RIPPING, title="Held Movie"),  # operator pressed Start
        ]
    )
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert client.rip_start_calls == ["job_test"]
    assert client.rip_complete_calls == ["job_test"]


async def test_review_gate_auto_start_path_identified_rips(stub_scan, stub_eject):
    """Auto-start at countdown expiry transitions the held job back to IDENTIFIED
    (the rip then proceeds) — also a success status for the review gate."""
    client = FakeClient()
    client.identify_responses.append(_job(JobStatus.AWAITING_REVIEW, title="Held Movie"))
    client.get_job_responses.append(_view(JobStatus.IDENTIFIED, title="Held Movie"))
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert client.rip_start_calls == ["job_test"]
    assert client.rip_complete_calls == ["job_test"]


async def test_review_gate_cancel_abandons_without_rip(stub_scan, stub_eject):
    """Cancel (abandon) while held leaves the gate as a terminal status; the
    controller gives up and does not rip."""
    client = FakeClient()
    client.identify_responses.append(_job(JobStatus.AWAITING_REVIEW, title="Held Movie"))
    client.get_job_responses.append(_view(JobStatus.ABANDONED))
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert client.rip_start_calls == []
    assert client.rip_complete_calls == []


async def test_review_gate_auto_starts_when_countdown_elapsed(stub_scan, stub_eject):
    """With the countdown elapsed (wait_start_time in the past, short
    manual_wait_seconds) and not paused, the parked ripper auto-starts the rip
    even though the operator never pressed Start (status stays awaiting_review)."""
    client = FakeClient()
    client.manual_wait_seconds = 1
    past = datetime.now(timezone.utc) - timedelta(seconds=10)
    client.identify_responses.append(_job(JobStatus.AWAITING_REVIEW, title="Held Movie"))
    # Every poll returns AWAITING_REVIEW with an already-elapsed countdown.
    client.get_job_responses.extend([_view(JobStatus.AWAITING_REVIEW, wait_start_time=past) for _ in range(4)])
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert client.rip_start_calls == ["job_test"]
    assert client.rip_complete_calls == ["job_test"]


async def test_review_gate_paused_does_not_auto_start(stub_scan, stub_eject, monkeypatch):
    """Countdown elapsed BUT globally paused -> no auto-start; the ripper keeps
    waiting (the wait times out in the test harness without ripping)."""
    monkeypatch.setattr(resolution_wait_module, "RESOLUTION_WAIT_TIMEOUT_SECONDS", 0.05)
    client = FakeClient()
    client.manual_wait_seconds = 1
    client.ripping_paused = True
    past = datetime.now(timezone.utc) - timedelta(seconds=10)
    client.identify_responses.append(_job(JobStatus.AWAITING_REVIEW, title="Held Movie"))
    client.get_job_responses.extend([_view(JobStatus.AWAITING_REVIEW, wait_start_time=past) for _ in range(6)])
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    # Paused suppresses auto-start: the wait expired without ripping.
    assert client.rip_start_calls == []
    assert client.rip_complete_calls == []


async def test_review_gate_per_job_pause_does_not_auto_start(stub_scan, stub_eject, monkeypatch):
    """Per-job manual_pause freezes THIS disc's countdown even when the machine is
    not globally paused — countdown elapsed but no auto-start."""
    monkeypatch.setattr(resolution_wait_module, "RESOLUTION_WAIT_TIMEOUT_SECONDS", 0.05)
    client = FakeClient()
    client.manual_wait_seconds = 1
    client.ripping_paused = False  # global NOT paused
    past = datetime.now(timezone.utc) - timedelta(seconds=10)
    client.identify_responses.append(_job(JobStatus.AWAITING_REVIEW, title="Held Movie"))
    # The held views carry manual_pause=True -> countdown stays frozen.
    client.get_job_responses.extend(
        [_view(JobStatus.AWAITING_REVIEW, wait_start_time=past, manual_pause=True) for _ in range(6)]
    )
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert client.rip_start_calls == []
    assert client.rip_complete_calls == []


async def test_review_gate_guessed_episodes_do_not_auto_start(stub_scan, stub_eject, monkeypatch, caplog):
    """A placement that is a guess holds the countdown like a per-job pause:
    elapsed, not paused, but `episodes_unsure` on every view -> no auto-start,
    logged once."""
    monkeypatch.setattr(resolution_wait_module, "RESOLUTION_WAIT_TIMEOUT_SECONDS", 0.05)
    client = FakeClient()
    client.manual_wait_seconds = 1
    client.ripping_paused = False
    past = datetime.now(timezone.utc) - timedelta(seconds=10)
    client.identify_responses.append(_job(JobStatus.AWAITING_REVIEW, title="Held Show"))
    client.get_job_responses.extend(
        [_view(JobStatus.AWAITING_REVIEW, wait_start_time=past, episodes_unsure=True) for _ in range(6)]
    )
    controller = JobController(client, "drv_test")

    with caplog.at_level(logging.INFO):
        await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert client.rip_start_calls == []
    assert client.rip_complete_calls == []
    assert sum("countdown held, its episode placement is a guess" in r.message for r in caplog.records) == 1


async def test_review_gate_auto_starts_once_the_guess_is_fixed(stub_scan, stub_eject):
    """The hold lifts with the flag: a later view without `episodes_unsure`
    (a Fix match left a confident placement) auto-starts as usual."""
    client = FakeClient()
    client.manual_wait_seconds = 1
    past = datetime.now(timezone.utc) - timedelta(seconds=10)
    client.identify_responses.append(_job(JobStatus.AWAITING_REVIEW, title="Held Show"))
    client.get_job_responses.extend(
        [_view(JobStatus.AWAITING_REVIEW, wait_start_time=past, episodes_unsure=True) for _ in range(2)]
        + [_view(JobStatus.AWAITING_REVIEW, wait_start_time=past) for _ in range(4)]
    )
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=4.0)

    assert client.rip_start_calls == ["job_test"]
    assert client.rip_complete_calls == ["job_test"]


# --- resolution_timeout: source mode's indefinite wait ----------------------
async def test_resolution_timeout_default_still_times_out(stub_scan, stub_eject):
    """No override passed to the constructor: the wait still honours
    RESOLUTION_WAIT_TIMEOUT_SECONDS exactly as before (the `fast_polls` fixture
    patches it to 1.0s, POLL_MAX_SECONDS to 0.01s, so a job stuck parked forever
    gives up quickly instead of actually waiting 30 minutes)."""

    async def _always_parked(job_id: str) -> JobView:
        return _view(JobStatus.AWAITING_USER_ID)

    client = FakeClient()
    client.identify_responses.append(_job(JobStatus.AWAITING_USER_ID))
    client.get_job = _always_parked  # type: ignore[method-assign]
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert client.rip_start_calls == []
    assert client.rip_complete_calls == []


async def test_resolution_timeout_none_waits_past_old_deadline_then_proceeds(stub_scan, stub_eject, monkeypatch):
    """`resolution_timeout=None` (source mode) keeps waiting well past the
    point where the default RESOLUTION_WAIT_TIMEOUT_SECONDS would have given
    up, and still proceeds with the rip once the job resolves."""
    monkeypatch.setattr(resolution_wait_module, "RESOLUTION_WAIT_TIMEOUT_SECONDS", 0.05)
    poll_count = 0

    async def _resolves_after_old_deadline(job_id: str) -> JobView:
        nonlocal poll_count
        poll_count += 1
        # POLL_MAX_SECONDS is patched to 0.01s, so 20 ticks is ~0.2s — well
        # past the 0.05s default deadline a timed-out wait would have used.
        if poll_count < 20:
            return _view(JobStatus.AWAITING_USER_ID)
        return _view(JobStatus.IDENTIFIED, title="Resolved")

    client = FakeClient()
    client.identify_responses.append(_job(JobStatus.AWAITING_USER_ID))
    client.get_job = _resolves_after_old_deadline  # type: ignore[method-assign]
    controller = JobController(client, "drv_test", resolution_timeout=None)

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert poll_count >= 20
    assert client.rip_start_calls == ["job_test"]
    assert client.rip_complete_calls == ["job_test"]


async def test_rip_start_ws_command_wakes_review_waiter():
    """A `rip.start` WS command sets the per-job wait Event (the review-gate
    analogue of identify.resolved)."""
    client = FakeClient()
    controller = JobController(client, "drv_test")
    event = asyncio.Event()
    controller._waiter._resolution_events["job_test"] = event

    await controller.on_ws_command(
        WSEnvelope(
            event_id="evt_1",
            event_type="rip.start",
            emitted_at=datetime.now(timezone.utc),
            topic="ripper.commands.drv_test",
            payload={"job_id": "job_test"},
        )
    )

    assert event.is_set()


def _command(event_type: str, payload: dict) -> WSEnvelope:
    return WSEnvelope(
        event_id="evt_1",
        event_type=event_type,
        emitted_at=datetime.now(timezone.utc),
        topic="ripper.commands.drv_test",
        payload=payload,
    )


@pytest.mark.parametrize("event_type", ["identify.resolved", "rip.start", "review.pause"])
async def test_wake_command_without_job_id_logs_warning(event_type, caplog):
    controller = JobController(FakeClient(), "drv_test")
    event = asyncio.Event()
    controller._waiter._resolution_events["job_test"] = event
    caplog.set_level(logging.DEBUG, logger="arm_ripper.job_controller")

    await controller.on_ws_command(_command(event_type, {"job_id": 5}))

    records = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert [r.getMessage() for r in records] == [f"{event_type} without job_id payload: {{'job_id': 5}}"]
    assert not event.is_set()


async def test_wake_command_without_waiter_logs_debug(caplog):
    controller = JobController(FakeClient(), "drv_test")
    caplog.set_level(logging.DEBUG, logger="arm_ripper.job_controller")

    await controller.on_ws_command(_command("rip.start", {"job_id": "job_x"}))

    assert [(r.levelno, r.getMessage()) for r in caplog.records] == [
        (logging.DEBUG, "rip.start for job_id=job_x but no waiter registered")
    ]


@pytest.mark.parametrize(
    ("payload", "expected", "warns"),
    [
        ({"session_id": "sess_1"}, "sess_1", False),
        ({}, None, False),
        ({"session_id": 5}, None, True),
    ],
)
async def test_manual_trigger_ws_command_schedules_handler(payload, expected, warns, caplog):
    controller = JobController(FakeClient(), "drv_test")
    seen: list[str | None] = []

    async def fake(session_id: str | None) -> None:
        seen.append(session_id)

    controller.handle_manual_trigger = fake  # type: ignore[method-assign]
    caplog.set_level(logging.DEBUG, logger="arm_ripper.job_controller")

    await controller.on_ws_command(_command("manual.trigger", payload))
    await asyncio.sleep(0)

    assert seen == [expected]
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert warnings == (["manual.trigger with non-string session_id: 5"] if warns else [])


async def test_job_abandoned_without_job_id_is_ignored(caplog):
    controller = JobController(FakeClient(), "drv_test")
    calls: list[str] = []
    controller._handle_abandon = lambda *a, **k: calls.append("x")  # type: ignore[method-assign]
    caplog.set_level(logging.DEBUG, logger="arm_ripper.job_controller")

    await controller.on_ws_command(_command("job.abandoned", {"delete_raw": True}))

    assert calls == []
    assert [(r.levelno, r.getMessage()) for r in caplog.records] == [
        (logging.WARNING, "job.abandoned without job_id payload: {'delete_raw': True}")
    ]


async def test_unknown_ws_command_is_ignored(caplog):
    controller = JobController(FakeClient(), "drv_test")
    event = asyncio.Event()
    controller._waiter._resolution_events["job_test"] = event
    caplog.set_level(logging.DEBUG, logger="arm_ripper.job_controller")
    tasks_before = len(asyncio.all_tasks())

    await controller.on_ws_command(_command("something.else", {"job_id": "job_test"}))

    assert [(r.levelno, r.getMessage()) for r in caplog.records] == [
        (logging.DEBUG, "ws command ignored: type=something.else")
    ]
    assert not event.is_set()
    assert len(asyncio.all_tasks()) == tasks_before


# --- abandon gives the disc back (user report: abandon left the disc seated) ----


@pytest.fixture
def eject_spy(monkeypatch):
    calls: list[str] = []

    async def _spy(self, device_path: str) -> None:
        calls.append(device_path)

    monkeypatch.setattr(eject_module.Ejector, "eject", _spy)
    return calls


def _abandon_envelope() -> WSEnvelope:
    return WSEnvelope(
        event_id="evt_abandon",
        event_type="job.abandoned",
        emitted_at=datetime.now(timezone.utc),
        topic="ripper.commands.drv_test",
        job_id="job_test",
        payload={"job_id": "job_test", "delete_raw": False},
    )


def _identify_refused(code: int, detail: object) -> httpx.HTTPStatusError:
    req = httpx.Request("POST", "https://x/api/ripper/identify")
    return httpx.HTTPStatusError(
        f"{code}", request=req, response=httpx.Response(code, json={"detail": detail}, request=req)
    )


async def test_identify_refusing_an_already_ripped_disc_ejects_it(stub_scan, eject_spy):
    """on_previously_ripped=reject: no job, and the disc comes back out."""
    client = FakeClient()
    client.identify_responses.append(_identify_refused(409, {"reason": "previously_ripped", "job_id": "job_old"}))
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert eject_spy == ["/dev/sr0"]
    assert client.rip_start_calls == []


async def test_other_identify_refusals_leave_the_disc_in(stub_scan, eject_spy):
    client = FakeClient()
    client.identify_responses.append(_identify_refused(409, "ripping is paused; no new jobs accepted"))
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert eject_spy == []


async def test_abandon_while_parked_cancels_and_ejects(stub_scan, eject_spy, monkeypatch):
    """Abandoning a job parked in AWAITING_USER_ID cancels the parked pipeline
    AND pops the tray — the post-rip eject never runs on an abandon exit."""
    monkeypatch.setattr(resolution_wait_module, "RESOLUTION_WS_FIRST_WAIT_SECONDS", 5.0)
    monkeypatch.setattr(resolution_wait_module, "RESOLUTION_WAIT_TIMEOUT_SECONDS", 30.0)
    client = FakeClient()
    client.identify_responses.append(_job(JobStatus.AWAITING_USER_ID))
    controller = JobController(client, "drv_test", device_path="/dev/sr0")

    pipeline = asyncio.create_task(controller.handle_disc_inserted("/dev/sr0"))
    await asyncio.sleep(0.05)  # reach _wait_for_resolution
    await controller.on_ws_command(_abandon_envelope())
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(pipeline, timeout=2.0)
    await asyncio.sleep(0.01)  # let the spawned eject task run

    assert eject_spy == ["/dev/sr0"]
    assert client.rip_start_calls == []


async def test_abandon_during_rip_cancels_and_ejects(stub_scan, eject_spy):
    """Abandon mid-rip cancels the pipeline task and still ejects the disc."""
    client = FakeClient()
    client.identify_responses.append(_job(JobStatus.IDENTIFIED, title="Mid Rip"))
    rip_started = asyncio.Event()

    async def _hanging_rip_start(job_id: str) -> RipStartResponse:
        client.rip_start_calls.append(job_id)
        rip_started.set()
        await asyncio.sleep(3600)
        raise AssertionError("unreachable")

    client.rip_start = _hanging_rip_start  # type: ignore[method-assign]
    controller = JobController(client, "drv_test", device_path="/dev/sr0")

    pipeline = asyncio.create_task(controller.handle_disc_inserted("/dev/sr0"))
    await asyncio.wait_for(rip_started.wait(), timeout=2.0)
    await controller.on_ws_command(_abandon_envelope())
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(pipeline, timeout=2.0)
    await asyncio.sleep(0.01)

    assert eject_spy == ["/dev/sr0"]
    assert client.rip_complete_calls == []


async def test_abandon_idle_drive_with_disc_seated_ejects(eject_spy, monkeypatch):
    """Abandon after the pipeline already exited (e.g. rip-start abort): the
    idle drive still holds the disc — give it back."""
    monkeypatch.setattr(jc_module, "read_drive_status", lambda _d: jc_module.DriveState.DISC_OK)
    controller = JobController(FakeClient(), "drv_test", device_path="/dev/sr0")

    controller._handle_abandon("job_test", delete_raw=False)
    await asyncio.sleep(0.01)

    assert eject_spy == ["/dev/sr0"]


async def test_abandon_idle_drive_without_disc_does_not_eject(eject_spy, monkeypatch):
    """Abandoning an old job from history with an empty drive must not pop
    the tray."""
    monkeypatch.setattr(jc_module, "read_drive_status", lambda _d: jc_module.DriveState.NO_DISC)
    controller = JobController(FakeClient(), "drv_test", device_path="/dev/sr0")

    controller._handle_abandon("job_test", delete_raw=False)
    await asyncio.sleep(0.01)

    assert eject_spy == []


async def test_abandon_stale_job_during_other_rip_does_not_eject(eject_spy):
    """A stale abandon while a DIFFERENT job's rip owns the drive must not
    cancel it or eject its disc mid-rip."""
    controller = JobController(FakeClient(), "drv_test", device_path="/dev/sr0")
    other = asyncio.create_task(asyncio.sleep(3600))
    controller._active_task = other
    controller._active_job_id = "job_other"

    controller._handle_abandon("job_test", delete_raw=False)
    await asyncio.sleep(0.01)

    assert eject_spy == []
    assert not other.cancelled()
    other.cancel()


async def test_spawn_eject_creates_task_that_ejects_the_device(eject_spy):
    """With a device path and no running task, _spawn_eject runs Ejector.eject(device_path) in a new task."""
    controller = JobController(FakeClient(), "drv_test", device_path="/dev/sr0")

    controller._spawn_eject()

    assert controller._eject_task is not None
    await controller._eject_task
    assert eject_spy == ["/dev/sr0"]


async def test_spawn_eject_without_device_path_does_nothing(eject_spy):
    """A controller built without a device path never creates an eject task."""
    controller = JobController(FakeClient(), "drv_test")

    controller._spawn_eject()
    await asyncio.sleep(0)

    assert controller._eject_task is None
    assert eject_spy == []


async def test_spawn_eject_is_deduped_while_a_task_is_running(monkeypatch):
    """A second _spawn_eject while the first eject task is pending keeps the same task and ejects only once."""
    release = asyncio.Event()
    calls: list[str] = []

    async def _blocked(self, device_path: str) -> None:
        calls.append(device_path)
        await release.wait()

    monkeypatch.setattr(eject_module.Ejector, "eject", _blocked)
    controller = JobController(FakeClient(), "drv_test", device_path="/dev/sr0")

    controller._spawn_eject()
    first = controller._eject_task
    await asyncio.sleep(0)
    controller._spawn_eject()
    await asyncio.sleep(0)

    assert first is not None and not first.done()
    assert controller._eject_task is first
    assert calls == ["/dev/sr0"]

    release.set()
    await first


async def test_ws_event_unblocks_resolution_faster_than_rest(monkeypatch, stub_scan, stub_eject):
    """An identify.resolved WS event makes _await_resolution return immediately.

    Confirms the new WS-driven path: registering the handler is enough; we
    don't need the slow REST fallback to do the work.
    """
    monkeypatch.setattr(resolution_wait_module, "RESOLUTION_WS_FIRST_WAIT_SECONDS", 5.0)
    monkeypatch.setattr(resolution_wait_module, "RESOLUTION_WAIT_TIMEOUT_SECONDS", 30.0)

    client = FakeClient()
    client.identify_responses.append(_job(JobStatus.AWAITING_USER_ID))
    # Once the WS handler fires, we still verify via REST get_job — feed identified.
    client.get_job_responses.append(_view(JobStatus.IDENTIFIED, title="Resolved"))
    controller = JobController(client, "drv_test")

    async def fire_ws_event_after_a_tick() -> None:
        # Yield twice so handle_disc_inserted reaches _wait_for_resolution.
        await asyncio.sleep(0.05)
        envelope = WSEnvelope(
            event_id="evt_test",
            event_type="identify.resolved",
            emitted_at=datetime.now(timezone.utc),
            topic="ripper.commands.drv_test",
            job_id="job_test",
            payload={"job_id": "job_test", "title": "Resolved"},
        )
        await controller.on_ws_command(envelope)

    await asyncio.wait_for(
        asyncio.gather(
            controller.handle_disc_inserted("/dev/sr0"),
            fire_ws_event_after_a_tick(),
        ),
        timeout=2.0,
    )

    assert client.rip_start_calls == ["job_test"]
    assert client.rip_complete_calls == ["job_test"]


async def test_long_wait_returns_none_when_the_job_leaves_the_gate_another_way():
    """In the long-wait loop, a job that left the gate by a non-success status (here ABANDONED)
    ends the wait with None instead of waiting out the deadline."""
    calls = 0

    async def fn(job_id: str) -> JobView:
        nonlocal calls
        calls += 1
        # Call 1 is the first-wait REST read (still parked); call 2 is long-wait cycle 1.
        return _view(JobStatus.AWAITING_USER_ID if calls == 1 else JobStatus.ABANDONED)

    client = FakeClient()
    client.get_job = fn  # type: ignore[method-assign]
    controller = JobController(client, "drv_test")

    result = await asyncio.wait_for(controller._waiter.await_resolution("job_test"), timeout=2.0)

    assert result is None
    assert calls >= 2


async def test_wake_while_still_parked_rearms_the_event():
    """A WS wake that finds the job still parked clears the Event so the next cycle waits again
    instead of spinning on an already-set Event."""
    calls = 0
    set_when_checked: list[bool] = []
    controller = JobController(FakeClient(), "drv_test")

    async def fn(job_id: str) -> JobView:
        nonlocal calls
        calls += 1
        event = controller._waiter._resolution_events["job_test"]
        if calls == 2:
            # Long-wait cycle 1 (timed out, no wake yet): still parked, fire the WS wake.
            event.set()
        elif calls == 4:
            # Long-wait cycle 3, after the woken cycle 2 cleared the Event: record its state.
            set_when_checked.append(event.is_set())
            return _view(JobStatus.IDENTIFIED, title="Resolved")
        # Call 1 is the first-wait read; call 3 is the woken cycle 2 (still parked, then cleared).
        return _view(JobStatus.AWAITING_USER_ID)

    controller._client.get_job = fn  # type: ignore[method-assign]

    result = await asyncio.wait_for(controller._waiter.await_resolution("job_test"), timeout=2.0)

    assert set_when_checked == [False]
    assert result is not None
    assert result.status == JobStatus.IDENTIFIED


async def test_long_wait_keeps_waiting_through_a_failed_job_read():
    """A REST failure during the long wait is read as 'keep waiting' (not abandon); the next
    successful read still resolves the wait."""
    calls = 0

    async def fn(job_id: str) -> JobView:
        nonlocal calls
        calls += 1
        if calls == 1:
            return _view(JobStatus.AWAITING_USER_ID)  # first-wait read
        if calls == 2:
            raise httpx.ConnectError("backend down")  # long-wait cycle 1: _safe_get_job -> None
        return _view(JobStatus.IDENTIFIED, title="Resolved")  # long-wait cycle 2

    client = FakeClient()
    client.get_job = fn  # type: ignore[method-assign]
    controller = JobController(client, "drv_test")

    result = await asyncio.wait_for(controller._waiter.await_resolution("job_test"), timeout=2.0)

    assert result is not None
    assert result.status == JobStatus.IDENTIFIED
    assert calls == 3


async def test_disc_inserted_skipped_when_auto_rip_disabled(stub_scan, stub_eject):
    """auto_rip_on_insert=False short-circuits the pipeline before scan."""
    client = FakeClient()
    client.auto_rip_on_insert = False
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert client.get_ripper_config_calls == 1
    assert client.identify_calls == []
    assert client.rip_start_calls == []
    assert client.rip_complete_calls == []


async def test_manual_trigger_runs_even_when_auto_rip_disabled(stub_scan, stub_eject):
    """manual.trigger is an explicit user action and bypasses the auto_rip switch."""
    client = FakeClient()
    client.auto_rip_on_insert = False
    client.identify_responses.append(_job(JobStatus.IDENTIFIED, title="Manual Movie"))
    controller = JobController(client, "drv_test", device_path="/dev/sr0")

    await asyncio.wait_for(controller.handle_manual_trigger("sess_test"), timeout=2.0)

    # The manual path bypasses the auto_rip gate (user already opted in) but
    # still does config lookups inside the pipeline: one for the MakeMKV key,
    # one for the community-keydb toggle, and one for the SDF toggle.
    assert client.get_ripper_config_calls == 3
    assert client.identify_pending_session_ids == ["sess_test"]
    assert client.rip_start_calls == ["job_test"]
    assert client.rip_complete_calls == ["job_test"]


async def test_pipeline_refreshes_makemkv_key_before_scan(monkeypatch, stub_scan, stub_eject):
    """The key is refreshed once, before the scan probe, with the configured key."""
    keys: list[str | None] = []

    async def _record(key: str | None = None) -> None:
        keys.append(key)

    monkeypatch.setattr(makemkv_prep_module, "refresh_makemkv_key", _record)

    client = FakeClient()
    client.makemkv_key = "T-configured"
    client.identify_responses.append(_job(JobStatus.IDENTIFIED, title="Test Movie"))
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    # Refreshed once, and the operator key from Config was threaded through.
    assert keys == ["T-configured"]
    assert client.rip_start_calls == ["job_test"]


async def test_makemkv_key_lookup_failure_falls_back_to_none(monkeypatch, stub_scan, stub_eject):
    """A backend error fetching the key is non-fatal: refresh runs with key=None
    (env/scrape fallback) and the rip proceeds."""
    keys: list[str | None] = []

    async def _record(key: str | None = None) -> None:
        keys.append(key)

    monkeypatch.setattr(makemkv_prep_module, "refresh_makemkv_key", _record)

    client = FakeClient()
    client.get_ripper_config_error = httpx.ConnectError("backend down")
    client.identify_responses.append(_job(JobStatus.IDENTIFIED, title="Test Movie"))
    controller = JobController(client, "drv_test", device_path="/dev/sr0")

    await asyncio.wait_for(controller.handle_manual_trigger(None), timeout=2.0)

    assert keys == [None]
    assert client.rip_start_calls == ["job_test"]


@pytest.mark.asyncio
async def test_pipeline_spawns_keydb_refresh_nonfatal(monkeypatch, stub_scan, stub_eject):
    # The keydb refresh is fire-and-forget and must not abort the rip even if it raises.
    calls = []

    async def _boom(*, script_path="/usr/local/bin/update_keydb.sh", enabled=True):
        calls.append(enabled)
        raise RuntimeError("keydb boom")

    monkeypatch.setattr(makemkv_prep_module, "refresh_community_keydb", _boom)

    client = FakeClient()
    client.community_keydb_enabled = True
    prep = MakeMKVPrep(client)
    prep._spawn_keydb_refresh(enabled=True)
    await prep._drain_keydb_tasks()
    assert calls == [True]  # ran once; the RuntimeError was swallowed (this line proves no propagation)


@pytest.mark.asyncio
async def test_keydb_refresh_reports_result(monkeypatch):
    from arm_common import KeydbState
    from arm_ripper.community_keydb import KeydbResult

    async def _ok(*, script_path="/usr/local/bin/update_keydb.sh", enabled=True):
        return KeydbResult(state=KeydbState.OK, vuk_count=42, age_days=None)

    monkeypatch.setattr(makemkv_prep_module, "refresh_community_keydb", _ok)
    client = FakeClient()
    prep = MakeMKVPrep(client)
    prep._spawn_keydb_refresh(enabled=True)
    await prep._drain_keydb_tasks()
    assert client.keydb_reports == [(KeydbState.OK, 42, None)]


async def test_drain_keydb_tasks_with_no_tasks_does_not_gather(monkeypatch):
    """Pin that draining with no keydb tasks returns without calling asyncio.gather."""

    def _fail_gather(*args, **kwargs):
        pytest.fail("asyncio.gather must not be called when there are no keydb tasks")

    monkeypatch.setattr(makemkv_prep_module.asyncio, "gather", _fail_gather)
    prep = MakeMKVPrep(FakeClient())
    assert await prep._drain_keydb_tasks() is None
    assert not prep._keydb_tasks


async def test_eject_runs_umount_then_eject_until_success(monkeypatch):
    monkeypatch.setattr(eject_module, "EJECT_RETRY_DELAYS", (0.0, 0.0, 0.0))

    invocations: list[tuple[str, ...]] = []
    rc_sequence = iter([1, 1, 1, 0])  # umount fails, eject 1+2 fail, eject 3 succeeds

    async def _fake_run(*argv: str, log_failure: bool = True) -> tuple[int | None, str]:
        invocations.append(argv)
        return next(rc_sequence), "Device or resource busy"

    monkeypatch.setattr(Ejector, "_run_command", staticmethod(_fake_run))
    controller = JobController(FakeClient(), "drv_test", device_path="/dev/sr0")
    await controller._ejector.eject("/dev/sr0")

    assert invocations[0] == ("umount", "/dev/sr0")
    assert all(call[0] == "eject" for call in invocations[1:])
    assert len(invocations) == 4


async def test_eject_gives_up_after_all_attempts(monkeypatch, caplog):
    monkeypatch.setattr(eject_module, "EJECT_RETRY_DELAYS", (0.0, 0.0))

    async def _always_busy(*argv: str, log_failure: bool = True) -> tuple[int | None, str]:
        return 1, "Device or resource busy"

    monkeypatch.setattr(Ejector, "_run_command", staticmethod(_always_busy))
    controller = JobController(FakeClient(), "drv_test", device_path="/dev/sr0")
    with caplog.at_level("ERROR", logger="arm_ripper.job_controller"):
        await controller._ejector.eject("/dev/sr0")

    assert any("check host auto-mount config" in r.message for r in caplog.records)


def _http_status_error(status_code: int, *, url: str = "https://x/api") -> httpx.HTTPStatusError:
    request = httpx.Request("POST", url)
    response = httpx.Response(status_code, request=request)
    return httpx.HTTPStatusError(f"HTTP {status_code}", request=request, response=response)


async def test_rip_start_4xx_aborts_pipeline_without_retry(monkeypatch, stub_scan, stub_eject, caplog):
    """A 422 from rip-start (e.g. backend rejected an empty scan_result)
    must not loop forever — log + exit so the operator can abandon."""

    client = FakeClient()
    client.identify_responses.append(_job(JobStatus.IDENTIFIED, title=None))

    call_count = 0

    async def boom(_job_id: str) -> RipStartResponse:
        nonlocal call_count
        call_count += 1
        raise _http_status_error(422, url="https://arm-backend:8443/api/ripper/jobs/job_test/rip-start")

    # Patch the bound method on the client instance (not the class) so
    # the existing FakeClient stays usable elsewhere.
    monkeypatch.setattr(client, "rip_start", boom)
    controller = JobController(client, "drv_test")

    with caplog.at_level("ERROR", logger="arm_ripper.job_controller"):
        await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    # One attempt, no retry.
    assert call_count == 1
    # rip-complete is NOT called when rip-start aborts.
    assert client.rip_complete_calls == []
    assert any("rejected by backend" in r.message for r in caplog.records)
    assert any("abandon job_id=job_test" in r.message for r in caplog.records)


async def test_rip_start_5xx_keeps_retrying(monkeypatch, stub_scan, stub_eject):
    """A 5xx is transient (backend restart, brief overload) — keep
    retrying until it clears, then proceed."""

    client = FakeClient()
    client.identify_responses.append(_job(JobStatus.IDENTIFIED, title="X"))

    call_count = 0

    real_rip_start = client.rip_start

    async def flaky(job_id: str) -> RipStartResponse:
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise _http_status_error(503)
        return await real_rip_start(job_id)

    monkeypatch.setattr(client, "rip_start", flaky)
    # Don't actually sleep between retries.
    monkeypatch.setattr(backend_retry_module, "PATCH_RETRY_INITIAL_SECONDS", 0.0)
    monkeypatch.setattr(backend_retry_module, "PATCH_RETRY_MAX_SECONDS", 0.0)

    controller = JobController(client, "drv_test")
    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert call_count == 3
    assert client.rip_complete_calls == ["job_test"]


@pytest.mark.asyncio
async def test_pipeline_spawns_sdf_refresh_nonfatal(monkeypatch, stub_scan, stub_eject):
    # Fire-and-forget: an SDF refresh that raises must not abort the rip.
    calls = []

    async def _boom(*, script_path="/usr/local/bin/update_sdf.sh", enabled=True):
        calls.append(enabled)
        raise RuntimeError("sdf boom")

    monkeypatch.setattr(makemkv_prep_module, "refresh_makemkv_sdf", _boom)

    client = FakeClient()
    client.makemkv_sdf_enabled = True
    prep = MakeMKVPrep(client)
    prep._spawn_sdf_refresh(enabled=True)
    await prep._drain_sdf_tasks()
    assert calls == [True]  # ran once; RuntimeError swallowed (no propagation)


@pytest.mark.asyncio
async def test_sdf_refresh_reports_result(monkeypatch):
    from arm_common import MakemkvSdfState
    from arm_ripper.makemkv_sdf import SdfResult

    async def _ok(*, script_path="/usr/local/bin/update_sdf.sh", enabled=True):
        return SdfResult(state=MakemkvSdfState.UPDATED, age_days=None)

    monkeypatch.setattr(makemkv_prep_module, "refresh_makemkv_sdf", _ok)
    client = FakeClient()
    prep = MakeMKVPrep(client)
    prep._spawn_sdf_refresh(enabled=True)
    await prep._drain_sdf_tasks()
    assert client.sdf_reports == [(MakemkvSdfState.UPDATED, None)]


# ---------------------------------------------------------------------------
# _scan_with_ready_retry — DISC_OK + zero-title race
# ---------------------------------------------------------------------------


async def _noop_async(*_a, **_k):
    return None


def _async_return(value):
    async def _coro(*_a, **_k):
        return value

    return _coro()


def _titled_scan() -> ScanResult:
    return ScanResult(
        disc_type=DiscType.DVD,
        volume_label="MOVIE",
        titles=[ScanTitle(index=0, duration_seconds=3600)],
    )


def _empty_scan() -> ScanResult:
    return ScanResult(disc_type=DiscType.UNKNOWN, volume_label=None, titles=[])


async def test_scan_retry_recovers_transient_not_ready(monkeypatch):
    monkeypatch.setattr(disc_scan_module.asyncio, "sleep", _noop_async)
    results = deque([_empty_scan(), _titled_scan()])
    calls = {"n": 0}

    async def _scan(device_path):
        calls["n"] += 1
        return results.popleft()

    monkeypatch.setattr(disc_scan_module, "scan_disc", _scan)
    monkeypatch.setattr(disc_scan_module, "read_drive_status", lambda _p: DriveState.DISC_OK)

    out = await disc_scan_module._scan_with_ready_retry("/dev/sr0")
    assert out.titles
    assert calls["n"] == 2


async def test_scan_retry_exhausts_and_logs_marker(monkeypatch, caplog):
    monkeypatch.setattr(disc_scan_module.asyncio, "sleep", _noop_async)
    monkeypatch.setattr(disc_scan_module, "scan_disc", lambda _p: _async_return(_empty_scan()))
    monkeypatch.setattr(disc_scan_module, "read_drive_status", lambda _p: DriveState.DISC_OK)

    with caplog.at_level("ERROR"):
        out = await disc_scan_module._scan_with_ready_retry("/dev/sr0")
    assert not out.titles
    assert "DISC_UNREADABLE_AFTER_RETRIES" in caplog.text


async def test_scan_retry_iso_source_never_touches_drive_ioctl(monkeypatch, tmp_path):
    """An ISO source that scans to zero titles returns at once: the drive-status
    ioctl is meaningless on a regular file (ENOTTY) and must not be attempted."""
    monkeypatch.setattr(disc_scan_module.asyncio, "sleep", _noop_async)
    iso = tmp_path / "movie.iso"
    iso.write_bytes(b"\0" * 16)
    calls = {"n": 0}

    async def _scan(device_path):
        calls["n"] += 1
        return _empty_scan()

    def _ioctl_on_file(_p):
        raise OSError(25, "Inappropriate ioctl for device")

    monkeypatch.setattr(disc_scan_module, "scan_disc", _scan)
    monkeypatch.setattr(disc_scan_module, "read_drive_status", _ioctl_on_file)

    out = await disc_scan_module._scan_with_ready_retry(str(iso))
    assert not out.titles
    assert calls["n"] == 1


async def test_scan_retry_stops_when_disc_pulled(monkeypatch):
    monkeypatch.setattr(disc_scan_module.asyncio, "sleep", _noop_async)
    calls = {"n": 0}

    async def _scan(device_path):
        calls["n"] += 1
        return _empty_scan()

    states = deque([DriveState.DISC_OK, DriveState.NO_DISC])
    monkeypatch.setattr(disc_scan_module, "scan_disc", _scan)
    monkeypatch.setattr(disc_scan_module, "read_drive_status", lambda _p: states.popleft())

    out = await disc_scan_module._scan_with_ready_retry("/dev/sr0")
    assert not out.titles
    assert calls["n"] == 1


async def test_scan_retry_stops_pre_sleep_when_disc_absent(monkeypatch):
    """Drive reports non-DISC_OK on the first status check (pre-sleep): stop immediately, no sleep."""
    sleep_calls = {"n": 0}

    async def _count_sleep(_):
        sleep_calls["n"] += 1

    monkeypatch.setattr(disc_scan_module.asyncio, "sleep", _count_sleep)
    monkeypatch.setattr(disc_scan_module, "scan_disc", lambda _p: _async_return(_empty_scan()))
    monkeypatch.setattr(disc_scan_module, "read_drive_status", lambda _p: DriveState.NO_DISC)

    out = await disc_scan_module._scan_with_ready_retry("/dev/sr0")
    assert not out.titles
    assert sleep_calls["n"] == 0  # exited before the backoff block — no sleep


async def test_scan_retry_no_retry_on_first_success(monkeypatch):
    calls = {"n": 0, "status": 0}

    async def _scan(device_path):
        calls["n"] += 1
        return _titled_scan()

    def _status(_p):
        calls["status"] += 1
        return DriveState.DISC_OK

    monkeypatch.setattr(disc_scan_module, "scan_disc", _scan)
    monkeypatch.setattr(disc_scan_module, "read_drive_status", _status)

    out = await disc_scan_module._scan_with_ready_retry("/dev/sr0")
    assert out.titles
    assert calls["n"] == 1
    assert calls["status"] == 0


async def test_scan_retry_propagates_scanerror(monkeypatch):
    async def _scan(device_path):
        raise disc_scan_module.ScanError("makemkvcon rc=1")

    monkeypatch.setattr(disc_scan_module, "scan_disc", _scan)
    with pytest.raises(disc_scan_module.ScanError):
        await disc_scan_module._scan_with_ready_retry("/dev/sr0")


async def test_run_command_kill_survives_process_lookup_error(monkeypatch):
    class _DeadProc:
        returncode = None

        async def communicate(self):
            raise asyncio.TimeoutError

        def kill(self):
            raise ProcessLookupError  # child already exited

        async def wait(self):
            return None

    async def _fake_exec(*_a, **_k):
        return _DeadProc()

    monkeypatch.setattr(eject_module.asyncio, "create_subprocess_exec", _fake_exec)

    rc, msg = await Ejector._run_command("eject", "-sv", "/dev/sr0", log_failure=False)
    assert rc is None
    assert msg == "timeout"


class _FakeProc:
    """Stand-in subprocess: `communicate` returns canned output or raises; kill/wait are recorded."""

    def __init__(self, *, stderr: bytes = b"", returncode: int | None = 0, timeout: bool = False) -> None:
        self._stderr = stderr
        self.returncode = returncode
        self._timeout = timeout
        self.calls: list[str] = []

    async def communicate(self):
        if self._timeout:
            raise asyncio.TimeoutError
        return b"", self._stderr

    def kill(self) -> None:
        self.calls.append("kill")

    async def wait(self) -> None:
        self.calls.append("wait")


def _patch_exec(monkeypatch, proc: _FakeProc) -> None:
    async def _fake_exec(*_a, **_k):
        return proc

    monkeypatch.setattr(eject_module.asyncio, "create_subprocess_exec", _fake_exec)


def _patch_exec_raising(monkeypatch, exc: OSError) -> None:
    async def _fake_exec(*_a, **_k):
        raise exc

    monkeypatch.setattr(eject_module.asyncio, "create_subprocess_exec", _fake_exec)


async def test_run_command_spawn_failure_logs_warning_and_returns_error(monkeypatch, caplog):
    """A spawn failure with log_failure=True warns '<argv0> errored: <err>' and returns (None, str(err))."""
    _patch_exec_raising(monkeypatch, FileNotFoundError("no such eject"))

    with caplog.at_level("WARNING", logger="arm_ripper.job_controller"):
        result = await Ejector._run_command("eject", "-sv", "/dev/sr0")

    assert result == (None, "no such eject")
    assert [(r.levelno, r.getMessage()) for r in caplog.records] == [(logging.WARNING, "eject errored: no such eject")]


async def test_run_command_spawn_failure_is_silent_without_log_failure(monkeypatch, caplog):
    """A spawn failure (generic OSError) with log_failure=False logs nothing but returns (None, str(err))."""
    _patch_exec_raising(monkeypatch, OSError("boom"))

    with caplog.at_level("WARNING", logger="arm_ripper.job_controller"):
        result = await Ejector._run_command("umount", "/dev/sr0", log_failure=False)

    assert result == (None, "boom")
    assert caplog.records == []


async def test_run_command_timeout_logs_warning_kills_and_waits(monkeypatch, caplog):
    """A communicate() timeout with log_failure=True kills and reaps the child, warns, and returns (None, 'timeout')."""
    proc = _FakeProc(timeout=True, returncode=None)
    _patch_exec(monkeypatch, proc)

    with caplog.at_level("WARNING", logger="arm_ripper.job_controller"):
        result = await Ejector._run_command("eject", "/dev/sr0")

    assert result == (None, "timeout")
    assert proc.calls == ["kill", "wait"]
    assert [(r.levelno, r.getMessage()) for r in caplog.records] == [(logging.WARNING, "eject timed out")]


async def test_run_command_success_returns_returncode_and_stripped_stderr(monkeypatch, caplog):
    """On success it returns (returncode, stderr decoded and stripped) without logging or killing."""
    proc = _FakeProc(stderr=b"  some stderr \n", returncode=0)
    _patch_exec(monkeypatch, proc)

    with caplog.at_level("WARNING", logger="arm_ripper.job_controller"):
        result = await Ejector._run_command("eject", "/dev/sr0")

    assert result == (0, "some stderr")
    assert proc.calls == []
    assert caplog.records == []


async def test_run_command_replaces_invalid_utf8_in_stderr(monkeypatch):
    """Undecodable stderr bytes become U+FFFD instead of raising, and a non-zero returncode is passed through."""
    _patch_exec(monkeypatch, _FakeProc(stderr=b"bad \xff byte\n", returncode=1))

    assert await Ejector._run_command("eject", "/dev/sr0") == (1, "bad \ufffd byte")


async def test_abandon_with_delete_raw_wipes_off_the_event_loop(eject_spy, monkeypatch, tmp_path):
    """The raw-dir wipe runs in a thread via a spawned task, so the
    WS handler returns before a multi-GB rmtree finishes."""
    monkeypatch.setattr(raw_dir_module, "RAW_ROOT", tmp_path)
    monkeypatch.setattr(jc_module, "read_drive_status", lambda _d: jc_module.DriveState.NO_DISC)
    raw = tmp_path / "job_test"
    (raw / "sub").mkdir(parents=True)
    (raw / "sub" / "title_t00.mkv").write_bytes(b"x")
    threads: list[object] = []
    real_to_thread = raw_dir_module.asyncio.to_thread

    async def spy_to_thread(fn, *a, **kw):
        threads.append(fn)
        return await real_to_thread(fn, *a, **kw)

    monkeypatch.setattr(raw_dir_module.asyncio, "to_thread", spy_to_thread)
    controller = JobController(FakeClient(), "drv_test", device_path="/dev/sr0")

    controller._handle_abandon("job_test", delete_raw=True)
    assert raw.exists()  # not deleted inline
    await asyncio.gather(*controller._wipe_tasks)

    assert not raw.exists()
    assert threads == [raw_dir_module.shutil.rmtree]
    assert controller._wipe_tasks == set()


async def test_abandon_wipe_tolerates_missing_and_unremovable_dirs(monkeypatch, tmp_path, caplog):
    monkeypatch.setattr(raw_dir_module, "RAW_ROOT", tmp_path)
    monkeypatch.setattr(jc_module, "read_drive_status", lambda _d: jc_module.DriveState.NO_DISC)
    controller = JobController(FakeClient(), "drv_test", device_path="/dev/sr0")

    with caplog.at_level(logging.INFO, logger="arm_ripper.raw_dir"):
        controller._handle_abandon("never_existed", delete_raw=True)
        await asyncio.gather(*controller._wipe_tasks)
    assert "already absent" in caplog.text

    def denied(path, *, onexc):
        onexc(os.unlink, str(path), PermissionError("read-only mount"))

    monkeypatch.setattr(raw_dir_module.shutil, "rmtree", denied)
    controller._handle_abandon("job_x", delete_raw=True)
    await asyncio.gather(*controller._wipe_tasks)
    assert "raw-dir cleanup failed" in caplog.text


# --- pickup / recover_held_job / backend retries ---


def _spy_run_rip(controller: JobController) -> list[tuple[str, str, bool, str | None]]:
    calls: list[tuple[str, str, bool, str | None]] = []

    async def fake(job: JobView, device_path: str) -> None:
        calls.append((job.id, device_path, controller.is_idle(), controller._active_job_id))

    controller._run_rip = fake  # type: ignore[method-assign]
    return calls


@pytest.mark.asyncio
async def test_pickup_busy_is_ignored(caplog):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.job_controller")
    controller = JobController(FakeClient(), "drv_test")
    calls = _spy_run_rip(controller)
    controller._active_task = object()  # type: ignore[assignment]

    await controller.pickup(_view(JobStatus.IDENTIFIED), "/dev/sr0")

    assert calls == []
    assert any(
        r.levelno == logging.DEBUG and r.getMessage() == "pickup ignored: controller already busy"
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_pickup_claims_gate_and_runs_rip(caplog):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.job_controller")
    controller = JobController(FakeClient(), "drv_test")
    calls = _spy_run_rip(controller)

    await controller.pickup(_view(JobStatus.IDENTIFIED), "/dev/sr0")

    assert calls == [("job_test", "/dev/sr0", False, "job_test")]
    assert controller.is_idle()
    assert controller._active_job_id is None
    assert any(
        r.levelno == logging.INFO and r.getMessage() == "pickup: re-acquiring job job_test status=identified"
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_pickup_releases_gate_when_run_rip_raises():
    controller = JobController(FakeClient(), "drv_test")

    async def boom(job: JobView, device_path: str) -> None:
        raise RuntimeError("boom")

    controller._run_rip = boom  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="boom"):
        await controller.pickup(_view(JobStatus.IDENTIFIED), "/dev/sr0")

    assert controller.is_idle()
    assert controller._active_job_id is None


def _fake_resolution(controller: JobController, result: JobView | None) -> list[tuple[str, object]]:
    waits: list[tuple[str, object]] = []

    async def fake(job_id: str, spec: object) -> JobView | None:
        waits.append((job_id, spec))
        return result

    controller._waiter.await_resolution = fake  # type: ignore[method-assign]
    return waits


@pytest.mark.asyncio
async def test_recover_held_job_unresolved_returns(caplog):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.job_controller")
    controller = JobController(FakeClient(), "drv_test")
    calls = _spy_run_rip(controller)
    waits = _fake_resolution(controller, None)

    await controller.recover_held_job(_view(JobStatus.AWAITING_REVIEW), "/dev/sr0")

    assert waits == [("job_test", resolution_wait_module.REVIEW_WAIT)]
    assert calls == []
    assert controller.is_idle()
    assert controller._active_job_id is None
    assert any(
        r.levelno == logging.INFO and r.getMessage() == "reboot recovery: re-parking held job job_test"
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_recover_held_job_other_status_not_ripped(caplog):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.job_controller")
    controller = JobController(FakeClient(), "drv_test")
    calls = _spy_run_rip(controller)
    waits = _fake_resolution(controller, _view(JobStatus.ABANDONED))

    await controller.recover_held_job(_view(JobStatus.AWAITING_REVIEW), "/dev/sr0")

    assert waits == [("job_test", resolution_wait_module.REVIEW_WAIT)]
    assert calls == []
    assert controller.is_idle()
    assert any(
        r.levelno == logging.INFO and r.getMessage() == "recovered job job_test in status abandoned; not ripping"
        for r in caplog.records
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [JobStatus.IDENTIFIED, JobStatus.RIPPING])
async def test_recover_held_job_runs_rip_with_resolved_job(status):
    controller = JobController(FakeClient(), "drv_test")
    calls = _spy_run_rip(controller)
    waits = _fake_resolution(controller, _view(status, title="Resolved"))

    await controller.recover_held_job(_view(JobStatus.AWAITING_REVIEW), "/dev/sr0")

    assert waits == [("job_test", resolution_wait_module.REVIEW_WAIT)]
    assert calls == [("job_test", "/dev/sr0", False, "job_test")]
    assert controller.is_idle()
    assert controller._active_job_id is None


@pytest.mark.asyncio
async def test_recover_held_job_releases_gate_when_run_rip_raises():
    controller = JobController(FakeClient(), "drv_test")
    _fake_resolution(controller, _view(JobStatus.IDENTIFIED))

    async def boom(job: JobView, device_path: str) -> None:
        raise RuntimeError("boom")

    controller._run_rip = boom  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="boom"):
        await controller.recover_held_job(_view(JobStatus.AWAITING_REVIEW), "/dev/sr0")

    assert controller.is_idle()
    assert controller._active_job_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("make_error", [lambda: _http_status_error(503), lambda: httpx.ConnectError("down")])
async def test_rip_complete_retries_transient_error(monkeypatch, caplog, make_error):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.job_controller")
    monkeypatch.setattr(backend_retry_module, "PATCH_RETRY_INITIAL_SECONDS", 0.0)
    monkeypatch.setattr(backend_retry_module, "PATCH_RETRY_MAX_SECONDS", 0.0)
    client = FakeClient()
    controller = JobController(client, "drv_test")
    calls: list[str] = []
    done = _view(JobStatus.RIPPED)

    async def flaky(job_id: str) -> JobView:
        calls.append(job_id)
        if len(calls) < 3:
            raise make_error()
        return done

    client.rip_complete = flaky  # type: ignore[method-assign]

    assert await controller._backend.rip_complete("job_test") is done
    assert calls == ["job_test"] * 3
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2
    assert all(r.getMessage().startswith("rip-complete job_test failed (") for r in warnings)
    assert all(r.getMessage().endswith("); retrying in 0.0s") for r in warnings)


@pytest.mark.asyncio
async def test_rip_complete_rejected_4xx_gives_up(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.job_controller")
    monkeypatch.setattr(backend_retry_module, "PATCH_RETRY_INITIAL_SECONDS", 0.0)
    monkeypatch.setattr(backend_retry_module, "PATCH_RETRY_MAX_SECONDS", 0.0)
    client = FakeClient()
    controller = JobController(client, "drv_test")
    calls: list[str] = []

    async def reject(job_id: str) -> JobView:
        calls.append(job_id)
        raise _http_status_error(409)

    client.rip_complete = reject  # type: ignore[method-assign]

    with pytest.raises(httpx.HTTPStatusError):
        await controller._backend.rip_complete("job_test")

    assert calls == ["job_test"]
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert errors[0].getMessage().startswith("rip-complete job_test rejected by backend (")
    assert errors[0].getMessage().endswith("); giving up")
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]


@pytest.mark.asyncio
@pytest.mark.parametrize("make_error", [lambda: _http_status_error(502), lambda: httpx.ConnectError("down")])
async def test_patch_track_retries_transient_error(monkeypatch, caplog, make_error):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.job_controller")
    monkeypatch.setattr(backend_retry_module, "PATCH_RETRY_INITIAL_SECONDS", 0.0)
    monkeypatch.setattr(backend_retry_module, "PATCH_RETRY_MAX_SECONDS", 0.0)
    client = FakeClient()
    controller = JobController(client, "drv_test")
    calls: list[tuple[str, dict[str, object]]] = []

    async def flaky(track_id: str, **fields: object) -> None:
        calls.append((track_id, fields))
        if len(calls) < 3:
            raise make_error()

    client.update_track = flaky  # type: ignore[method-assign]

    await controller._backend.patch_track("trk_1", status="ripped", progress=100)

    assert calls == [("trk_1", {"status": "ripped", "progress": 100})] * 3
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2
    assert all(r.getMessage().startswith("PATCH track trk_1 failed (") for r in warnings)
    assert all(r.getMessage().endswith("); retrying in 0.0s") for r in warnings)


@pytest.mark.asyncio
async def test_patch_track_rejected_4xx_gives_up(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.job_controller")
    monkeypatch.setattr(backend_retry_module, "PATCH_RETRY_INITIAL_SECONDS", 0.0)
    monkeypatch.setattr(backend_retry_module, "PATCH_RETRY_MAX_SECONDS", 0.0)
    client = FakeClient()
    controller = JobController(client, "drv_test")
    calls: list[tuple[str, dict[str, object]]] = []

    async def reject(track_id: str, **fields: object) -> None:
        calls.append((track_id, fields))
        raise _http_status_error(422)

    client.update_track = reject  # type: ignore[method-assign]

    with pytest.raises(httpx.HTTPStatusError):
        await controller._backend.patch_track("trk_1", status="ripped")

    assert calls == [("trk_1", {"status": "ripped"})]
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert errors[0].getMessage().startswith("PATCH track trk_1 rejected by backend (")
    assert errors[0].getMessage().endswith("); giving up")
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]


# --- config lookup failure, eject back-off, unfinished tracks ---


async def test_safe_get_ripper_config_returns_config_on_success():
    client = FakeClient()
    waiter = ResolutionWaiter(client)

    config = await waiter._safe_get_ripper_config()

    assert isinstance(config, RipperConfigView)
    assert client.get_ripper_config_calls == 1


async def test_safe_get_ripper_config_returns_none_and_warns_on_http_error(caplog):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.job_controller")
    client = FakeClient()
    client.get_ripper_config_error = httpx.ConnectError("boom")
    waiter = ResolutionWaiter(client)

    assert await waiter._safe_get_ripper_config() is None

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert [r.getMessage() for r in warnings] == ["get_ripper_config failed (boom); keeping countdown suspended"]


async def test_eject_sleeps_for_positive_delay_before_retrying(monkeypatch, caplog):
    caplog.set_level(logging.DEBUG, logger="arm_ripper.job_controller")
    monkeypatch.setattr(eject_module, "EJECT_RETRY_DELAYS", (0.0, 0.5))
    sleeps: list[float] = []

    async def _record_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(eject_module.asyncio, "sleep", _record_sleep)
    results = iter([(0, ""), (1, "busy"), (0, "")])  # umount, eject 1 fails, eject 2 succeeds
    calls: list[tuple[str, ...]] = []

    async def _fake_run(*argv: str, log_failure: bool = True) -> tuple[int | None, str]:
        calls.append(argv)
        return next(results)

    controller = JobController(FakeClient(), "drv_test", device_path="/dev/sr0")
    controller._ejector._run_command = _fake_run  # type: ignore[method-assign]
    await controller._ejector.eject("/dev/sr0")

    assert sleeps == [0.5]
    assert [c[0] for c in calls] == ["umount", "eject", "eject"]
    messages = [(r.levelno, r.getMessage()) for r in caplog.records]
    assert (logging.WARNING, "eject /dev/sr0 attempt 1 failed (rc=1): busy") in messages
    assert (logging.INFO, "ejected /dev/sr0 on attempt 2") in messages


def _unfinished_track(idx: int):
    from arm_common.enums import TrackKind, TrackStatus

    return TrackView(
        id=f"trk_{idx}",
        job_id="job_test",
        kind=TrackKind.VIDEO_TITLE,
        index=idx,
        source_ref=str(idx),
        status=TrackStatus.QUEUED,
        output_path=None,
        size_bytes=None,
        duration_seconds=1800,
        attempts=0,
        last_error=None,
    )


@pytest.mark.parametrize(
    ("resumes", "reason"),
    [
        (0, "the drive disconnected mid-rip and did not come back within 180s"),
        (
            disc_rip_module.MAX_DEVICE_RESUMES,
            f"the drive disconnected mid-rip {disc_rip_module.MAX_DEVICE_RESUMES + 1} times; giving up",
        ),
    ],
)
async def test_fail_unfinished_starts_unstarted_tracks_then_fails_them(caplog, resumes, reason):
    from arm_common.enums import TrackStatus

    caplog.set_level(logging.DEBUG, logger="arm_ripper.job_controller")
    controller = JobController(FakeClient(), "drv_test")
    patches: list[tuple[str, dict[str, object]]] = []

    async def _record(track_id: str, **fields: object) -> None:
        patches.append((track_id, fields))

    controller._backend.patch_track = _record  # type: ignore[method-assign]
    tracks = [_unfinished_track(1), _unfinished_track(2), _unfinished_track(3)]
    rip = disc_rip_module.DiscRip(
        backend=controller._backend,
        ws=controller._ws,
        ejector=controller._ejector,
        device=controller._device,
        default_min_length_seconds=controller._default_min_length_seconds,
        output_dir=raw_dir_module.RAW_ROOT / "job_x",
        job_id="job_x",
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        rip_start=RipStartResponse(job_id="job_x", rip_preset_id="rpr", tracks=tracks),
    )
    rip._unfinished = {"trk_1", "trk_2"}
    rip._started = {"trk_1"}
    rip._resumes = resumes

    await rip._fail_unfinished()

    assert patches == [
        ("trk_1", {"status": TrackStatus.FAILED, "last_error": reason}),
        ("trk_2", {"status": TrackStatus.IN_PROGRESS}),
        ("trk_2", {"status": TrackStatus.FAILED, "last_error": reason}),
    ]
    assert rip._started == {"trk_1", "trk_2"}
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert errors == [f"{reason}; 2 title(s) not ripped"]


async def test_auto_start_due_is_false_for_a_timed_gate_with_no_job_view():
    """A timed review gate with no job view (a failed read) never auto-starts, and never checks the countdown."""
    waiter = ResolutionWaiter(FakeClient())

    async def _never(view: JobView) -> bool:
        raise AssertionError("the countdown must not be checked without a job view")

    waiter._review_countdown_expired = _never  # type: ignore[method-assign]

    assert await waiter._auto_start_due(None, resolution_wait_module.REVIEW_WAIT) is False


async def test_scan_failure_ends_the_pipeline_before_identify(monkeypatch, caplog, stub_eject):
    """A ScanError from the scan logs one ERROR and ends the pipeline before identify or rip-start."""

    async def _boom(_device_path: str) -> ScanResult:
        raise disc_scan_module.ScanError("no disc")

    monkeypatch.setattr(disc_scan_module, "scan_disc", _boom)
    caplog.set_level(logging.DEBUG, logger="arm_ripper.job_controller")
    client = FakeClient()
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert client.identify_calls == []
    assert client.rip_start_calls == []
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert errors == ["scan failed device=/dev/sr0 err=no disc"]


async def test_identify_in_an_unexpected_status_does_not_rip(caplog, stub_scan, stub_eject):
    """An identified job in a status outside every gate (RIPPED) logs at INFO and returns without ripping."""
    caplog.set_level(logging.DEBUG, logger="arm_ripper.job_controller")
    client = FakeClient()
    client.identify_responses.append(_job(JobStatus.RIPPED))
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert client.get_job_calls == []
    assert client.rip_start_calls == []
    infos = [r.getMessage() for r in caplog.records if r.levelno == logging.INFO]
    assert "job job_test in unexpected status ripped; not ripping" in infos


async def test_disc_inserted_while_busy_is_ignored(caplog, stub_scan, stub_eject):
    """A disc-inserted event on a busy drive is dropped at DEBUG without a config lookup or identify."""
    caplog.set_level(logging.DEBUG, logger="arm_ripper.job_controller")
    client = FakeClient()
    controller = JobController(client, "drv_test")
    async with controller._active_lock:
        assert controller.is_active
        await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert client.get_ripper_config_calls == 0
    assert client.identify_calls == []
    debugs = [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG]
    assert "disc-inserted ignored: drive already busy" in debugs


async def test_auto_rip_lookup_failure_proceeds_fail_open(caplog, stub_scan, stub_eject):
    """An HTTP error on the auto-rip config lookup warns and still runs the rip (fail-open)."""
    caplog.set_level(logging.DEBUG, logger="arm_ripper.job_controller")
    client = FakeClient()
    client.get_ripper_config_error = httpx.ConnectError("down")
    client.identify_responses.append(_job(JobStatus.IDENTIFIED, title="X"))
    controller = JobController(client, "drv_test")

    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert "auto-rip config lookup failed (down); proceeding fail-open" in warnings
    assert client.rip_start_calls == ["job_test"]
    assert client.rip_complete_calls == ["job_test"]
