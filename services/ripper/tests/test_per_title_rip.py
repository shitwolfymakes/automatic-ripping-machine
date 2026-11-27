"""The per-title DVD/BD rip: one makemkvcon invocation per selected title, behind the drive-readiness gate."""

import asyncio
import functools
from pathlib import Path
from typing import Any

import pytest

from arm_common.enums import TrackKind, TrackStatus
from arm_common.schemas import TrackView
from arm_ripper.drive_poll import DriveState
from arm_ripper.drive_ready import Probe, ReadyOutcome
from arm_ripper.rip import optical_rip as optical_rip_module
from arm_ripper.rip.makemkv_process import STOPPED_ERROR
from arm_ripper.rip.makemkv_rip import RipDiscResult
from arm_ripper.rip.result import RipResult

_JOB = "job_01M4R7157QDCVQ3MX6M2VK0XX0"
_NOT_READY_ERROR = "makemkvcon failed: SCSI NOT READY, LOGICAL UNIT IS IN PROCESS OF BECOMING READY"


def _track(idx: int, *, expected: int | None = 10, duration: int = 1800) -> TrackView:
    return TrackView(
        id=f"trk_{idx}",
        job_id=_JOB,
        kind=TrackKind.VIDEO_TITLE,
        index=idx,
        source_ref=str(idx),
        status=TrackStatus.QUEUED,
        output_path=None,
        size_bytes=None,
        duration_seconds=duration,
        expected_size_bytes=expected,
        attempts=0,
        last_error=None,
    )


class _Rig:
    """Fakes rip_disc (scripted per title) and the gate; collects everything the rip reports."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, gates: list[ReadyOutcome] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.events: list[str] = []
        self.done: list[tuple[str, bool, str | None]] = []
        self.started: list[str] = []
        self.progress: list[tuple[str, float]] = []
        self.failures: dict[int, list[str]] = {}
        self.stop_after: int | None = None
        self.stop: asyncio.Event | None = None
        self._gates = gates

        async def fake_rip_disc(**kw: Any) -> RipDiscResult:
            return await self._rip_disc(**kw)

        async def fake_gate(_path: str) -> ReadyOutcome:
            self.events.append("gate")
            return self._gates.pop(0) if self._gates else ReadyOutcome.READY

        monkeypatch.setattr(optical_rip_module, "rip_disc", fake_rip_disc)
        monkeypatch.setattr(optical_rip_module, "wait_until_readable", fake_gate)
        monkeypatch.setattr(
            optical_rip_module,
            "rip_title_with_retry",
            functools.partial(
                optical_rip_module.rip_title_with_retry,
                probe=lambda _p: Probe(DriveState.DISC_OK, True),
                wait_ready=self._retry_gate,
            ),
        )

    async def _retry_gate(self, _path: str) -> ReadyOutcome:
        self.events.append("retry-gate")
        return ReadyOutcome.READY

    async def _rip_disc(self, **kw: Any) -> RipDiscResult:
        self.calls.append(kw)
        title = kw["title"]
        self.events.append(f"rip-{title}")
        for fraction in (0.0, 0.5, 1.0):
            await kw["on_title_progress"](title, fraction)
        if self.failures.get(title):
            return RipDiscResult(overall_error=self.failures[title].pop(0), titles={})
        out: Path = kw["output_dir"]
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"Disc_t{0:02d}.mkv"
        path.write_bytes(b"x" * 4)
        if self.stop_after is not None and len(self.calls) == self.stop_after:
            kw["stop"].set()
        return RipDiscResult(overall_error=None, titles={title: RipResult(ok=True, output_path=path, size_bytes=4)})

    async def rip(
        self, tmp_path: Path, tracks: list[TrackView], skip: set[str] = frozenset(), *, with_progress: bool = True
    ) -> None:
        async def on_start(track: TrackView) -> None:
            self.started.append(track.id)

        async def on_done(track: TrackView, result: RipResult) -> None:
            self.done.append((track.id, result.ok, result.error))

        async def on_progress(track: TrackView, fraction: float, _stats: Any = None, /) -> None:
            self.progress.append((track.id, fraction))

        await optical_rip_module.rip_optical(
            device_path="/dev/sr0",
            tracks=tracks,
            output_dir=tmp_path,
            on_track_start=on_start,
            on_track_done=on_done,
            on_track_progress=on_progress if with_progress else None,
            min_length_seconds=60,
            stop=self.stop,
            skip_track_ids=skip,
            per_title=True,
        )


async def test_each_selected_title_is_ripped_alone_with_the_minlength_after_its_gate(monkeypatch, tmp_path) -> None:
    rig = _Rig(monkeypatch)
    await rig.rip(tmp_path, [_track(1), _track(3)])

    assert [(c["title"], c["minlength_seconds"], c["eligible_source_indexes"]) for c in rig.calls] == [
        (1, 60, [1]),
        (3, 60, [3]),
    ]
    assert [c["output_dir"] for c in rig.calls] == [tmp_path / "title-01", tmp_path / "title-03"]
    assert rig.events == ["gate", "rip-1", "gate", "rip-3"]
    assert sorted(rig.done) == [("trk_1", True, None), ("trk_3", True, None)]


async def test_a_title_that_was_not_selected_is_never_read(monkeypatch, tmp_path) -> None:
    # The disc has titles 0..3; only 1 and 3 are selected, so only they arrive.
    rig = _Rig(monkeypatch)
    await rig.rip(tmp_path, [_track(1), _track(3)])
    assert {c["title"] for c in rig.calls} == {1, 3}


async def test_a_settled_title_is_not_read_again(monkeypatch, tmp_path) -> None:
    rig = _Rig(monkeypatch)
    await rig.rip(tmp_path, [_track(0), _track(1), _track(3)], {"trk_0"})
    assert [c["title"] for c in rig.calls] == [1, 3]
    assert "trk_0" not in rig.started


async def test_a_selected_title_below_the_minimum_length_fails_without_being_read(monkeypatch, tmp_path) -> None:
    rig = _Rig(monkeypatch)
    await rig.rip(tmp_path, [_track(1), _track(2, duration=30)])
    assert [c["title"] for c in rig.calls] == [1]
    failed = {tid: err for tid, ok, err in rig.done if not ok}
    assert "below minlength=60s" in (failed["trk_2"] or "")
    assert "trk_2" in rig.started


async def test_a_drive_transient_failure_is_retried_once_and_the_title_is_done(monkeypatch, tmp_path) -> None:
    rig = _Rig(monkeypatch)
    rig.failures = {1: [_NOT_READY_ERROR]}
    await rig.rip(tmp_path, [_track(1), _track(3)])

    assert [c["title"] for c in rig.calls] == [1, 1, 3]
    assert rig.events == ["gate", "rip-1", "retry-gate", "rip-1", "gate", "rip-3"]
    assert sorted(rig.done) == [("trk_1", True, None), ("trk_3", True, None)]


async def test_a_title_failing_twice_on_a_not_ready_drive_is_failed_and_the_rest_still_rip(
    monkeypatch, tmp_path
) -> None:
    rig = _Rig(monkeypatch)
    rig.failures = {1: [_NOT_READY_ERROR, _NOT_READY_ERROR]}
    await rig.rip(tmp_path, [_track(1), _track(3)])

    assert [c["title"] for c in rig.calls] == [1, 1, 3]
    assert ("trk_1", False, _NOT_READY_ERROR) in rig.done
    assert ("trk_3", True, None) in rig.done


async def test_a_real_failure_is_reported_without_a_retry(monkeypatch, tmp_path) -> None:
    rig = _Rig(monkeypatch)
    rig.failures = {1: ["makemkvcon failed: Failed to save title 1"]}
    await rig.rip(tmp_path, [_track(1)])
    assert [c["title"] for c in rig.calls] == [1]
    assert rig.done == [("trk_1", False, "makemkvcon failed: Failed to save title 1")]


async def test_a_drive_that_is_gone_before_a_title_leaves_the_rest_stopped_for_a_resume(monkeypatch, tmp_path) -> None:
    rig = _Rig(monkeypatch, gates=[ReadyOutcome.READY, ReadyOutcome.ABSENT])
    await rig.rip(tmp_path, [_track(1), _track(2), _track(3)])

    assert [c["title"] for c in rig.calls] == [1]
    assert sorted(rig.done) == [
        ("trk_1", True, None),
        ("trk_2", False, STOPPED_ERROR),
        ("trk_3", False, STOPPED_ERROR),
    ]
    assert "trk_2" not in rig.started


@pytest.mark.parametrize("gate", [ReadyOutcome.TIMED_OUT, ReadyOutcome.LEFT_DISC])
async def test_a_drive_that_is_not_ready_fails_the_remaining_titles_with_the_reason(
    monkeypatch, tmp_path, gate: ReadyOutcome
) -> None:
    rig = _Rig(monkeypatch, gates=[gate])
    await rig.rip(tmp_path, [_track(1), _track(2)])

    assert rig.calls == []
    reason = f"the drive was not ready to rip this title ({gate.value})"
    assert sorted(rig.done) == [("trk_1", False, reason), ("trk_2", False, reason)]
    assert sorted(rig.started) == ["trk_1", "trk_2"]


async def test_the_titles_not_reached_are_reported_stopped_once_the_drive_drops(monkeypatch, tmp_path) -> None:
    rig = _Rig(monkeypatch)
    rig.stop = asyncio.Event()
    rig.stop_after = 1
    await rig.rip(tmp_path, [_track(1), _track(2), _track(3)])

    assert [c["title"] for c in rig.calls] == [1]
    assert {("trk_2", False, STOPPED_ERROR), ("trk_3", False, STOPPED_ERROR)} <= set(rig.done)


async def test_progress_is_disc_wide_and_never_goes_back_across_three_titles(monkeypatch, tmp_path) -> None:
    rig = _Rig(monkeypatch)
    await rig.rip(tmp_path, [_track(1, expected=10), _track(2, expected=30), _track(3, expected=60)])

    fractions = [f for _tid, f in rig.progress]
    assert fractions == sorted(fractions)
    assert fractions[0] == 0.0
    assert fractions[-1] == pytest.approx(1.0)
    # Title 2 at half: title 1's 10 and half of 30, over 100.
    assert fractions[4] == pytest.approx(0.25)
    assert [tid for tid, _f in rig.progress[3:6]] == ["trk_2"] * 3


async def test_progress_stays_monotonic_when_a_title_is_retried(monkeypatch, tmp_path) -> None:
    rig = _Rig(monkeypatch)
    rig.failures = {1: [_NOT_READY_ERROR]}
    await rig.rip(tmp_path, [_track(1, expected=50), _track(2, expected=50)])
    fractions = [f for _tid, f in rig.progress]
    assert fractions == sorted(fractions)


async def test_a_rip_with_no_progress_listener_still_rips(monkeypatch, tmp_path) -> None:
    rig = _Rig(monkeypatch)
    await rig.rip(tmp_path, [_track(1)], with_progress=False)
    assert rig.done == [("trk_1", True, None)]
