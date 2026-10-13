"""A DVD/BD drive that drops off the USB bus mid-rip (D-133).

The rip stops makemkvcon instead of failing every remaining title, waits for
the drive to come back (often under a new srN), and rips what was left with
one more `mkv all` on the new node, keeping the titles that finished. Only if
the drive stays away does the job finish partial, saying why.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

import arm_ripper.job_controller as jc_module
from arm_common import DiscType, JobStatus
from arm_common.enums import TrackKind, TrackStatus
from arm_common.schemas import JobView, RipStartResponse, TrackView
from arm_ripper.drive_handle import DriveHandle
from arm_ripper.drive_poll import DriveState
from arm_ripper.job_controller import JobController
from arm_ripper.rip import RipResult

_JOB = "job_01M4R7157QDCVQ3MX6M2VK0XX0"


def _track(idx: int, kind: TrackKind = TrackKind.VIDEO_TITLE) -> TrackView:
    return TrackView(
        id=f"trk_{idx}",
        job_id=_JOB,
        kind=kind,
        index=idx,
        source_ref=str(idx),
        status=TrackStatus.QUEUED,
        output_path=None,
        size_bytes=None,
        duration_seconds=1800,
        attempts=0,
        last_error=None,
    )


class _Client:
    def __init__(self) -> None:
        self.patches: list[tuple[str, dict[str, object]]] = []
        self.completed: list[str] = []

    async def update_track(self, track_id: str, **fields: object) -> TrackView:
        self.patches.append((track_id, fields))
        return _track(0)

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

    def statuses(self, track_id: str) -> list[object]:
        return [f.get("status") for tid, f in self.patches if tid == track_id]


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Any]:
    monkeypatch.setattr(jc_module, "RAW_ROOT", tmp_path)
    monkeypatch.setattr(jc_module, "EJECT_GRACE_SECONDS", 0.0)
    monkeypatch.setattr(jc_module, "DEVICE_WATCH_INTERVAL_SECONDS", 0.005)
    monkeypatch.setattr(jc_module, "DEVICE_RETURN_WAIT_SECONDS", 2.0)
    # Whatever node the handle names reads as a seated disc.
    monkeypatch.setattr(jc_module, "read_drive_status", lambda _path: DriveState.DISC_OK)
    ejected: list[str] = []

    async def _eject(self: JobController, device_path: str) -> None:
        ejected.append(device_path)

    monkeypatch.setattr(JobController, "_eject_with_retry", _eject)
    handle = DriveHandle("/dev/sr0")
    client = _Client()
    controller = JobController(client, "drv_x", device_path=handle)  # type: ignore[arg-type]
    return {"handle": handle, "client": client, "controller": controller, "ejected": ejected, "raw": tmp_path / _JOB}


def _script(monkeypatch: pytest.MonkeyPatch, passes: list[Any]) -> list[dict[str, Any]]:
    """Replace rip_all with scripted passes; returns each call's kwargs."""
    calls: list[dict[str, Any]] = []

    async def fake_rip_all(**kw: Any) -> None:
        calls.append(kw)
        await passes[len(calls) - 1](**kw)

    monkeypatch.setattr(jc_module, "rip_all", fake_rip_all)
    return calls


async def _ok(kw: dict[str, Any], track: TrackView, name: str) -> None:
    path = Path(kw["output_dir"]) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * 8)
    await kw["on_track_start"](track)
    await kw["on_track_done"](track, RipResult(ok=True, output_path=path, size_bytes=8))


async def _drive_drops(env: dict[str, Any], kw: dict[str, Any], *, back_on: str | None) -> None:
    """The USB bus drops the drive: the poll loop clears the handle, the
    watcher stops makemkvcon, and the titles it never reached fail."""
    (Path(kw["output_dir"]) / "Disc_t01.mkv").write_bytes(b"partial")
    env["handle"].set(None)
    await asyncio.wait_for(kw["stop"].wait(), timeout=1.0)
    for track in kw["tracks"][1:]:
        await kw["on_track_start"](track)
        await kw["on_track_done"](track, RipResult(ok=False, error="Failed to save title to file"))
    if back_on is not None:
        asyncio.get_running_loop().call_later(0.02, env["handle"].set, back_on)


async def test_a_drive_that_comes_back_on_a_new_node_resumes_the_rest(monkeypatch, env) -> None:
    tracks = [_track(0), _track(1), _track(2)]

    async def first(**kw: Any) -> None:
        await _ok(kw, tracks[0], "Disc_t00.mkv")
        await _drive_drops(env, kw, back_on="/dev/sr1")

    async def resume(**kw: Any) -> None:
        for track in kw["tracks"]:
            if track.id not in kw["skip_track_ids"]:
                await _ok(kw, track, f"Disc_t{track.index:02d}.mkv")

    calls = _script(monkeypatch, [first, resume])
    await env["controller"]._execute_rip(
        job_id=_JOB,
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        rip_start=RipStartResponse(job_id=_JOB, rip_preset_id="rpr", tracks=tracks),
    )

    client: _Client = env["client"]
    # One more `mkv all`, on the new node, into its own folder, skipping the
    # title that finished.
    assert len(calls) == 2
    assert calls[1]["device_path"] == "/dev/sr1"
    assert calls[1]["output_dir"] == env["raw"] / "resume-1"
    assert calls[1]["skip_track_ids"] == {"trk_0"}
    # Nothing failed; each track went in_progress once, then done.
    for tid in ("trk_0", "trk_1", "trk_2"):
        assert client.statuses(tid) == [TrackStatus.IN_PROGRESS, TrackStatus.DONE]
    # The half-written title is gone; the finished one stays.
    assert (env["raw"] / "Disc_t00.mkv").exists()
    assert not (env["raw"] / "Disc_t01.mkv").exists()
    assert client.completed == [_JOB]
    # Ejected once, after the resume, from the node the drive is on now.
    assert env["ejected"] == ["/dev/sr1"]


async def test_a_drive_that_stays_away_finishes_partial_saying_why(monkeypatch, env) -> None:
    monkeypatch.setattr(jc_module, "DEVICE_RETURN_WAIT_SECONDS", 0.05)
    tracks = [_track(0), _track(1), _track(2)]

    async def first(**kw: Any) -> None:
        await _ok(kw, tracks[0], "Disc_t00.mkv")
        await _drive_drops(env, kw, back_on=None)

    calls = _script(monkeypatch, [first])
    await env["controller"]._execute_rip(
        job_id=_JOB,
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        rip_start=RipStartResponse(job_id=_JOB, rip_preset_id="rpr", tracks=tracks),
    )

    client: _Client = env["client"]
    assert len(calls) == 1
    assert client.statuses("trk_0") == [TrackStatus.IN_PROGRESS, TrackStatus.DONE]
    for tid in ("trk_1", "trk_2"):
        assert client.statuses(tid) == [TrackStatus.IN_PROGRESS, TrackStatus.FAILED]
        error = [f["last_error"] for t, f in client.patches if t == tid and "last_error" in f][0]
        assert error == "the drive disconnected mid-rip and did not come back within 0s"
    assert client.completed == [_JOB]


async def test_a_title_failure_with_the_drive_still_there_fails_the_title(monkeypatch, env) -> None:
    tracks = [_track(0), _track(1)]

    async def only(**kw: Any) -> None:
        await _ok(kw, tracks[0], "Disc_t00.mkv")
        await kw["on_track_start"](tracks[1])
        await kw["on_track_done"](tracks[1], RipResult(ok=False, error="read error at sector 123"))

    calls = _script(monkeypatch, [only])
    await env["controller"]._execute_rip(
        job_id=_JOB,
        disc_type=DiscType.DVD,
        device_path="/dev/sr0",
        rip_start=RipStartResponse(job_id=_JOB, rip_preset_id="rpr", tracks=tracks),
    )
    assert len(calls) == 1
    assert env["client"].statuses("trk_1") == [TrackStatus.IN_PROGRESS, TrackStatus.FAILED]
    assert env["ejected"] == ["/dev/sr0"]


async def test_a_title_failure_on_a_node_that_no_longer_answers_is_held_for_the_resume(monkeypatch, env) -> None:
    """makemkvcon can fail titles before the poll loop notices the drive left;
    the node not answering is enough to tell."""

    def gone(_path: str) -> DriveState:
        raise OSError(6, "No such device or address")  # ENXIO

    monkeypatch.setattr(jc_module, "read_drive_status", gone)
    monkeypatch.setattr(jc_module, "DEVICE_RETURN_WAIT_SECONDS", 0.05)
    tracks = [_track(0)]

    async def only(**kw: Any) -> None:
        await kw["on_track_start"](tracks[0])
        await kw["on_track_done"](tracks[0], RipResult(ok=False, error="Failed to save title 0"))

    calls = _script(monkeypatch, [only])
    await env["controller"]._execute_rip(
        job_id=_JOB,
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        rip_start=RipStartResponse(job_id=_JOB, rip_preset_id="rpr", tracks=tracks),
    )
    assert len(calls) == 1
    error = [f["last_error"] for t, f in env["client"].patches if "last_error" in f]
    assert error == ["the drive disconnected mid-rip and did not come back within 0s"]


async def test_cds_and_disc_backups_are_not_resumed(monkeypatch, env) -> None:
    """Only the makemkvcon `mkv all` path resumes; a full-disc backup and a CD
    fail as before when the drive goes."""
    for disc_type, kind in ((DiscType.CD, TrackKind.AUDIO_TRACK), (DiscType.BLURAY, TrackKind.DISC_BACKUP)):
        env["client"].patches.clear()
        tracks = [_track(0, kind)]
        env["handle"].set("/dev/sr0")

        async def only(**kw: Any) -> None:
            assert kw["stop"] is None
            env["handle"].set(None)
            await kw["on_track_start"](tracks[0])
            await kw["on_track_done"](tracks[0], RipResult(ok=False, error="device gone"))

        _script(monkeypatch, [only])
        await env["controller"]._execute_rip(
            job_id=_JOB,
            disc_type=disc_type,
            device_path="/dev/sr0",
            rip_start=RipStartResponse(job_id=_JOB, rip_preset_id="rpr", tracks=tracks),
        )
        assert env["client"].statuses("trk_0") == [TrackStatus.IN_PROGRESS, TrackStatus.FAILED]
