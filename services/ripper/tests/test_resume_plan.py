"""How a resumed rip chooses between one `mkv all` and one invocation per unsettled title."""

import asyncio
import logging
from pathlib import Path
from typing import Any

import pytest

from arm_common import ResumeMode
from arm_common.enums import TrackKind, TrackStatus
from arm_common.schemas import ResumePolicy, TrackView
from arm_ripper.rip import optical_rip as optical_rip_module
from arm_ripper.rip.makemkv_process import STOPPED_ERROR
from arm_ripper.rip.makemkv_rip import RipDiscResult
from arm_ripper.rip.result import RipResult
from arm_ripper.rip.resume_plan import log_resume_plan, plan_resume

_JOB = "job_01M4R7157QDCVQ3MX6M2VK0XX0"


def _track(idx: int, *, expected: int | None, duration: int = 1800) -> TrackView:
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


def _auto(pct: int = 50) -> ResumePolicy:
    return ResumePolicy(mode=ResumeMode.AUTO, per_title_max_remaining_pct=pct)


# ---- plan_resume ------------------------------------------------------------


@pytest.mark.parametrize(("pct", "per_title"), [(25, True), (24, False), (26, True)])
def test_auto_rips_per_title_up_to_the_remaining_percentage(pct: int, per_title: bool) -> None:
    # 25 of the 100 bytes `mkv all` would read are left.
    tracks = [_track(0, expected=75), _track(1, expected=25)]
    plan = plan_resume(tracks, {"trk_0"}, 120, _auto(pct))
    assert plan.per_title is per_title
    assert plan.remaining_pct == 25.0
    assert (plan.remaining_bytes, plan.mkv_all_bytes, plan.settled_bytes, plan.remaining_titles) == (25, 100, 75, 1)


def test_mkv_all_counts_unselected_titles_but_not_ones_below_the_minimum_length() -> None:
    # trk_2 is too short for `mkv all` to read; nothing settled yet, so all eligible bytes are left.
    tracks = [_track(0, expected=60), _track(1, expected=40), _track(2, expected=1000, duration=60)]
    plan = plan_resume(tracks, set(), 120, _auto())
    assert plan.mkv_all_bytes == 100
    assert plan.remaining_bytes == 100
    assert plan.per_title is False


def test_auto_falls_back_to_mkv_all_when_a_size_is_unknown() -> None:
    tracks = [_track(0, expected=100), _track(1, expected=None)]
    plan = plan_resume(tracks, {"trk_0"}, 120, _auto())
    assert plan.per_title is False
    assert plan.remaining_pct is None
    assert "unknown" in plan.reason


def test_auto_reads_nothing_more_when_every_eligible_title_is_settled() -> None:
    tracks = [_track(0, expected=100), _track(1, expected=50, duration=60)]
    plan = plan_resume(tracks, {"trk_0"}, 120, _auto(0))
    assert plan.per_title is True
    assert plan.remaining_titles == 0


@pytest.mark.parametrize(("mode", "per_title"), [(ResumeMode.MKV_ALL, False), (ResumeMode.PER_TITLE, True)])
def test_a_forced_mode_wins_over_the_data(mode: ResumeMode, per_title: bool) -> None:
    # 1% left would pick per title in auto; 99% would pick mkv all.
    for settled, expected in (({"trk_0"}, (99, 1)), ({"trk_1"}, (1, 99))):
        tracks = [_track(0, expected=expected[0]), _track(1, expected=expected[1])]
        plan = plan_resume(tracks, settled, 120, ResumePolicy(mode=mode))
        assert plan.per_title is per_title
        assert plan.reason == f"ARM_RESUME_MODE={mode.value}"


def test_the_plan_is_logged_as_a_resume_plan_event_with_its_inputs(caplog: pytest.LogCaptureFixture) -> None:
    tracks = [_track(0, expected=75), _track(1, expected=25)]
    policy = _auto(30)
    plan = plan_resume(tracks, {"trk_0"}, 120, policy)
    with caplog.at_level(logging.INFO, logger="arm_ripper.job_controller"):
        log_resume_plan(plan, policy)
    record = next(r for r in caplog.records if getattr(r, "event", None) == "rip.resume_plan")
    fields = record.__dict__
    assert fields["path"] == "per_title"
    assert fields["mode"] == "auto"
    assert fields["per_title_max_remaining_pct"] == 30
    assert (fields["remaining_bytes"], fields["mkv_all_bytes"], fields["settled_bytes"]) == (25, 100, 75)
    assert fields["remaining_pct"] == 25.0
    assert fields["remaining_titles"] == 1


def test_resume_policy_rejects_a_percentage_outside_0_to_100() -> None:
    with pytest.raises(ValueError):
        ResumePolicy(per_title_max_remaining_pct=101)


# ---- the per-title rip path -------------------------------------------------


def _fake_rip_disc(monkeypatch: pytest.MonkeyPatch, *, stop_after: int | None = None) -> list[dict[str, Any]]:
    """Replace rip_disc: each call writes one title file into its folder; returns each call's kwargs."""
    calls: list[dict[str, Any]] = []

    async def fake(**kw: Any) -> RipDiscResult:
        calls.append(kw)
        out: Path = kw["output_dir"]
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"Disc_t{kw['title']:02d}.mkv"
        path.write_bytes(b"x" * 4)
        if stop_after is not None and len(calls) == stop_after:
            kw["stop"].set()
        return RipDiscResult(
            overall_error=None, titles={kw["title"]: RipResult(ok=True, output_path=path, size_bytes=4)}
        )

    monkeypatch.setattr(optical_rip_module, "rip_disc", fake)
    return calls


async def _rip_per_title(
    tmp_path: Path, tracks: list[TrackView], skip: set[str], stop=None
) -> list[tuple[str, bool, str | None]]:
    done: list[tuple[str, bool, str | None]] = []

    async def on_start(_track: TrackView) -> None:
        return None

    async def on_done(track: TrackView, result: RipResult) -> None:
        done.append((track.id, result.ok, result.error))

    await optical_rip_module.rip_optical(
        device_path="/dev/sr0",
        tracks=tracks,
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
        on_track_progress=None,
        min_length_seconds=120,
        stop=stop,
        skip_track_ids=skip,
        per_title=True,
    )
    return done


async def test_per_title_reads_only_the_unsettled_titles_each_into_its_own_folder(monkeypatch, tmp_path) -> None:
    calls = _fake_rip_disc(monkeypatch)
    tracks = [_track(0, expected=100), _track(1, expected=10), _track(3, expected=10)]

    done = await _rip_per_title(tmp_path, tracks, {"trk_0"})

    assert [(c["title"], c["eligible_source_indexes"], c["output_dir"]) for c in calls] == [
        (1, [1], tmp_path / "title-01"),
        (3, [3], tmp_path / "title-03"),
    ]
    assert sorted(done) == [("trk_1", True, None), ("trk_3", True, None)]


async def test_per_title_reports_the_titles_not_reached_as_stopped_once_the_drive_drops(monkeypatch, tmp_path) -> None:
    _fake_rip_disc(monkeypatch, stop_after=1)
    tracks = [_track(1, expected=10), _track(2, expected=10), _track(3, expected=10)]

    done = await _rip_per_title(tmp_path, tracks, set(), stop=asyncio.Event())

    # The first title's own pass sees the stop and fails it; the two never reached are reported stopped.
    stopped = [tid for tid, ok, err in done if not ok and err == STOPPED_ERROR]
    assert {"trk_2", "trk_3"} <= set(stopped)


async def test_per_title_fails_a_selected_title_below_the_minimum_length(monkeypatch, tmp_path) -> None:
    calls = _fake_rip_disc(monkeypatch)
    tracks = [_track(1, expected=10), _track(2, expected=10, duration=60)]

    done = await _rip_per_title(tmp_path, tracks, set())

    assert [c["title"] for c in calls] == [1]
    failed = {tid: err for tid, ok, err in done if not ok}
    assert "below minlength=120s" in (failed["trk_2"] or "")
