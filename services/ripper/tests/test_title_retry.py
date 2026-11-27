"""One title's rip and its single retry when the drive, not the title, made it fail."""

from pathlib import Path

import pytest

from arm_common.enums import TrackKind, TrackStatus
from arm_common.schemas import TrackView
from arm_ripper.drive_poll import DriveState
from arm_ripper.drive_ready import Probe, ReadyOutcome
from arm_ripper.rip.makemkv_process import STOPPED_ERROR
from arm_ripper.rip.result import RipResult
from arm_ripper.rip.title_retry import TITLE_RETRIES, rip_title_with_retry

_TRACK = TrackView(
    id="trk_1",
    job_id="job_01M4R7157QDCVQ3MX6M2VK0XX0",
    kind=TrackKind.VIDEO_TITLE,
    index=1,
    source_ref="1",
    status=TrackStatus.QUEUED,
    output_path=None,
    size_bytes=None,
    duration_seconds=1800,
    expected_size_bytes=10,
    attempts=0,
    last_error=None,
)
_OK = RipResult(ok=True, output_path=Path("/x.mkv"), size_bytes=4)
_NOT_READY = RipResult(ok=False, error="makemkvcon failed: SCSI NOT READY")
_BAD_TITLE = RipResult(ok=False, error="Failed to save title 1")


class _Rig:
    """Scripted attempts, drive probe and gate; records what the retry did."""

    def __init__(self, results: list[RipResult | None], *, state=DriveState.DISC_OK, gate=ReadyOutcome.READY) -> None:
        self.results = list(results)
        self.state = state
        self.gate = gate
        self.attempts = 0
        self.gates = 0
        self.reported: list[RipResult] = []

    async def attempt(self, on_done) -> None:
        self.attempts += 1
        result = self.results.pop(0)
        if result is not None:
            await on_done(_TRACK, result)

    def probe(self, _path: str) -> Probe:
        return Probe(self.state, False)

    async def wait_ready(self, _path: str) -> ReadyOutcome:
        self.gates += 1
        return self.gate

    async def on_done(self, _track: TrackView, result: RipResult) -> None:
        self.reported.append(result)

    async def run(self, folder: Path) -> RipResult:
        return await rip_title_with_retry(
            track=_TRACK,
            device_path="/dev/sr0",
            folder=folder,
            run_attempt=self.attempt,
            on_track_done=self.on_done,
            probe=self.probe,
            wait_ready=self.wait_ready,
        )


async def test_a_title_that_rips_is_reported_once_with_no_gate_or_retry(tmp_path) -> None:
    rig = _Rig([_OK])
    assert await rig.run(tmp_path) is _OK
    assert (rig.attempts, rig.gates, rig.reported) == (1, 0, [_OK])


async def test_a_drive_transient_failure_is_retried_once_after_the_gate_and_reports_the_retry(tmp_path) -> None:
    folder = tmp_path / "title-01"
    folder.mkdir()
    (folder / "partial.mkv").write_bytes(b"x")
    rig = _Rig([_NOT_READY, _OK])
    await rig.run(folder)
    assert (rig.attempts, rig.gates, rig.reported) == (2, 1, [_OK])
    assert not folder.exists()  # the failed attempt's partial file is gone before the retry


async def test_a_title_that_is_transient_twice_is_reported_failed_after_one_retry(tmp_path) -> None:
    rig = _Rig([_NOT_READY, _NOT_READY, _OK])
    await rig.run(tmp_path)
    assert TITLE_RETRIES == 1
    assert (rig.attempts, rig.gates, rig.reported) == (2, 1, [_NOT_READY])


async def test_a_real_failure_on_a_ready_drive_is_not_retried(tmp_path) -> None:
    rig = _Rig([_BAD_TITLE])
    await rig.run(tmp_path)
    assert (rig.attempts, rig.gates, rig.reported) == (1, 0, [_BAD_TITLE])


async def test_a_failure_with_the_drive_not_ready_is_transient_whatever_the_text_says(tmp_path) -> None:
    rig = _Rig([_BAD_TITLE, _OK], state=DriveState.NOT_READY)
    await rig.run(tmp_path)
    assert (rig.attempts, rig.reported) == (2, [_OK])


async def test_a_drive_that_went_away_is_left_to_the_resume_path(tmp_path) -> None:
    rig = _Rig([_NOT_READY], state=DriveState.ABSENT)
    await rig.run(tmp_path)
    assert (rig.attempts, rig.gates, rig.reported) == (1, 0, [_NOT_READY])


async def test_a_stopped_attempt_is_not_retried(tmp_path) -> None:
    stopped = RipResult(ok=False, error=STOPPED_ERROR)
    rig = _Rig([stopped], state=DriveState.NOT_READY)
    await rig.run(tmp_path)
    assert (rig.attempts, rig.reported) == (1, [stopped])


@pytest.mark.parametrize("gate", [ReadyOutcome.TIMED_OUT, ReadyOutcome.LEFT_DISC, ReadyOutcome.ABSENT])
async def test_a_drive_that_does_not_come_back_gets_no_retry(tmp_path, gate: ReadyOutcome) -> None:
    rig = _Rig([_NOT_READY, _OK], gate=gate)
    await rig.run(tmp_path)
    assert (rig.attempts, rig.gates, rig.reported) == (1, 1, [_NOT_READY])


async def test_an_attempt_that_reports_nothing_is_a_failure(tmp_path) -> None:
    rig = _Rig([None])
    result = await rig.run(tmp_path)
    assert result.ok is False
    assert rig.reported == [result]
