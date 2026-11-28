"""A structure-scan Blu-ray ripped per title, from the rip-start answer down to the makemkvcon command lines.

Its tracks are keyed by title ref (`00800.mpls:2`), so the MakeMKV title each one is ripped as comes from
rip-start's `title_numbers`, never from the ref itself. Each ticked title is one `makemkvcon mkv … <N>` into
`title-NN` (N = the MakeMKV title number); unticked titles (SKIPPED at Start) and refs MakeMKV does not list are
never read. Only the makemkvcon subprocess and the drive-readiness gate are faked.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import arm_ripper.disc_rip as disc_rip_module
import arm_ripper.eject as eject_module
import arm_ripper.raw_dir as raw_dir_module
from arm_common import DiscType, JobStatus, RipInvocation
from arm_common.enums import TrackKind, TrackStatus
from arm_common.schemas import JobView, RipStartResponse, TrackView
from arm_ripper.drive_handle import DriveHandle
from arm_ripper.drive_poll import DriveState
from arm_ripper.drive_ready import ReadyOutcome
from arm_ripper.job_controller import JobController
from arm_ripper.rip import makemkv_rip as makemkv_rip_module
from arm_ripper.rip import optical_rip as optical_rip_module

_JOB = "job_01M4R7157QDCVQ3MX6M2VK0XX0"


def _track(n: int, ref: str, *, status: TrackStatus = TrackStatus.QUEUED) -> TrackView:
    return TrackView(
        id=f"trk_{n}",
        job_id=_JOB,
        kind=TrackKind.VIDEO_TITLE,
        index=n,
        source_ref=ref,
        status=status,
        excluded=status is TrackStatus.SKIPPED,
        output_path=None,
        size_bytes=None,
        duration_seconds=7200,
        expected_size_bytes=8,
        attempts=0,
        last_error=None,
    )


class _Client:
    def __init__(self) -> None:
        self.patches: list[tuple[str, dict[str, object]]] = []
        self.completed: list[str] = []

    async def update_track(self, track_id: str, **fields: object) -> TrackView:
        self.patches.append((track_id, fields))
        return _track(0, "x")

    async def rip_complete(self, job_id: str) -> JobView:
        self.completed.append(job_id)
        return JobView(
            id=job_id,
            drive_id="drv_x",
            disc_type=DiscType.BLURAY,
            status=JobStatus.RIPPED,
            title=None,
            year=None,
            metadata_json={},
            resumed_from_crash=False,
        )

    def done(self) -> dict[str, str]:
        return {tid: str(f["output_path"]) for tid, f in self.patches if f.get("status") == TrackStatus.DONE}

    def touched(self) -> set[str]:
        return {tid for tid, _ in self.patches}


@pytest.fixture
def makemkvcon(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[list[str]]:
    """Fake each makemkvcon run: record its argv and leave the one output file a title rip writes."""
    monkeypatch.setattr(raw_dir_module, "RAW_ROOT", tmp_path)
    monkeypatch.setattr(disc_rip_module, "EJECT_GRACE_SECONDS", 0.0)
    monkeypatch.setattr(disc_rip_module, "read_drive_status", lambda _path: DriveState.DISC_OK)

    async def _ready(_device_path: str) -> ReadyOutcome:
        return ReadyOutcome.READY

    monkeypatch.setattr(optical_rip_module, "wait_until_readable", _ready)

    async def _eject(_self: Any, _device_path: str) -> None:
        return None

    monkeypatch.setattr(eject_module.Ejector, "eject", _eject)
    runs: list[list[str]] = []

    async def _run(cmd: list[str], _state: Any, **_kw: Any) -> str | None:
        runs.append(cmd)
        out = Path(cmd[-1])
        out.mkdir(parents=True, exist_ok=True)
        (out / "Feature_t00.mkv").write_bytes(b"x" * 8)
        return None

    monkeypatch.setattr(makemkv_rip_module, "run_makemkvcon", _run)
    return runs


async def test_ticked_refs_rip_as_their_makemkv_title_numbers_and_the_rest_are_never_read(
    makemkvcon: list[list[str]], tmp_path: Path
) -> None:
    tracks = [
        _track(0, "00010.mpls"),
        _track(1, "00800.mpls:1", status=TrackStatus.SKIPPED),  # the other angle, unticked at Start
        _track(2, "00800.mpls:2"),
        _track(3, "00102.mpls", status=TrackStatus.SKIPPED),  # a playlist MakeMKV does not list
    ]
    numbers = {"00010.mpls": 3, "00800.mpls:1": 6, "00800.mpls:2": 7}
    client = _Client()
    controller = JobController(client, "drv_x", device_path=DriveHandle("/dev/sr0"))  # type: ignore[arg-type]

    await controller._execute_rip(
        job_id=_JOB,
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        rip_start=RipStartResponse(
            job_id=_JOB,
            rip_preset_id="rpr",
            tracks=tracks,
            title_numbers=numbers,
            rip_invocation=RipInvocation.PER_TITLE,
            end_on_completion_message=False,
        ),
    )

    raw = tmp_path / _JOB
    assert [(cmd[1], cmd[-2], cmd[-1]) for cmd in makemkvcon] == [
        ("mkv", "3", str(raw / "title-03")),
        ("mkv", "7", str(raw / "title-07")),
    ]
    assert client.done() == {
        "trk_0": str(raw / "title-03" / "Feature_t00.mkv"),
        "trk_2": str(raw / "title-07" / "Feature_t00.mkv"),
    }
    assert client.touched() == {"trk_0", "trk_2"}
    assert client.completed == [_JOB]
