"""fail_job, the scan-failure text and the identify branch that fails a job for a scan failure."""

from __future__ import annotations

import re
from typing import Any

import pytest

from arm_backend import identify_flow
from arm_backend.job_failure import fail_job
from arm_common import Drive, DriveStatus, Job, JobStatus, SessionApplication
from arm_common.enums import DiscType, ScanFailureReason, SessionApplicationStatus
from arm_common.schemas import IdentifyRequest, ScanFailure, ScanResult

from tests._fakes import FakeSession

_JOB_ID = "job_01JZXR7K3M5Q8N4VWA00000001"


class _Hub:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def emit(self, topic: str, event_type: str, payload: dict[str, Any], **kw: Any) -> None:
        self.events.append({"topic": topic, "event_type": event_type, "payload": payload, **kw})


def _job(status: JobStatus = JobStatus.IDENTIFIED) -> Job:
    return Job(id=_JOB_ID, drive_id="drv_x", disc_type=DiscType.BLURAY, status=status)


async def test_fail_job_fails_the_job_with_the_reason() -> None:
    db, hub, job = FakeSession(), _Hub(), _job()
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_1", session_id="ses_x", job_id=_JOB_ID, status=SessionApplicationStatus.WAITING_IDENTIFY
        )
    ]

    await fail_job(db, hub, job, "why it failed")  # type: ignore[arg-type]

    assert job.status == JobStatus.FAILED
    assert job.failure_reason == "why it failed"
    assert job.ripped_at is not None
    assert db.rows["session_applications"][0].status == SessionApplicationStatus.CANCELLED
    assert db.committed == 1
    [event] = hub.events
    assert (event["event_type"], event["topic"], event["job_id"]) == ("rip.failed", "ripper.events", _JOB_ID)
    assert event["payload"] == {
        "job_id": _JOB_ID,
        "drive_id": "drv_x",
        "status": "failed",
        "tracks_done": 0,
        "tracks_failed": 0,
        "tracks_total": 0,
        "reason": "why it failed",
    }


@pytest.mark.parametrize("reason", list(ScanFailureReason))
def test_failure_text_is_a_sentence_for_every_reason(reason: ScanFailureReason) -> None:
    text = identify_flow._failure_text(ScanFailure(reason=reason, detail="the detail"))
    assert text.endswith(".")
    assert len(text) > 40


def test_failure_texts_differ_per_reason() -> None:
    texts = {identify_flow._failure_text(ScanFailure(reason=r, detail="d")) for r in ScanFailureReason}
    assert len(texts) == len(ScanFailureReason)


def test_failure_text_names_no_ip_address_for_an_unknown_key() -> None:
    text = identify_flow._failure_text(ScanFailure(reason=ScanFailureReason.VOLUME_KEY_UNKNOWN, detail="d"))
    assert "volume key is unknown" in text
    assert "HTTPS (TCP 443)" in text
    assert not re.search(r"\d+\.\d+\.\d+\.\d+", text)


class _NoCalls:
    """Fails the test if the flow touches it."""

    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"unexpected call: {name}")


async def test_run_with_a_scan_failure_fails_the_job_and_does_nothing_else() -> None:
    from arm_backend.constants import CONFIG_SINGLETON_ID
    from arm_common import Config

    db, hub = FakeSession(), _Hub()
    db.rows["drives"] = [Drive(id="drv_x", hostname="h", device_path="/dev/sr0", status=DriveStatus.ONLINE)]
    db.rows["config"] = [Config(id=CONFIG_SINGLETON_ID)]
    scan = ScanResult(
        disc_type=DiscType.BLURAY,
        failure=ScanFailure(reason=ScanFailureReason.DISC_OPEN_FAILED, detail="d", output_tail=["x"]),
    )
    flow = identify_flow.IdentifyFlow(
        req=IdentifyRequest(drive_id="drv_x", scan_result=scan),
        thediscdb_store=None,
        session=db,  # type: ignore[arg-type]
        dispatcher=_NoCalls(),  # type: ignore[arg-type]
        hub=hub,  # type: ignore[arg-type]
        stage_runner=None,
    )

    job = await flow.run()

    assert job.status == JobStatus.FAILED
    assert job.disc_type == DiscType.BLURAY
    assert job.failure_reason == identify_flow._failure_text(scan.failure)  # type: ignore[arg-type]
    assert job.title is None
    assert [r for r in db.added if type(r).__name__ == "DiscFingerprint"] == []
    assert [e["event_type"] for e in hub.events] == ["rip.failed"]
