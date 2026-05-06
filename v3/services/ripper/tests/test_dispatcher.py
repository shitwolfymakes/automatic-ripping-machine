"""Dispatcher tests.

Two surfaces:

(1) `probe_drive_media` — the heartbeat/manual-trigger pre-check probe.
    Pure ioctl, no read-verify — the per-title rip loop that needed
    verify-read no longer exists.

(2) `rip_all` for DVD/BD discs — the single-invocation v2-style flow.
    Faked `rip_disc` simulates per-title outcomes (a TitleStart hook
    fires, then a per-title RipResult comes back); the dispatcher
    fans the lifecycle hooks out to the right TrackView and handles
    skipped-by-minlength + disc-level failures.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path
from typing import Any


import arm_ripper.drive_status as drive_status_module
import arm_ripper.rip.dispatcher as dispatcher_module
from arm_common import DiscType, DriveMediaStatus
from arm_common.enums import TrackKind, TrackStatus
from arm_common.schemas import TrackView

from arm_ripper.drive_status import probe_drive_media
from arm_ripper.rip.dispatcher import rip_all
from arm_ripper.rip.makemkv_rip import RipDiscResult, RipResult


def _track(idx: int, source_ref: str | None = None, duration_seconds: int | None = 1800) -> TrackView:
    """Default duration is 30 min so the dispatcher's eligibility
    filter (`duration_seconds >= min_length_seconds`) treats it as
    rippable. Pass an explicit duration to test below-minlength
    skipping."""
    return TrackView(
        id=f"trk_{idx}",
        job_id="job_test",
        kind=TrackKind.VIDEO_TITLE,
        index=idx,
        source_ref=str(idx) if source_ref is None else source_ref,
        status=TrackStatus.QUEUED,
        output_path=None,
        size_bytes=None,
        duration_seconds=duration_seconds,
        attempts=0,
        last_error=None,
    )


# --- probe_drive_media -------------------------------------------------------


def _patch_open_close_ioctl(monkeypatch, *, open_result, ioctl_result):
    """Stub os.open/os.close + fcntl.ioctl together so a single test
    can describe one probe's behaviour. *_result accepts a value or
    an Exception."""

    def fake_open(path: str, flags: int) -> int:
        if isinstance(open_result, Exception):
            raise open_result
        return open_result

    def fake_close(fd: int) -> None:
        return None

    def fake_ioctl(fd: int, request: int, arg: int) -> int:
        if isinstance(ioctl_result, Exception):
            raise ioctl_result
        return ioctl_result

    monkeypatch.setattr(os, "open", fake_open)
    monkeypatch.setattr(os, "close", fake_close)
    monkeypatch.setattr(drive_status_module.fcntl, "ioctl", fake_ioctl)


def test_probe_returns_loaded_when_disc_ok(monkeypatch):
    _patch_open_close_ioctl(monkeypatch, open_result=11, ioctl_result=4)  # CDS_DISC_OK
    status, reason = probe_drive_media("/dev/sr0")
    assert status is DriveMediaStatus.LOADED
    assert "loaded" in reason


def test_probe_returns_unavailable_when_open_fails(monkeypatch):
    _patch_open_close_ioctl(
        monkeypatch,
        open_result=OSError(errno.ENODEV, "No such device"),
        ioctl_result=4,
    )
    status, reason = probe_drive_media("/dev/sr0")
    assert status is DriveMediaStatus.UNAVAILABLE
    assert "errno=19" in reason


def test_probe_returns_not_ready_when_disc_becoming_ready(monkeypatch):
    _patch_open_close_ioctl(monkeypatch, open_result=11, ioctl_result=3)  # CDS_DRIVE_NOT_READY
    status, _ = probe_drive_media("/dev/sr0")
    assert status is DriveMediaStatus.NOT_READY


def test_probe_returns_tray_open(monkeypatch):
    _patch_open_close_ioctl(monkeypatch, open_result=11, ioctl_result=2)  # CDS_TRAY_OPEN
    status, _ = probe_drive_media("/dev/sr0")
    assert status is DriveMediaStatus.TRAY_OPEN


def test_probe_returns_no_disc(monkeypatch):
    _patch_open_close_ioctl(monkeypatch, open_result=11, ioctl_result=1)  # CDS_NO_DISC
    status, _ = probe_drive_media("/dev/sr0")
    assert status is DriveMediaStatus.NO_DISC


def test_probe_returns_unknown_when_ioctl_unsupported(monkeypatch):
    _patch_open_close_ioctl(
        monkeypatch,
        open_result=11,
        ioctl_result=OSError(errno.ENOTTY, "Inappropriate ioctl for device"),
    )
    status, reason = probe_drive_media("/dev/sr0")
    assert status is DriveMediaStatus.UNKNOWN
    assert "ioctl unsupported" in reason


def test_probe_does_not_call_read(monkeypatch):
    """Probe is ioctl-only since the single-invocation rip removed
    the need for read-verify. Any os.read attempt is a regression."""

    def boom(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("os.read must not be called by the probe")

    monkeypatch.setattr(os, "open", lambda path, flags: 11)
    monkeypatch.setattr(os, "close", lambda fd: None)
    monkeypatch.setattr(os, "read", boom)
    monkeypatch.setattr(drive_status_module.fcntl, "ioctl", lambda fd, req, arg: 4)

    status, _ = probe_drive_media("/dev/sr0")
    assert status is DriveMediaStatus.LOADED


# --- rip_all (DVD/BD single-invocation) --------------------------------------


def _stub_rip_disc(
    monkeypatch,
    fake_result: RipDiscResult,
    *,
    captured: dict[str, Any] | None = None,
    fire_per_title_start: bool = True,
):
    """Replace dispatcher's rip_disc with a fake that captures kwargs
    and returns the canned RipDiscResult. Optionally invokes
    on_title_start for each title in `fake_result.titles` so the
    dispatcher's lifecycle-hook plumbing is exercised.

    `fire_per_title_start=False` simulates MakeMKV's `mkv all` mode,
    where no per-title PRGT fires — the dispatcher must still drive
    the on_track_start → on_track_done sequence post-rip for every
    track the user selected."""

    async def fake_rip_disc(
        *,
        device_path: str,
        output_dir: Path,
        minlength_seconds: int,
        eligible_source_indexes: list[int] | None = None,
        on_title_start: Any | None = None,
        on_title_progress: Any | None = None,
    ) -> RipDiscResult:
        if captured is not None:
            captured["device_path"] = device_path
            captured["output_dir"] = output_dir
            captured["minlength_seconds"] = minlength_seconds
            captured["eligible_source_indexes"] = eligible_source_indexes
        if fire_per_title_start and on_title_start is not None:
            for idx in fake_result.titles:
                await on_title_start(idx)
        if on_title_progress is not None:
            for idx in fake_result.titles:
                await on_title_progress(idx, 0.5)
                await on_title_progress(idx, 1.0)
        return fake_result

    monkeypatch.setattr(dispatcher_module, "rip_disc", fake_rip_disc)


async def test_rip_all_dvd_single_invocation_per_disc(monkeypatch, tmp_path):
    """The DVD/BD branch invokes rip_disc exactly once for the whole
    disc. The lifecycle hooks fire per-title from the stream callbacks."""
    fake_result = RipDiscResult(
        overall_error=None,
        titles={
            0: RipResult(ok=True, output_path=tmp_path / "title_t00.mkv", size_bytes=100, sha256="a"),
            1: RipResult(ok=True, output_path=tmp_path / "title_t01.mkv", size_bytes=200, sha256="b"),
            2: RipResult(ok=True, output_path=tmp_path / "title_t02.mkv", size_bytes=300, sha256="c"),
        },
    )
    captured: dict[str, Any] = {}
    _stub_rip_disc(monkeypatch, fake_result, captured=captured)

    started: list[str] = []
    done: list[tuple[str, bool, str | None]] = []
    progress: list[tuple[str, float]] = []

    async def on_start(track: TrackView) -> None:
        started.append(track.id)

    async def on_done(track: TrackView, result: RipResult) -> None:
        done.append((track.id, result.ok, result.error))

    async def on_progress(track: TrackView, fraction: float) -> None:
        progress.append((track.id, fraction))

    tracks = [_track(0), _track(1), _track(2)]
    await rip_all(
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        tracks=tracks,
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
        on_track_progress=on_progress,
        min_length_seconds=600,
    )

    assert captured["device_path"] == "/dev/sr0"
    assert captured["output_dir"] == tmp_path
    assert captured["minlength_seconds"] == 600
    assert started == ["trk_0", "trk_1", "trk_2"]
    assert [t for t, ok, _ in done] == ["trk_0", "trk_1", "trk_2"]
    assert all(ok for _, ok, _ in done)
    # Two progress samples per track (0.5 then 1.0) routed through the lookup.
    assert len(progress) == 6


async def test_rip_all_marks_skipped_titles_failed(monkeypatch, tmp_path):
    """A track the user selected whose duration is below `--minlength`
    never reaches MakeMKV's output. The dispatcher must mark it FAILED
    with a clear reason rather than silently dropping it."""
    fake_result = RipDiscResult(
        overall_error=None,
        titles={
            0: RipResult(ok=True, output_path=tmp_path / "vol_t00.mkv", size_bytes=100, sha256="a"),
        },
    )
    _stub_rip_disc(monkeypatch, fake_result)

    done: list[tuple[str, bool, str | None]] = []

    async def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def on_done(track: TrackView, result: RipResult) -> None:
        done.append((track.id, result.ok, result.error))

    # Track 1 is 60s — below the 600s minlength, so the dispatcher
    # filters it from the eligible list and reports it FAILED.
    short_track = _track(1, duration_seconds=60)
    await rip_all(
        disc_type=DiscType.DVD,
        device_path="/dev/sr0",
        tracks=[_track(0), short_track],
        output_dir=tmp_path,
        on_track_start=noop,
        on_track_done=on_done,
        min_length_seconds=600,
    )

    assert done[0] == ("trk_0", True, None)
    failed = [d for d in done if d[0] == "trk_1"][0]
    assert failed[1] is False
    assert "below minlength=600s" in failed[2]


async def test_rip_all_passes_eligible_source_indexes_to_rip_disc(monkeypatch, tmp_path):
    """The dispatcher must compute the eligible-source-indexes list
    (those whose duration meets minlength) and pass it to rip_disc
    so attribution can pair output files positionally to source
    title indexes."""
    fake_result = RipDiscResult(overall_error=None, titles={})
    captured: dict[str, Any] = {}
    _stub_rip_disc(monkeypatch, fake_result, captured=captured)

    async def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    tracks = [
        _track(0, duration_seconds=6708),
        _track(1, duration_seconds=314),  # below 600 → skipped
        _track(2, duration_seconds=852),
        _track(3, duration_seconds=315),  # below 600 → skipped
        _track(4, duration_seconds=1800),
    ]
    await rip_all(
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        tracks=tracks,
        output_dir=tmp_path,
        on_track_start=noop,
        on_track_done=noop,
        min_length_seconds=600,
    )

    assert captured["eligible_source_indexes"] == [0, 2, 4]


async def test_rip_all_propagates_disc_level_error(monkeypatch, tmp_path):
    """rip_disc reporting overall_error → every selected track FAILED
    with that error string."""
    fake_result = RipDiscResult(
        overall_error="makemkvcon failed: SCSI error",
        titles={},
    )
    _stub_rip_disc(monkeypatch, fake_result)

    done: list[tuple[str, bool, str | None]] = []

    async def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def on_done(track: TrackView, result: RipResult) -> None:
        done.append((track.id, result.ok, result.error))

    await rip_all(
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        tracks=[_track(0), _track(1)],
        output_dir=tmp_path,
        on_track_start=noop,
        on_track_done=on_done,
        min_length_seconds=600,
    )

    assert all(d[1] is False for d in done)
    assert all("SCSI error" in (d[2] or "") for d in done)


async def test_rip_all_invalid_source_ref_fails_fast(monkeypatch, tmp_path):
    """A track whose source_ref isn't an int never reaches makemkvcon."""
    fake_result = RipDiscResult(overall_error=None, titles={})
    _stub_rip_disc(monkeypatch, fake_result)

    done: list[tuple[str, bool, str | None]] = []

    async def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def on_done(track: TrackView, result: RipResult) -> None:
        done.append((track.id, result.ok, result.error))

    bad = _track(5, source_ref="not-an-int")
    await rip_all(
        disc_type=DiscType.DVD,
        device_path="/dev/sr0",
        tracks=[bad],
        output_dir=tmp_path,
        on_track_start=noop,
        on_track_done=on_done,
    )

    assert done == [("trk_5", False, "invalid source_ref: 'not-an-int'")]


async def test_rip_all_synthesises_start_when_prgt_misses(monkeypatch, tmp_path):
    """In `mkv all` mode MakeMKV emits a single overall "Saving all
    titles to MKV files" PRGT instead of per-title milestones, so
    `on_title_start` never fires from the stream. The dispatcher must
    synthesise `on_track_start` before each `on_track_done` so the
    backend's QUEUED → IN_PROGRESS → DONE state machine sees a legal
    transition. This is the regression that broke job_01KQX2EE...:
    the post-rip PATCH `done` got 409'd and aborted the pipeline."""
    fake_result = RipDiscResult(
        overall_error=None,
        titles={
            0: RipResult(ok=True, output_path=tmp_path / "title_t00.mkv", size_bytes=100, sha256="a"),
            2: RipResult(ok=True, output_path=tmp_path / "title_t02.mkv", size_bytes=200, sha256="b"),
        },
    )
    _stub_rip_disc(monkeypatch, fake_result, fire_per_title_start=False)

    events: list[tuple[str, str]] = []

    async def on_start(track: TrackView) -> None:
        events.append(("start", track.id))

    async def on_done(track: TrackView, result: RipResult) -> None:
        events.append(("done", track.id))

    # 8 selected tracks, only indexes 0 and 2 ripped (rest skipped by minlength).
    tracks = [_track(i) for i in range(8)]
    await rip_all(
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        tracks=tracks,
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
        min_length_seconds=600,
    )

    # Every track must see a `start` followed by a `done` in that order.
    by_track: dict[str, list[str]] = {}
    for kind, tid in events:
        by_track.setdefault(tid, []).append(kind)
    assert len(by_track) == 8
    for tid, seq in by_track.items():
        assert seq == ["start", "done"], f"track {tid} had bad lifecycle: {seq}"


async def test_rip_all_disc_error_path_drives_full_lifecycle(monkeypatch, tmp_path):
    """When rip_disc reports an overall_error every selected track must
    be FAILED — and each must transit IN_PROGRESS first per the
    backend state machine."""
    fake_result = RipDiscResult(overall_error="makemkvcon failed: SCSI error", titles={})
    _stub_rip_disc(monkeypatch, fake_result, fire_per_title_start=False)

    events: list[tuple[str, str]] = []

    async def on_start(track: TrackView) -> None:
        events.append(("start", track.id))

    async def on_done(track: TrackView, result: RipResult) -> None:
        events.append(("done", track.id))

    tracks = [_track(0), _track(1), _track(2)]
    await rip_all(
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        tracks=tracks,
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
        min_length_seconds=600,
    )

    by_track: dict[str, list[str]] = {}
    for kind, tid in events:
        by_track.setdefault(tid, []).append(kind)
    for tid in ("trk_0", "trk_1", "trk_2"):
        assert by_track[tid] == ["start", "done"]


async def test_rip_all_does_not_double_start_when_prgt_fires(monkeypatch, tmp_path):
    """If the per-title PRGT *did* fire and called on_track_start, the
    post-rip ensure-started shim must not call it again. Prevents a
    409 on the second IN_PROGRESS PATCH."""
    fake_result = RipDiscResult(
        overall_error=None,
        titles={0: RipResult(ok=True, output_path=tmp_path / "t.mkv", size_bytes=10, sha256="a")},
    )
    _stub_rip_disc(monkeypatch, fake_result, fire_per_title_start=True)

    starts = 0

    async def on_start(track: TrackView) -> None:
        nonlocal starts
        starts += 1

    async def on_done(track: TrackView, result: RipResult) -> None:
        pass

    await rip_all(
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        tracks=[_track(0)],
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
        min_length_seconds=600,
    )

    assert starts == 1


async def test_rip_all_carries_duration_from_track_view(monkeypatch, tmp_path):
    """rip_disc has no scan-side duration info; the dispatcher must
    forward TrackView.duration_seconds onto the success result so the
    backend track row gets populated."""
    fake_result = RipDiscResult(
        overall_error=None,
        titles={
            0: RipResult(ok=True, output_path=tmp_path / "t.mkv", size_bytes=100, sha256="a"),
        },
    )
    _stub_rip_disc(monkeypatch, fake_result)

    seen_duration: list[int | None] = []

    async def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def on_done(track: TrackView, result: RipResult) -> None:
        seen_duration.append(result.duration_seconds)

    track = TrackView(
        id="trk_0",
        job_id="j",
        kind=TrackKind.VIDEO_TITLE,
        index=0,
        source_ref="0",
        status=TrackStatus.QUEUED,
        output_path=None,
        size_bytes=None,
        duration_seconds=7321,
        attempts=0,
        last_error=None,
    )
    await rip_all(
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        tracks=[track],
        output_dir=tmp_path,
        on_track_start=noop,
        on_track_done=on_done,
    )

    assert seen_duration == [7321]


async def test_rip_all_falls_back_to_expected_duration(monkeypatch, tmp_path):
    """At rip-start, `track.duration_seconds` is null (it's the post-rip
    actual). `track.expected_duration_seconds` carries the scan-time
    estimate. The dispatcher must fall back to the latter so the
    backend's PATCH-DONE row gets a non-null duration. (This was the
    ripped-but-null bug surfaced by job_01KQXA9JM3RX2SV8SB7S4CP6NX.)"""
    fake_result = RipDiscResult(
        overall_error=None,
        titles={
            0: RipResult(ok=True, output_path=tmp_path / "t.mkv", size_bytes=100, sha256="a"),
        },
    )
    _stub_rip_disc(monkeypatch, fake_result)

    seen_duration: list[int | None] = []

    async def noop(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def on_done(track: TrackView, result: RipResult) -> None:
        seen_duration.append(result.duration_seconds)

    track = TrackView(
        id="trk_0",
        job_id="j",
        kind=TrackKind.VIDEO_TITLE,
        index=0,
        source_ref="0",
        status=TrackStatus.QUEUED,
        output_path=None,
        size_bytes=None,
        duration_seconds=None,
        expected_duration_seconds=6708,
        attempts=0,
        last_error=None,
    )
    await rip_all(
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        tracks=[track],
        output_dir=tmp_path,
        on_track_start=noop,
        on_track_done=on_done,
    )

    assert seen_duration == [6708]
