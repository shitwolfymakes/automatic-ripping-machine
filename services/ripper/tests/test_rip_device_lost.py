"""A DVD/BD drive that drops off the USB bus mid-rip.

The rip stops makemkvcon instead of failing every remaining title, waits for
the drive to come back (often under a new srN), and rips what was left with
one more `mkv all` on the new node, keeping the titles that finished. Only if
the drive stays away does the job finish partial, saying why.
"""

from __future__ import annotations

import asyncio
import errno
from pathlib import Path
from typing import Any

import pytest

import arm_ripper.eject as eject_module
import arm_ripper.disc_rip as disc_rip_module
import arm_ripper.raw_dir as raw_dir_module
from arm_common import DiscType, JobStatus
from arm_common.enums import TrackKind, TrackStatus
from arm_common.schemas import JobView, RipStartResponse, TrackView
from arm_ripper.drive_handle import DriveHandle
from arm_ripper.drive_poll import DriveState
from arm_ripper.job_controller import JobController
from arm_ripper.rip import RipResult
from arm_ripper.rip import optical_rip as optical_rip_module
from arm_ripper.rip.makemkv_process import STOPPED_ERROR
from arm_ripper.rip.makemkv_rip import RipDiscResult
from arm_ripper.rip.track_callbacks import TransferStats

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
    monkeypatch.setattr(raw_dir_module, "RAW_ROOT", tmp_path)
    monkeypatch.setattr(disc_rip_module, "EJECT_GRACE_SECONDS", 0.0)
    monkeypatch.setattr(disc_rip_module, "DEVICE_WATCH_INTERVAL_SECONDS", 0.005)
    monkeypatch.setattr(disc_rip_module, "DEVICE_RETURN_WAIT_SECONDS", 2.0)
    # Whatever node the handle names reads as a seated disc.
    monkeypatch.setattr(disc_rip_module, "read_drive_status", lambda _path: DriveState.DISC_OK)
    ejected: list[str] = []

    async def _eject(self, device_path: str) -> None:
        ejected.append(device_path)

    monkeypatch.setattr(eject_module.Ejector, "eject", _eject)
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

    monkeypatch.setattr(disc_rip_module, "rip_all", fake_rip_all)
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
    monkeypatch.setattr(disc_rip_module, "DEVICE_RETURN_WAIT_SECONDS", 0.05)
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

    monkeypatch.setattr(disc_rip_module, "read_drive_status", gone)
    monkeypatch.setattr(disc_rip_module, "DEVICE_RETURN_WAIT_SECONDS", 0.05)
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


async def test_a_title_makemkvcon_moved_on_from_is_resumed_not_kept(monkeypatch, env) -> None:
    """The real dispatcher, with makemkvcon scripted: the drive drops under
    title 1 and makemkvcon moves on to title 2 before the poll loop notices.
    Title 1's cut-short file must not count as done; the resume rips it."""
    tracks = [_track(0), _track(1), _track(2)]
    calls: list[dict[str, Any]] = []

    async def fake_rip_disc(*, output_dir: Path, on_title_done: Any, stop: Any, **kw: Any) -> RipDiscResult:
        calls.append({"output_dir": output_dir, **kw})
        output_dir.mkdir(parents=True, exist_ok=True)
        if len(calls) == 1:
            (output_dir / "Disc_t00.mkv").write_bytes(b"x" * 8)
            (output_dir / "Disc_t01.mkv").write_bytes(b"cut")
            # PRGC:5017 for title 1 finalises title 0 while the drive is there.
            await on_title_done(0)
            # The USB bus drops under title 1; the node stops answering
            # before the poll loop moves the handle.
            monkeypatch.setattr(disc_rip_module, "read_drive_status", _absent)
            # PRGC:5017 for title 2: makemkvcon moved on from the failed title.
            await on_title_done(1)
            assert stop.is_set()
            env["handle"].set(None)
            monkeypatch.setattr(disc_rip_module, "read_drive_status", lambda _path: DriveState.DISC_OK)
            asyncio.get_running_loop().call_later(0.02, env["handle"].set, "/dev/sr1")
            return RipDiscResult(overall_error=STOPPED_ERROR, titles={})
        for pos in range(3):
            (output_dir / f"Disc_t{pos:02d}.mkv").write_bytes(b"y" * 8)
            await on_title_done(pos)
        return RipDiscResult(overall_error=None, titles={})

    monkeypatch.setattr(optical_rip_module, "rip_disc", fake_rip_disc)
    await env["controller"]._execute_rip(
        job_id=_JOB,
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        rip_start=RipStartResponse(job_id=_JOB, rip_preset_id="rpr", tracks=tracks),
    )

    client: _Client = env["client"]
    assert len(calls) == 2
    assert calls[1]["device_path"] == "/dev/sr1"
    for tid in ("trk_0", "trk_1", "trk_2"):
        assert client.statuses(tid) == [TrackStatus.IN_PROGRESS, TrackStatus.DONE]
    outputs = {tid: f["output_path"] for tid, f in client.patches if "output_path" in f}
    assert outputs == {
        "trk_0": str(env["raw"] / "Disc_t00.mkv"),
        "trk_1": str(env["raw"] / "resume-1" / "Disc_t01.mkv"),
        "trk_2": str(env["raw"] / "resume-1" / "Disc_t02.mkv"),
    }
    assert not (env["raw"] / "Disc_t01.mkv").exists()
    assert not (env["raw"] / "resume-1" / "Disc_t00.mkv").exists()


def _absent(_path: str) -> DriveState:
    raise OSError(19, "No such device")  # ENODEV


async def _run_one_pass(
    env: dict[str, Any], monkeypatch: pytest.MonkeyPatch, tracks: list[TrackView], one: Any
) -> None:
    _script(monkeypatch, [one])
    await env["controller"]._execute_rip(
        job_id=_JOB,
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        rip_start=RipStartResponse(job_id=_JOB, rip_preset_id="rpr", tracks=tracks),
    )


async def test_a_finished_title_reports_every_result_field(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, Any]
) -> None:
    """A DONE result carrying a path, size, checksum and duration patches all of them with the status."""
    track = _track(0)

    async def one(**kw: Any) -> None:
        path = Path(kw["output_dir"]) / "Disc_t00.mkv"
        path.write_bytes(b"x")
        await kw["on_track_start"](track)
        result = RipResult(ok=True, output_path=path, size_bytes=5, sha256="abc", duration_seconds=7)
        await kw["on_track_done"](track, result)

    await _run_one_pass(env, monkeypatch, [track], one)
    done = [f for _, f in env["client"].patches if f.get("status") == TrackStatus.DONE]
    assert done == [
        {
            "status": TrackStatus.DONE,
            "output_path": str(env["raw"] / "Disc_t00.mkv"),
            "size_bytes": 5,
            "sha256": "abc",
            "duration_seconds": 7,
        }
    ]


async def test_a_finished_title_without_result_fields_reports_only_done(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, Any]
) -> None:
    """A DONE result with no optional fields patches just the status, after the IN_PROGRESS patch."""
    track = _track(0)

    async def one(**kw: Any) -> None:
        await kw["on_track_start"](track)
        await kw["on_track_done"](track, RipResult(ok=True))

    await _run_one_pass(env, monkeypatch, [track], one)
    assert env["client"].patches == [
        ("trk_0", {"status": TrackStatus.IN_PROGRESS}),
        ("trk_0", {"status": TrackStatus.DONE}),
    ]


async def test_progress_without_a_websocket_only_logs(monkeypatch: pytest.MonkeyPatch, env: dict[str, Any]) -> None:
    """With no WebSocket a progress report is only logged: nothing raises and the rip completes."""
    track = _track(0)

    async def one(**kw: Any) -> None:
        await kw["on_track_start"](track)
        await kw["on_track_progress"](track, 0.5)
        await kw["on_track_done"](track, RipResult(ok=True))

    await _run_one_pass(env, monkeypatch, [track], one)
    assert env["client"].completed == [_JOB]


class _Ws:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    async def publish(self, **kw: Any) -> None:
        self.published.append(kw)


async def test_progress_publishes_the_percentage_and_transfer_stats(
    monkeypatch: pytest.MonkeyPatch, env: dict[str, Any]
) -> None:
    """Progress goes to the job's topic as a percentage, plus byte detail, a rounded rate and phase when given."""
    track = _track(0)
    ws = _Ws()
    env["controller"]._ws = ws

    async def one(**kw: Any) -> None:
        await kw["on_track_start"](track)
        await kw["on_track_progress"](track, 0.25)
        copying = TransferStats(bytes_done=1, bytes_total=4, rate_bps=2.4, phase="copy")
        await kw["on_track_progress"](track, 0.5, copying)
        await kw["on_track_progress"](track, 0.75, TransferStats(bytes_done=2, bytes_total=4, rate_bps=None))
        await kw["on_track_done"](track, RipResult(ok=True))

    await _run_one_pass(env, monkeypatch, [track], one)
    assert ws.published[0]["topic"] == f"ripper.progress.{_JOB}"
    assert ws.published[0]["event_type"] == "ripper.progress"
    assert [p["payload"] for p in ws.published] == [
        {"track_id": "trk_0", "progress_pct": 25.0},
        {
            "track_id": "trk_0",
            "progress_pct": 50.0,
            "bytes_done": 1,
            "bytes_total": 4,
            "rate_bps": 2,
            "phase": "copy",
        },
        {"track_id": "trk_0", "progress_pct": 75.0, "bytes_done": 2, "bytes_total": 4, "rate_bps": None},
    ]


@pytest.mark.parametrize(
    ("disc_type", "kinds", "expected"),
    [
        (DiscType.DVD, [TrackKind.VIDEO_TITLE], True),
        (DiscType.BLURAY, [TrackKind.VIDEO_TITLE], True),
        (DiscType.CD, [TrackKind.VIDEO_TITLE], False),
        (DiscType.DVD, [TrackKind.DISC_BACKUP, TrackKind.DATA_DUMP], False),
        (DiscType.DVD, [TrackKind.VIDEO_TITLE, TrackKind.DATA_DUMP], True),
    ],
)
def test_resumable_needs_a_dvd_or_bd_drive_with_a_title_to_rip(disc_type, kinds, expected) -> None:
    """Only a DVD or BD rip with at least one track that is not a full-disc backup or dump can resume."""
    tracks = [_track(i, kind) for i, kind in enumerate(kinds)]
    assert disc_rip_module._resumable(disc_type, "/dev/sr0", tracks) is expected


def test_resumable_is_false_for_an_iso_source(tmp_path: Path) -> None:
    """An ISO file has no bus to drop off, so its rip never waits to resume."""
    iso = tmp_path / "disc.iso"
    iso.write_bytes(b"x")
    assert disc_rip_module._resumable(DiscType.DVD, str(iso), [_track(0)]) is False


def test_done_fields_carries_every_reported_field_in_order() -> None:
    """A result with every field becomes a DONE patch holding all of them, in a fixed key order."""
    result = RipResult(ok=True, output_path=Path("/x/a.mkv"), size_bytes=5, sha256="abc", duration_seconds=7)
    fields = disc_rip_module._done_fields(result)
    assert list(fields) == ["status", "output_path", "size_bytes", "sha256", "duration_seconds"]
    assert fields == {
        "status": TrackStatus.DONE,
        "output_path": "/x/a.mkv",
        "size_bytes": 5,
        "sha256": "abc",
        "duration_seconds": 7,
    }


def test_done_fields_without_reported_fields_is_only_done() -> None:
    """A result that reported nothing becomes a patch holding just the DONE status."""
    assert disc_rip_module._done_fields(RipResult(ok=True)) == {"status": TrackStatus.DONE}


def test_progress_payload_without_stats_is_the_percentage_only() -> None:
    """A rip with no transfer stats reports just the track id and the rounded percentage."""
    assert disc_rip_module._progress_payload("trk_0", 0.256, None) == {"track_id": "trk_0", "progress_pct": 25.6}


def test_progress_payload_with_stats_adds_bytes_rounded_rate_and_phase() -> None:
    """A copy's stats add its byte counts, the rate rounded to whole bytes, and the phase, in a fixed order."""
    stats = {"bytes_done": 1, "bytes_total": 4, "rate_bps": 2.6, "phase": "copy"}
    payload = disc_rip_module._progress_payload("trk_0", 0.5, stats)  # type: ignore[arg-type]
    assert list(payload) == ["track_id", "progress_pct", "bytes_done", "bytes_total", "rate_bps", "phase"]
    assert payload["rate_bps"] == 3
    assert payload["phase"] == "copy"


def test_progress_payload_with_no_rate_or_phase_leaves_the_rate_none_and_omits_phase() -> None:
    """Stats with an unknown rate and no phase give a None rate and no phase key."""
    stats = {"bytes_done": 2, "bytes_total": 4, "rate_bps": None}
    payload = disc_rip_module._progress_payload("trk_0", 0.75, stats)  # type: ignore[arg-type]
    assert payload == {
        "track_id": "trk_0",
        "progress_pct": 75.0,
        "bytes_done": 2,
        "bytes_total": 4,
        "rate_bps": None,
    }


def _disc_rip(controller: JobController) -> disc_rip_module.DiscRip:
    """A disc rip on `/dev/sr0` built from `controller`'s parts."""
    return disc_rip_module.DiscRip(
        backend=controller._backend,
        ws=controller._ws,
        ejector=controller._ejector,
        device=controller._device,
        default_min_length_seconds=controller._default_min_length_seconds,
        output_dir=raw_dir_module.RAW_ROOT / _JOB,
        job_id=_JOB,
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        rip_start=RipStartResponse(job_id=_JOB, rip_preset_id="rpr", tracks=[]),
    )


def _drive_gone_controller(monkeypatch: pytest.MonkeyPatch, handle: DriveHandle, outcome: BaseException | None):
    """A controller on `handle` whose drive-status read records its calls and raises `outcome` if given."""
    calls: list[str] = []

    def fake_read(path: str) -> None:
        calls.append(path)
        if outcome is not None:
            raise outcome

    monkeypatch.setattr(disc_rip_module, "read_drive_status", fake_read)
    return JobController(_Client(), "drv_x", device_path=handle), calls  # type: ignore[arg-type]


@pytest.mark.parametrize("new_path", ["/dev/sr1", None])
def test_drive_gone_is_true_without_a_read_when_the_handle_moved_or_emptied(
    monkeypatch: pytest.MonkeyPatch, new_path: str | None
) -> None:
    """A handle naming another node, or none, means the drive left; the node is not read."""
    handle = DriveHandle("/dev/sr0")
    controller, calls = _drive_gone_controller(monkeypatch, handle, None)
    handle.set(new_path)
    assert _disc_rip(controller)._drive_gone("/dev/sr0") is True
    assert calls == []


@pytest.mark.parametrize("code", [errno.ENOENT, errno.ENXIO, errno.ENODEV])
def test_drive_gone_is_true_when_the_node_reads_as_absent(monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    """An OSError with an absent errno on the still-current node means the drive is gone."""
    controller, calls = _drive_gone_controller(monkeypatch, DriveHandle("/dev/sr0"), OSError(code, "absent"))
    assert _disc_rip(controller)._drive_gone("/dev/sr0") is True
    assert calls == ["/dev/sr0"]


@pytest.mark.parametrize("code", [errno.EIO, errno.EACCES])
def test_drive_gone_is_false_when_the_read_fails_for_another_reason(monkeypatch: pytest.MonkeyPatch, code: int) -> None:
    """An OSError with a non-absent errno on the current node does not count as the drive leaving."""
    controller, calls = _drive_gone_controller(monkeypatch, DriveHandle("/dev/sr0"), OSError(code, "other"))
    assert _disc_rip(controller)._drive_gone("/dev/sr0") is False
    assert calls == ["/dev/sr0"]


def test_drive_gone_is_false_when_the_current_node_reads_fine(monkeypatch: pytest.MonkeyPatch) -> None:
    """A readable drive on the node the rip started on has not gone."""
    controller, calls = _drive_gone_controller(monkeypatch, DriveHandle("/dev/sr0"), None)
    assert _disc_rip(controller)._drive_gone("/dev/sr0") is False
    assert calls == ["/dev/sr0"]


async def test_await_drive_return_gives_up_without_a_read_when_the_handle_stays_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty handle skips the drive read; once the deadline passes the wait returns None."""
    handle = DriveHandle("/dev/sr0")
    controller, calls = _drive_gone_controller(monkeypatch, handle, None)
    handle.set(None)
    monkeypatch.setattr(disc_rip_module, "DEVICE_RETURN_WAIT_SECONDS", 0.0)
    assert await _disc_rip(controller)._await_drive_return() is None
    assert calls == []


async def test_await_drive_return_returns_the_node_the_handle_fills_in_once_it_reads_a_disc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty handle is waited out; the node set while sleeping is read and returned on DISC_OK."""
    handle = DriveHandle("/dev/sr0")
    handle.set(None)
    reads: list[str] = []

    def fake_read(path: str) -> DriveState:
        reads.append(path)
        return DriveState.DISC_OK

    async def fake_sleep(_seconds: float) -> None:
        handle.set("/dev/sr1")

    monkeypatch.setattr(disc_rip_module, "read_drive_status", fake_read)
    monkeypatch.setattr(disc_rip_module, "DEVICE_RETURN_WAIT_SECONDS", 1000.0)
    monkeypatch.setattr(disc_rip_module, "DEVICE_WATCH_INTERVAL_SECONDS", 0.001)
    monkeypatch.setattr(disc_rip_module.asyncio, "sleep", fake_sleep)
    controller = JobController(_Client(), "drv_x", device_path=handle)  # type: ignore[arg-type]
    assert await _disc_rip(controller)._await_drive_return() == "/dev/sr1"
    assert reads == ["/dev/sr1"]


async def test_await_drive_return_keeps_waiting_while_the_node_reads_a_state_other_than_disc_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A readable node that is not DISC_OK is not returned; the wait ends None at the deadline."""
    reads: list[str] = []

    def fake_read(path: str) -> DriveState:
        reads.append(path)
        return DriveState.NOT_READY

    monkeypatch.setattr(disc_rip_module, "read_drive_status", fake_read)
    monkeypatch.setattr(disc_rip_module, "DEVICE_RETURN_WAIT_SECONDS", 0.0)
    controller = JobController(_Client(), "drv_x", device_path=DriveHandle("/dev/sr0"))  # type: ignore[arg-type]
    assert await _disc_rip(controller)._await_drive_return() is None
    assert reads == ["/dev/sr0"]
