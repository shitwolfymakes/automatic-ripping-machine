"""JobController behaviour with a fake BackendClient and stubbed scan."""

import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone

import httpx
import pytest

import arm_ripper.job_controller as jc_module
from arm_common import DiscType, Job, JobStatus
from arm_common.schemas import (
    JobView,
    RipperConfigView,
    RipStartResponse,
    ScanResult,
    TrackView,
    WSEnvelope,
)
from arm_ripper.job_controller import JobController


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
) -> JobView:
    return JobView(
        id="job_test",
        drive_id="drv_test",
        disc_type=DiscType.DVD,
        status=status,
        title=title,
        year=None,
        metadata_json={},
        resumed_from_crash=False,
        wait_start_time=wait_start_time,
        manual_pause=manual_pause,
    )


class FakeClient:
    def __init__(self) -> None:
        self.identify_responses: deque[Job] = deque()
        self.get_job_responses: deque[JobView] = deque()
        self.identify_calls: list[ScanResult] = []
        self.identify_pending_session_ids: list[str | None] = []
        self.get_job_calls: list[str] = []
        self.rip_start_calls: list[str] = []
        self.rip_complete_calls: list[str] = []
        self.auto_rip_on_insert: bool = True
        self.makemkv_key: str | None = None
        self.get_ripper_config_error: Exception | None = None
        self.get_ripper_config_calls: int = 0
        self.community_keydb_enabled: bool = True
        self.ripping_paused: bool = False
        self.manual_wait_seconds: int = 60
        self.keydb_reports: list = []

    async def identify(
        self,
        *,
        drive_id: str,
        scan_result: ScanResult,
        pending_session_id: str | None = None,
    ) -> Job:
        self.identify_calls.append(scan_result)
        self.identify_pending_session_ids.append(pending_session_id)
        return self.identify_responses.popleft()

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
        )

    async def report_keydb_status(self, *, state, vuk_count=None, age_days=None) -> None:
        self.keydb_reports.append((state, vuk_count, age_days))


@pytest.fixture(autouse=True)
def fast_polls(monkeypatch, tmp_path):
    """Don't wait 5+ seconds between polls; write under tmp_path, not /raw."""
    monkeypatch.setattr(jc_module, "POLL_INITIAL_SECONDS", 0.0)
    monkeypatch.setattr(jc_module, "POLL_MAX_SECONDS", 0.01)
    monkeypatch.setattr(jc_module, "EJECT_GRACE_SECONDS", 0.0)
    monkeypatch.setattr(jc_module, "RAW_ROOT", tmp_path)
    # WS-driven resolution path: collapse the boot-race grace window so
    # tests fall straight through to the REST fallback path that the
    # FakeClient feeds.
    monkeypatch.setattr(jc_module, "RESOLUTION_WS_FIRST_WAIT_SECONDS", 0.0)
    monkeypatch.setattr(jc_module, "RESOLUTION_WAIT_TIMEOUT_SECONDS", 1.0)


@pytest.fixture
def stub_eject(monkeypatch):
    async def _noop_eject(self, device_path: str) -> None:
        return None

    monkeypatch.setattr(jc_module.JobController, "_eject_with_retry", _noop_eject)


@pytest.fixture
def stub_scan(monkeypatch):
    async def _scan(_device_path: str) -> ScanResult:
        return ScanResult(disc_type=DiscType.DVD, volume_label="TEST")

    monkeypatch.setattr(jc_module, "scan_disc", _scan)


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
    monkeypatch.setattr(jc_module, "RESOLUTION_WAIT_TIMEOUT_SECONDS", 0.05)
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
    monkeypatch.setattr(jc_module, "RESOLUTION_WAIT_TIMEOUT_SECONDS", 0.05)
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


async def test_rip_start_ws_command_wakes_review_waiter():
    """A `rip.start` WS command sets the per-job wait Event (the review-gate
    analogue of identify.resolved)."""
    client = FakeClient()
    controller = JobController(client, "drv_test")
    event = asyncio.Event()
    controller._resolution_events["job_test"] = event

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


async def test_ws_event_unblocks_resolution_faster_than_rest(monkeypatch, stub_scan, stub_eject):
    """An identify.resolved WS event makes _await_resolution return immediately.

    Confirms the new WS-driven path: registering the handler is enough; we
    don't need the slow REST fallback to do the work.
    """
    monkeypatch.setattr(jc_module, "RESOLUTION_WS_FIRST_WAIT_SECONDS", 5.0)
    monkeypatch.setattr(jc_module, "RESOLUTION_WAIT_TIMEOUT_SECONDS", 30.0)

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
    # still does config lookups inside the pipeline: one for the MakeMKV key
    # and one for the community-keydb toggle.
    assert client.get_ripper_config_calls == 2
    assert client.identify_pending_session_ids == ["sess_test"]
    assert client.rip_start_calls == ["job_test"]
    assert client.rip_complete_calls == ["job_test"]


async def test_pipeline_refreshes_makemkv_key_before_scan(monkeypatch, stub_scan, stub_eject):
    """The key is refreshed once, before the scan probe, with the configured key."""
    keys: list[str | None] = []

    async def _record(key: str | None = None) -> None:
        keys.append(key)

    monkeypatch.setattr(jc_module, "refresh_makemkv_key", _record)

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

    monkeypatch.setattr(jc_module, "refresh_makemkv_key", _record)

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

    monkeypatch.setattr(jc_module, "refresh_community_keydb", _boom)

    client = FakeClient()
    client.community_keydb_enabled = True
    controller = JobController(client, "drv_test")
    controller._spawn_keydb_refresh(enabled=True)
    await controller._drain_keydb_tasks()
    assert calls == [True]  # ran once; the RuntimeError was swallowed (this line proves no propagation)


@pytest.mark.asyncio
async def test_keydb_refresh_reports_result(monkeypatch):
    from arm_common import KeydbState
    from arm_ripper.community_keydb import KeydbResult

    async def _ok(*, script_path="/usr/local/bin/update_keydb.sh", enabled=True):
        return KeydbResult(state=KeydbState.OK, vuk_count=42, age_days=None)

    monkeypatch.setattr(jc_module, "refresh_community_keydb", _ok)
    client = FakeClient()
    controller = JobController(client, "drv_test")
    controller._spawn_keydb_refresh(enabled=True)
    await controller._drain_keydb_tasks()
    assert client.keydb_reports == [(KeydbState.OK, 42, None)]


async def test_eject_runs_umount_then_eject_until_success(monkeypatch):
    monkeypatch.setattr(jc_module, "EJECT_RETRY_DELAYS", (0.0, 0.0, 0.0))

    invocations: list[tuple[str, ...]] = []
    rc_sequence = iter([1, 1, 1, 0])  # umount fails, eject 1+2 fail, eject 3 succeeds

    async def _fake_run(*argv: str, log_failure: bool = True) -> tuple[int | None, str]:
        invocations.append(argv)
        return next(rc_sequence), "Device or resource busy"

    monkeypatch.setattr(JobController, "_run_command", staticmethod(_fake_run))
    controller = JobController(FakeClient(), "drv_test")
    await controller._eject_with_retry("/dev/sr0")

    assert invocations[0] == ("umount", "/dev/sr0")
    assert all(call[0] == "eject" for call in invocations[1:])
    assert len(invocations) == 4


async def test_eject_gives_up_after_all_attempts(monkeypatch, caplog):
    monkeypatch.setattr(jc_module, "EJECT_RETRY_DELAYS", (0.0, 0.0))

    async def _always_busy(*argv: str, log_failure: bool = True) -> tuple[int | None, str]:
        return 1, "Device or resource busy"

    monkeypatch.setattr(JobController, "_run_command", staticmethod(_always_busy))
    controller = JobController(FakeClient(), "drv_test")
    with caplog.at_level("ERROR", logger="arm_ripper.job_controller"):
        await controller._eject_with_retry("/dev/sr0")

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
    monkeypatch.setattr(jc_module, "PATCH_RETRY_INITIAL_SECONDS", 0.0)
    monkeypatch.setattr(jc_module, "PATCH_RETRY_MAX_SECONDS", 0.0)

    controller = JobController(client, "drv_test")
    await asyncio.wait_for(controller.handle_disc_inserted("/dev/sr0"), timeout=2.0)

    assert call_count == 3
    assert client.rip_complete_calls == ["job_test"]
