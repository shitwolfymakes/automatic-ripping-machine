"""Dispatcher tests.

Two surfaces:

(1) `probe_drive_media` — the heartbeat/manual-trigger pre-check probe.
    Pure ioctl, no read-verify.

(2) `rip_all` for DVD/BD discs — the single-invocation flow.
    Faked `rip_disc` simulates per-title outcomes (a TitleStart hook
    fires, then a per-title RipResult comes back); the dispatcher
    fans the lifecycle hooks out to the right TrackView and handles
    skipped-by-minlength + disc-level failures.
"""

from __future__ import annotations

import asyncio
import errno
import logging
import os
from pathlib import Path
from typing import Any

import pytest

import arm_ripper.drive_status as drive_status_module
import arm_ripper.rip.dispatcher as dispatcher_module
import arm_ripper.rip.optical_rip as optical_rip_module
from arm_common import DiscType, DriveMediaStatus
from arm_common.enums import TrackKind, TrackStatus
from arm_common.schemas import TrackView

from arm_ripper.drive_status import probe_drive_media
from arm_ripper.rip.dispatcher import _effective_disc_type, rip_all
from arm_ripper.rip.makemkv_rip import RipDiscResult
from arm_ripper.rip.optical_rip import (
    _eligible_source_indexes,
    _finished_file,
    _first_eligible_track,
    _index_tracks,
    _no_output_error,
)
from arm_ripper.rip.result import RipResult


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


def test_probe_returns_detached_when_open_says_the_drive_is_gone(monkeypatch):
    """ENODEV/ENOENT/ENXIO mean the drive is unplugged, not misconfigured —
    the heartbeat must carry DETACHED so the backend can derive OFFLINE."""
    _patch_open_close_ioctl(
        monkeypatch,
        open_result=OSError(errno.ENODEV, "No such device"),
        ioctl_result=4,
    )
    status, reason = probe_drive_media("/dev/sr0")
    assert status is DriveMediaStatus.DETACHED
    assert "errno=19" in reason


def test_probe_returns_detached_when_the_node_has_no_hardware_behind_it(monkeypatch):
    _patch_open_close_ioctl(
        monkeypatch,
        open_result=OSError(errno.ENXIO, "No such device or address"),
        ioctl_result=4,
    )
    status, _ = probe_drive_media("/dev/sr0")
    assert status is DriveMediaStatus.DETACHED


def test_probe_returns_unavailable_when_open_is_denied(monkeypatch):
    """EACCES: the node exists but the cgroup rule / CDROM_GID is wrong.
    That is an operator misconfiguration, not a detached drive."""
    _patch_open_close_ioctl(
        monkeypatch,
        open_result=OSError(errno.EACCES, "Permission denied"),
        ioctl_result=4,
    )
    status, reason = probe_drive_media("/dev/sr0")
    assert status is DriveMediaStatus.UNAVAILABLE
    assert "errno=13" in reason


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
    """Probe is ioctl-only: the single-invocation rip needs no read-verify.
    Any os.read attempt is a regression."""

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
    fire_per_title_done: bool = False,
    fire_disc_progress: list[float] | None = None,
):
    """Replace dispatcher's rip_disc with a fake that captures kwargs
    and returns the canned RipDiscResult. Optionally invokes
    on_title_start for each title in `fake_result.titles` so the
    dispatcher's lifecycle-hook plumbing is exercised.

    `fire_per_title_start=False` simulates MakeMKV's `mkv all` mode,
    where no per-title PRGT fires — the dispatcher must still drive
    the on_track_start → on_track_done sequence post-rip for every
    track the user selected.

    `fire_per_title_done=True` invokes on_title_done for each title in
    `fake_result.titles` — simulates the streamer's PRGC:5017
    transitions that finalise each title mid-rip. With this on, the
    dispatcher PATCHes DONE per-title via the live path and skips
    those tracks in its post-rip attribution loop.

    `fire_disc_progress=[0.1, 0.5, ...]` invokes on_disc_progress with
    each fraction in order, simulating the disc-overall PRGV stream
    that's the only progress signal in `mkv all` mode."""

    async def fake_rip_disc(
        *,
        device_path: str,
        output_dir: Path,
        minlength_seconds: int,
        eligible_source_indexes: list[int] | None = None,
        on_title_start: Any | None = None,
        on_title_progress: Any | None = None,
        on_disc_progress: Any | None = None,
        on_title_done: Any | None = None,
        hash_outputs: bool = True,
        stop: Any | None = None,
    ) -> RipDiscResult:
        if captured is not None:
            captured["hash_outputs"] = hash_outputs
            captured["device_path"] = device_path
            captured["output_dir"] = output_dir
            captured["minlength_seconds"] = minlength_seconds
            captured["eligible_source_indexes"] = eligible_source_indexes
        if fire_per_title_start and on_title_start is not None:
            for idx in fake_result.titles:
                await on_title_start(idx)
        # Per-title progress can only fire when the streamer has
        # established `current_title` from a "Saving title #N" PRGT —
        # i.e. the same condition that gates `fire_per_title_start`.
        # `mkv all` mode (fire_per_title_start=False) emits no
        # per-title PRGT and therefore no per-title progress; skipping
        # it here keeps the fake's behaviour aligned with the real
        # streamer in [makemkv_stream.py].
        if fire_per_title_start and on_title_progress is not None:
            for idx in fake_result.titles:
                await on_title_progress(idx, 0.5)
                await on_title_progress(idx, 1.0)
        if fire_disc_progress is not None and on_disc_progress is not None:
            for frac in fire_disc_progress:
                await on_disc_progress(frac)
        if fire_per_title_done and on_title_done is not None:
            for idx in fake_result.titles:
                await on_title_done(idx)
        return fake_result

    monkeypatch.setattr(optical_rip_module, "rip_disc", fake_rip_disc)


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

    async def on_progress(track: TrackView, fraction: float, stats: Any = None) -> None:
        if stats is not None and stats.get("phase") == "verifying":
            return  # the post-rip hash pass; covered by its own tests
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

    assert [d for d in done if d[0] == "trk_0"] == [("trk_0", True, None)]
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


async def test_rip_all_disc_progress_attributes_to_first_eligible_track(monkeypatch, tmp_path):
    """`mkv all` emits no per-title PRGT, so `on_title_progress` never
    fires from the stream. The dispatcher must surface PRGV's
    `total/max` (disc-overall) channel via `on_disc_progress`,
    attributed to the first eligible track. The UI's rips store keys
    live progress by job_id and renders one bar per disc, so the
    track_id chosen is purely a wire-format detail — what matters is
    that the bar advances 0 → 100 % across the rip."""
    fake_result = RipDiscResult(
        overall_error=None,
        titles={
            0: RipResult(ok=True, output_path=tmp_path / "title_t00.mkv", size_bytes=100, sha256="a"),
            2: RipResult(ok=True, output_path=tmp_path / "title_t01.mkv", size_bytes=200, sha256="b"),
        },
    )
    _stub_rip_disc(
        monkeypatch,
        fake_result,
        fire_per_title_start=False,
        fire_disc_progress=[0.05, 0.4, 0.7, 1.0],
    )

    progress: list[tuple[str, float]] = []

    async def on_progress(track: TrackView, fraction: float, stats: Any = None) -> None:
        if stats is not None and stats.get("phase") == "verifying":
            return  # the post-rip hash pass; covered by its own tests
        progress.append((track.id, fraction))

    async def noop_start(_track: TrackView) -> None:
        return None

    async def noop_done(_track: TrackView, _result: RipResult) -> None:
        return None

    # 4 selected tracks; first eligible is track index 0 (`trk_0`).
    tracks = [_track(i) for i in range(4)]
    await rip_all(
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        tracks=tracks,
        output_dir=tmp_path,
        on_track_start=noop_start,
        on_track_done=noop_done,
        on_track_progress=on_progress,
        min_length_seconds=600,
    )

    # Every disc-progress sample lands on the first eligible track,
    # in order, with the supplied fractions intact.
    assert progress == [("trk_0", 0.05), ("trk_0", 0.4), ("trk_0", 0.7), ("trk_0", 1.0)]


async def test_rip_all_disc_progress_no_op_when_no_progress_callback(monkeypatch, tmp_path):
    """If the caller doesn't wire `on_track_progress`, the dispatcher's
    disc-progress fallback must be a silent no-op rather than crashing
    on a None call."""
    fake_result = RipDiscResult(
        overall_error=None,
        titles={
            0: RipResult(ok=True, output_path=tmp_path / "title_t00.mkv", size_bytes=100, sha256="a"),
        },
    )
    _stub_rip_disc(
        monkeypatch,
        fake_result,
        fire_per_title_start=False,
        fire_disc_progress=[0.5, 1.0],
    )

    async def noop_start(_track: TrackView) -> None:
        return None

    async def noop_done(_track: TrackView, _result: RipResult) -> None:
        return None

    await rip_all(
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        tracks=[_track(0)],
        output_dir=tmp_path,
        on_track_start=noop_start,
        on_track_done=noop_done,
        on_track_progress=None,
        min_length_seconds=600,
    )
    # No assertions on progress because no callback was wired; reaching
    # here without raising is the success criterion.


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


async def test_rip_all_live_per_title_done_patches_via_streamer_callback(monkeypatch, tmp_path):
    """When the streamer fires on_title_done mid-rip (the new path),
    the dispatcher's `_on_title_done` stats the file and PATCHes the
    track DONE before rip_disc returns. The post-rip attribution loop
    must then skip those tracks rather than emitting a duplicate
    on_track_done."""
    # Files MakeMKV would have produced — positional `_tNN.mkv` suffix
    # matches eligible_source_indexes[N].
    (tmp_path / "Disc_t00.mkv").write_bytes(b"x" * 100)
    (tmp_path / "Disc_t01.mkv").write_bytes(b"y" * 200)

    fake_result = RipDiscResult(overall_error=None, titles={})
    _stub_rip_disc(monkeypatch, fake_result, fire_per_title_start=True, fire_per_title_done=True)

    events: list[tuple[str, str, int | None]] = []

    async def on_start(track: TrackView) -> None:
        events.append(("start", track.id, None))

    async def on_done(track: TrackView, result: RipResult) -> None:
        events.append(("done", track.id, result.size_bytes))

    # The fake fires on_title_done with the source idx (which our stub
    # passes from `fake_result.titles` keys). Seed those so the fake
    # has something to iterate.
    fake_result.titles[0] = RipResult(ok=True, output_path=None, size_bytes=None)
    fake_result.titles[1] = RipResult(ok=True, output_path=None, size_bytes=None)

    await rip_all(
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        tracks=[_track(0), _track(1)],
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
        min_length_seconds=600,
    )

    # Each track exactly one start + one done — no duplicate from the
    # post-rip attribution loop. Sizes come from the on-disk file
    # (stat'd by `_on_title_done`), not from `fake_result.titles`.
    by_track: dict[str, list[tuple[str, int | None]]] = {}
    for kind, tid, size in events:
        by_track.setdefault(tid, []).append((kind, size))
    assert by_track["trk_0"] == [("start", None), ("done", 100)]
    assert by_track["trk_1"] == [("start", None), ("done", 200)]


async def test_rip_all_disc_error_keeps_already_done_tracks_done(monkeypatch, tmp_path):
    """If the rip fails partway, tracks that already finalised via the
    live path keep their DONE status — partial success is still
    success for those files. Only the unfinished tracks transition to
    FAILED with the disc-level reason."""
    (tmp_path / "Disc_t00.mkv").write_bytes(b"x" * 100)

    # rip_disc failure path — but on_title_done was already called for
    # source idx 0 before the disc-level error fired.
    fake_result = RipDiscResult(
        overall_error="makemkvcon failed mid-rip",
        titles={0: RipResult(ok=True, output_path=None, size_bytes=None)},
    )
    _stub_rip_disc(monkeypatch, fake_result, fire_per_title_start=True, fire_per_title_done=True)

    events: list[tuple[str, str, str | None]] = []

    async def on_start(track: TrackView) -> None:
        events.append(("start", track.id, None))

    async def on_done(track: TrackView, result: RipResult) -> None:
        events.append(("done", track.id, result.error if not result.ok else None))

    await rip_all(
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        tracks=[_track(0), _track(1)],
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
        min_length_seconds=600,
    )

    # Track 0 was finalised via the live path and stays DONE.
    # Track 1 hadn't finalised; it gets the disc-level FAILED reason.
    assert ("done", "trk_0", None) in events
    failures = [e for e in events if e[0] == "done" and e[1] == "trk_1"]
    assert len(failures) == 1
    assert failures[0][2] == "makemkvcon failed mid-rip"


async def test_rip_all_live_done_handles_unselected_titles_gracefully(monkeypatch, tmp_path):
    """If MakeMKV's stream announces a title that isn't in the user's
    track selection (rare but possible if `mkv all` picks up extras),
    the dispatcher's `_on_title_done` no-ops cleanly without
    crashing or PATCHing a non-existent track."""
    fake_result = RipDiscResult(
        overall_error=None,
        titles={0: RipResult(ok=True), 5: RipResult(ok=True)},  # 5 not in track list
    )
    _stub_rip_disc(monkeypatch, fake_result, fire_per_title_start=True, fire_per_title_done=True)
    (tmp_path / "Disc_t00.mkv").write_bytes(b"x" * 50)

    events: list[str] = []

    async def on_start(track: TrackView) -> None:
        events.append(f"start-{track.id}")

    async def on_done(track: TrackView, result: RipResult) -> None:
        events.append(f"done-{track.id}")

    await rip_all(
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        tracks=[_track(0)],  # only track 0 selected
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
        min_length_seconds=600,
    )

    # Track 0 went start → done. Title 5 was unselected; no events for it.
    assert events == ["start-trk_0", "done-trk_0"]


async def test_rip_all_dump_track_uses_data_rip_even_on_a_bluray_scan(monkeypatch, tmp_path):
    """The backend routes an ISO image MakeMKV could not open to the full-disc
    dump session: its single DATA_DUMP track must go through rip_data, never
    back into makemkvcon, even though the scan still says bluray."""
    data_calls: list[str] = []

    async def fake_rip_data(*, device_path, output_dir, on_progress=None):
        data_calls.append(device_path)
        if on_progress is not None:
            await on_progress(512, 1024)
        return RipResult(ok=True, output_path=output_dir / "dump.iso", size_bytes=1, sha256="x")

    async def fake_rip_disc(**_kwargs):
        raise AssertionError("makemkvcon must not be invoked for a dump track")

    monkeypatch.setattr(dispatcher_module, "rip_data", fake_rip_data)
    monkeypatch.setattr(optical_rip_module, "rip_disc", fake_rip_disc)
    dump = _track(0, source_ref="full")
    dump = dump.model_copy(update={"kind": TrackKind.DATA_DUMP})
    done: list[tuple[str, bool]] = []

    async def on_start(_t):
        pass

    async def on_done(t, result):
        done.append((t.id, result.ok))

    await dispatcher_module.rip_all(
        disc_type=DiscType.BLURAY,
        device_path="/source/movie.iso",
        tracks=[dump],
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
    )
    assert data_calls == ["/source/movie.iso"]
    assert done == [("trk_0", True)]


async def test_rip_all_dump_progress_carries_transfer_stats(monkeypatch, tmp_path):
    """The full-disc copy reports a fraction plus bytes done, total and rate."""

    async def fake_rip_data(*, device_path, output_dir, on_progress=None):
        await on_progress(256, 1024)
        await on_progress(1024, 1024)
        return RipResult(ok=True, output_path=output_dir / "dump.iso", size_bytes=1024, sha256="x")

    monkeypatch.setattr(dispatcher_module, "rip_data", fake_rip_data)
    dump = _track(0, source_ref="full").model_copy(update={"kind": TrackKind.DATA_DUMP})
    ticks: list[tuple[float, dict]] = []

    async def on_progress(_t, fraction, stats=None):
        ticks.append((fraction, stats))

    async def _noop(*_a):
        pass

    await dispatcher_module.rip_all(
        disc_type=DiscType.DATA,
        device_path="/source/movie.iso",
        tracks=[dump],
        output_dir=tmp_path,
        on_track_start=_noop,
        on_track_done=_noop,
        on_track_progress=on_progress,
    )
    assert [round(f, 2) for f, _s in ticks] == [0.25, 1.0]
    assert ticks[0][1]["bytes_done"] == 256 and ticks[0][1]["bytes_total"] == 1024
    assert ticks[-1][1]["rate_bps"] is None or ticks[-1][1]["rate_bps"] > 0


async def test_rip_all_disc_backup_track_uses_rip_backup(monkeypatch, tmp_path):
    backup_calls: list[str] = []

    async def fake_rip_backup(*, device_path, output_dir, on_progress=None):
        backup_calls.append(device_path)
        if on_progress is not None:
            await on_progress(0.5)
        return RipResult(ok=True, output_path=output_dir / "backup", size_bytes=7)

    async def must_not_run(**_kwargs):
        raise AssertionError("a disc backup must not reach rip_disc or rip_data")

    monkeypatch.setattr(dispatcher_module, "rip_backup", fake_rip_backup)
    monkeypatch.setattr(optical_rip_module, "rip_disc", must_not_run)
    monkeypatch.setattr(dispatcher_module, "rip_data", must_not_run)
    backup = _track(0, source_ref="full").model_copy(update={"kind": TrackKind.DISC_BACKUP})
    events: list[tuple[str, Any]] = []

    async def on_start(t):
        events.append(("start", t.id))

    async def on_progress(t, fraction, stats=None):
        events.append(("progress", (t.id, fraction, stats)))

    async def on_done(t, result):
        events.append(("done", (t.id, result.ok, result.size_bytes)))

    await dispatcher_module.rip_all(
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        tracks=[backup],
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
        on_track_progress=on_progress,
    )
    assert backup_calls == ["/dev/sr0"]
    assert events == [
        ("start", "trk_0"),
        ("progress", ("trk_0", 0.5, None)),
        ("done", ("trk_0", True, 7)),
    ]


async def test_rip_all_hashes_each_title_and_patches_done_with_its_sha256(monkeypatch, tmp_path):
    """The makemkv path hashes each title in the background as soon
    as it is written (rip_disc is told not to re-read everything after the
    rip) and PATCHes DONE with the digest, live titles and post-rip ones
    alike. Whatever is still hashing after the rip is reported as a
    "verifying" phase on the progress channel."""
    import hashlib

    (tmp_path / "title_t00.mkv").write_bytes(b"main feature")
    (tmp_path / "title_t01.mkv").write_bytes(b"extra")
    fake_result = RipDiscResult(
        overall_error=None,
        titles={
            0: RipResult(ok=True, output_path=tmp_path / "title_t00.mkv", size_bytes=12),
            1: RipResult(ok=True, output_path=tmp_path / "title_t01.mkv", size_bytes=5),
        },
    )
    captured: dict[str, Any] = {}
    _stub_rip_disc(monkeypatch, fake_result, captured=captured, fire_per_title_start=False)

    # Title 0 finalises live (mid-rip); title 1 is attributed post-rip.
    real_stub = optical_rip_module.rip_disc

    async def live_then_post(**kwargs: Any) -> RipDiscResult:
        await kwargs["on_title_done"](0)
        return await real_stub(**kwargs)

    monkeypatch.setattr(optical_rip_module, "rip_disc", live_then_post)

    done: dict[str, str | None] = {}
    phases: list[str] = []

    async def noop_start(_track: TrackView) -> None:
        return None

    async def on_done(track: TrackView, result: RipResult) -> None:
        assert result.ok
        done[track.id] = result.sha256

    async def on_progress(_track: TrackView, _fraction: float, stats: Any = None) -> None:
        if stats is not None and "phase" in stats:
            phases.append(stats["phase"])

    await rip_all(
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        tracks=[_track(0), _track(1)],
        output_dir=tmp_path,
        on_track_start=noop_start,
        on_track_done=on_done,
        on_track_progress=on_progress,
        min_length_seconds=600,
    )

    assert captured["hash_outputs"] is False
    assert done == {
        "trk_0": hashlib.sha256(b"main feature").hexdigest(),
        "trk_1": hashlib.sha256(b"extra").hexdigest(),
    }
    assert set(phases) <= {"verifying"}


async def test_title_hasher_reports_verify_progress_until_done(tmp_path):
    from arm_ripper.rip import title_hasher

    path = tmp_path / "t.mkv"
    path.write_bytes(b"x" * 10)
    gate = asyncio.Event()
    real = title_hasher.sha256_file

    async def slow(p, on_bytes=None):  # type: ignore[no-untyped-def]
        await gate.wait()
        return await real(p, on_bytes)

    title_hasher.sha256_file = slow  # type: ignore[assignment]
    try:
        hasher = title_hasher.TitleHasher()
        got: list[str | None] = []

        async def then(digest: str | None) -> None:
            got.append(digest)

        hasher.submit(path, 10, then)
        seen: list[tuple[int, int]] = []

        async def on_progress(done: int, total: int, _rate: float | None) -> None:
            seen.append((done, total))
            gate.set()

        await hasher.finish(on_progress)
    finally:
        title_hasher.sha256_file = real  # type: ignore[assignment]
    assert seen and seen[0] == (0, 10)
    assert got and got[0] is not None


async def test_title_hasher_passes_none_for_an_unreadable_file(tmp_path):
    from arm_ripper.rip.title_hasher import TitleHasher

    hasher = TitleHasher()
    got: list[str | None] = []

    async def then(digest: str | None) -> None:
        got.append(digest)

    hasher.submit(tmp_path / "missing.mkv", 1, then)
    await hasher.finish()
    assert got == [None]


async def test_rip_all_resume_pass_skips_titles_an_earlier_pass_settled(monkeypatch, tmp_path):
    """A resume after the drive dropped off the bus runs one more
    `mkv all`, which rips every title again. Titles already settled get no
    callbacks and their duplicate files are deleted; the rest attribute by
    position exactly as in a first pass."""
    for pos in range(3):
        (tmp_path / f"Disc_t{pos:02d}.mkv").write_bytes(b"x" * (10 + pos))
    fake_result = RipDiscResult(
        overall_error=None,
        titles={
            0: RipResult(ok=True, output_path=tmp_path / "Disc_t00.mkv", size_bytes=10),
            1: RipResult(ok=True, output_path=tmp_path / "Disc_t01.mkv", size_bytes=11),
            2: RipResult(ok=True, output_path=tmp_path / "Disc_t02.mkv", size_bytes=12),
        },
    )
    captured: dict[str, Any] = {}
    stop = asyncio.Event()
    _stub_rip_disc(monkeypatch, fake_result, captured=captured, fire_per_title_start=True, fire_per_title_done=True)

    events: list[tuple[str, str]] = []

    async def on_start(track: TrackView) -> None:
        events.append(("start", track.id))

    async def on_done(track: TrackView, result: RipResult) -> None:
        assert result.ok
        events.append(("done", track.id))

    await rip_all(
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr1",
        tracks=[_track(0), _track(1), _track(2)],
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
        min_length_seconds=600,
        stop=stop,
        skip_track_ids={"trk_0"},
    )

    # Positions still line up with every eligible title, skipped or not.
    assert captured["eligible_source_indexes"] == [0, 1, 2]
    assert {e[1] for e in events} == {"trk_1", "trk_2"}
    assert sorted(f.name for f in tmp_path.glob("*.mkv")) == ["Disc_t01.mkv", "Disc_t02.mkv"]


async def test_rip_all_stopped_pass_reports_the_rest_without_touching_settled_tracks(monkeypatch, tmp_path):
    """A pass stopped by the lost drive reports its unfinished tracks with
    the stop error (the controller holds them for the resume), never the
    ones an earlier pass settled."""
    from arm_ripper.rip.makemkv_process import STOPPED_ERROR

    _stub_rip_disc(monkeypatch, RipDiscResult(overall_error=STOPPED_ERROR, titles={}), fire_per_title_start=False)
    done: list[tuple[str, str | None]] = []

    async def on_start(track: TrackView) -> None:
        pass

    async def on_done(track: TrackView, result: RipResult) -> None:
        done.append((track.id, result.error))

    await rip_all(
        disc_type=DiscType.DVD,
        device_path="/dev/sr0",
        tracks=[_track(0), _track(1), _track(2, source_ref="bad")],
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
        min_length_seconds=600,
        skip_track_ids={"trk_0", "trk_2"},
    )
    assert done == [("trk_1", STOPPED_ERROR)]


async def test_rip_all_does_not_finalise_a_title_the_drive_dropped_under(monkeypatch, tmp_path):
    """makemkvcon moves on from the title the drive dropped under (a
    PRGC transition) before the poll loop notices. That title's file is cut
    short, so it and the rest are reported stopped, never DONE, and `stop` is
    set to kill makemkvcon."""
    from arm_ripper.rip.makemkv_process import STOPPED_ERROR

    for pos in range(3):
        (tmp_path / f"Disc_t{pos:02d}.mkv").write_bytes(b"x" * (10 + pos))
    fake_result = RipDiscResult(
        overall_error=None,
        titles={idx: RipResult(ok=True, output_path=tmp_path / f"Disc_t{idx:02d}.mkv") for idx in range(3)},
    )
    _stub_rip_disc(monkeypatch, fake_result, fire_per_title_start=True, fire_per_title_done=True)
    asked: list[int] = []

    def drive_lost() -> bool:
        # Still there when title 0 finishes; gone by the time title 1 does.
        asked.append(1)
        return len(asked) > 1

    stop = asyncio.Event()
    done: list[tuple[str, bool, str | None]] = []

    async def on_start(track: TrackView) -> None:
        pass

    async def on_done(track: TrackView, result: RipResult) -> None:
        done.append((track.id, result.ok, result.error))

    await rip_all(
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        tracks=[_track(0), _track(1), _track(2)],
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
        min_length_seconds=600,
        stop=stop,
        drive_lost=drive_lost,
    )

    assert stop.is_set()
    assert sorted(done) == [("trk_0", True, None), ("trk_1", False, STOPPED_ERROR), ("trk_2", False, STOPPED_ERROR)]


async def test_rip_all_with_the_drive_present_finalises_every_title(monkeypatch, tmp_path):
    for pos in range(2):
        (tmp_path / f"Disc_t{pos:02d}.mkv").write_bytes(b"x" * (10 + pos))
    fake_result = RipDiscResult(
        overall_error=None,
        titles={idx: RipResult(ok=True, output_path=tmp_path / f"Disc_t{idx:02d}.mkv") for idx in range(2)},
    )
    _stub_rip_disc(monkeypatch, fake_result, fire_per_title_start=True, fire_per_title_done=True)
    stop = asyncio.Event()
    done: list[tuple[str, bool]] = []

    async def on_start(track: TrackView) -> None:
        pass

    async def on_done(track: TrackView, result: RipResult) -> None:
        done.append((track.id, result.ok))

    await rip_all(
        disc_type=DiscType.DVD,
        device_path="/dev/sr0",
        tracks=[_track(0), _track(1)],
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
        min_length_seconds=600,
        stop=stop,
        drive_lost=lambda: False,
    )
    assert not stop.is_set()
    assert sorted(done) == [("trk_0", True), ("trk_1", True)]


# --- _on_title_done early exits ----------------------------------------------


async def _fire_on_title_done_once(monkeypatch, tmp_path, tracks: list[TrackView], title_idx: int) -> dict[str, Any]:
    """Run rip_all with a fake rip_disc that fires `on_title_done(title_idx)`
    once and snapshots, right after the closure returns, what it handed to
    the hasher and which lifecycle callbacks had fired by then."""
    seen: dict[str, Any] = {"submitted": [], "events": []}
    real_submit = optical_rip_module.TitleHasher.submit

    def recording_submit(self: Any, path: Path, size: int, on_hashed: Any) -> None:
        seen["submitted"].append(path)
        real_submit(self, path, size, on_hashed)

    monkeypatch.setattr(optical_rip_module.TitleHasher, "submit", recording_submit)

    async def fake_rip_disc(**kwargs: Any) -> RipDiscResult:
        await kwargs["on_title_done"](title_idx)
        seen["submitted_in_closure"] = list(seen["submitted"])
        seen["events_in_closure"] = list(seen["events"])
        return RipDiscResult(overall_error=None, titles={})

    monkeypatch.setattr(optical_rip_module, "rip_disc", fake_rip_disc)

    async def on_start(track: TrackView) -> None:
        seen["events"].append(("start", track.id))

    async def on_done(track: TrackView, result: RipResult) -> None:
        seen["events"].append(("done", track.id))

    async def on_progress(track: TrackView, fraction: float, stats: Any = None) -> None:
        seen["events"].append(("progress", track.id))

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
    return seen


async def test_on_title_done_ignores_a_title_missing_from_the_eligible_list(monkeypatch, tmp_path, caplog):
    """Track 5 is selected but shorter than the minimum length, so it is
    not in the eligible list: the closure returns before touching the disk."""
    (tmp_path / "Disc_t00.mkv").write_bytes(b"x" * 10)
    tracks = [_track(0), _track(5, duration_seconds=60)]

    with caplog.at_level(logging.DEBUG, logger=optical_rip_module.logger.name):
        seen = await _fire_on_title_done_once(monkeypatch, tmp_path, tracks, 5)

    assert seen["submitted_in_closure"] == []
    assert seen["events_in_closure"] == []
    assert not [r for r in caplog.records if r.name == optical_rip_module.logger.name and "on_title_done" in r.message]


async def test_on_title_done_defers_a_title_whose_file_is_not_on_disk_yet(monkeypatch, tmp_path, caplog):
    """No `_tNN.mkv` exists for the title's position: the closure logs at
    debug and returns without hashing or PATCHing anything."""
    with caplog.at_level(logging.DEBUG, logger=optical_rip_module.logger.name):
        seen = await _fire_on_title_done_once(monkeypatch, tmp_path, [_track(0)], 0)

    assert seen["submitted_in_closure"] == []
    assert seen["events_in_closure"] == []
    records = [r for r in caplog.records if r.name == optical_rip_module.logger.name and "deferring" in r.message]
    assert len(records) == 1
    assert records[0].levelno == logging.DEBUG
    assert records[0].getMessage() == "on_title_done: file for source_idx=0 position=0 not on disk yet; deferring"


async def test_on_title_done_warns_and_skips_a_title_whose_file_cannot_be_stat_ed(monkeypatch, tmp_path, caplog):
    """A dangling symlink named like the output is listed by the glob but
    `stat` fails: the closure logs a warning and hands nothing to the hasher."""
    dangling = tmp_path / "Disc_t00.mkv"
    dangling.symlink_to(tmp_path / "missing_target.mkv")

    with caplog.at_level(logging.DEBUG, logger=optical_rip_module.logger.name):
        seen = await _fire_on_title_done_once(monkeypatch, tmp_path, [_track(0)], 0)

    assert seen["submitted_in_closure"] == []
    assert seen["events_in_closure"] == []
    records = [r for r in caplog.records if r.name == optical_rip_module.logger.name and "stat failed" in r.message]
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert records[0].getMessage().startswith(f"on_title_done: stat failed source_idx=0 path={dangling} err=")


# --- rip_optical post-rip attribution, failures and progress ----------------


async def _run_rip_all_recording_events(tmp_path, tracks: list[TrackView]) -> list[tuple[Any, ...]]:
    """Run rip_all over DVD/BD tracks and return every lifecycle callback in order."""
    events: list[tuple[Any, ...]] = []

    async def on_start(track: TrackView) -> None:
        events.append(("start", track.id))

    async def on_done(track: TrackView, result: RipResult) -> None:
        events.append(("done", track.id, result))

    async def on_progress(track: TrackView, fraction: float, stats: Any = None) -> None:
        events.append(("progress", track.id, fraction))

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
    return events


async def test_rip_all_reports_a_failed_title_result_as_is_after_starting_the_track(monkeypatch, tmp_path):
    """A title rip_disc reports as not ok, or ok without an output path, gets
    on_track_start then on_track_done with that very RipResult object."""
    failed = RipResult(ok=False, error="title 0 write error")
    no_path = RipResult(ok=True, output_path=None, size_bytes=5)
    _stub_rip_disc(
        monkeypatch,
        RipDiscResult(overall_error=None, titles={0: failed, 1: no_path}),
        fire_per_title_start=False,
    )

    events = await _run_rip_all_recording_events(tmp_path, [_track(0), _track(1)])

    assert events == [
        ("start", "trk_0"),
        ("done", "trk_0", failed),
        ("start", "trk_1"),
        ("done", "trk_1", no_path),
    ]
    assert events[1][2] is failed
    assert events[3][2] is no_path


async def test_rip_all_keeps_the_duration_a_title_result_already_has(monkeypatch, tmp_path):
    """A successful title result that carries its own duration is not rebuilt
    with the track's duration: the hasher gets it and on_track_done reports the
    same duration, output path and size plus the file's sha256."""
    import hashlib

    mkv = tmp_path / "title_t00.mkv"
    mkv.write_bytes(b"main feature")
    result = RipResult(ok=True, output_path=mkv, size_bytes=12, duration_seconds=42)
    _stub_rip_disc(
        monkeypatch,
        RipDiscResult(overall_error=None, titles={0: result}),
        fire_per_title_start=False,
    )
    submitted: list[tuple[Path, int]] = []
    real_submit = optical_rip_module.TitleHasher.submit

    def recording_submit(self: Any, path: Path, size: int, on_hashed: Any) -> None:
        submitted.append((path, size))
        real_submit(self, path, size, on_hashed)

    monkeypatch.setattr(optical_rip_module.TitleHasher, "submit", recording_submit)

    events = await _run_rip_all_recording_events(tmp_path, [_track(0, duration_seconds=1800)])

    assert submitted == [(mkv, 12)]
    # The hasher's own "verifying" progress may interleave; only lifecycle order matters.
    lifecycle = [e for e in events if e[0] != "progress"]
    assert [e[:2] for e in lifecycle] == [("start", "trk_0"), ("done", "trk_0")]
    reported = lifecycle[1][2]
    assert reported.ok is True
    assert reported.output_path == mkv
    assert reported.size_bytes == 12
    assert reported.duration_seconds == 42
    assert reported.sha256 == hashlib.sha256(b"main feature").hexdigest()


@pytest.mark.parametrize("exc", [RuntimeError("rip blew up"), asyncio.CancelledError()], ids=["error", "cancel"])
async def test_rip_all_cancels_the_hasher_and_propagates_an_exception_raised_mid_rip(monkeypatch, tmp_path, exc):
    """Anything raised inside the rip cancels the background hasher and
    reaches the caller of rip_all as the same exception object."""
    cancelled: list[Any] = []
    real_cancel = optical_rip_module.TitleHasher.cancel

    def recording_cancel(self: Any) -> None:
        cancelled.append(self)
        real_cancel(self)

    monkeypatch.setattr(optical_rip_module.TitleHasher, "cancel", recording_cancel)

    async def raising_rip_disc(**kwargs: Any) -> RipDiscResult:
        raise exc

    monkeypatch.setattr(optical_rip_module, "rip_disc", raising_rip_disc)

    with pytest.raises(type(exc)) as caught:
        await _run_rip_all_recording_events(tmp_path, [_track(0)])

    assert caught.value is exc
    assert len(cancelled) == 1


async def test_rip_all_drops_per_title_progress_for_a_title_that_was_not_selected(monkeypatch, tmp_path):
    """Progress for a title index with no selected track fires no
    on_track_progress; progress for a selected title does."""

    async def fake_rip_disc(**kwargs: Any) -> RipDiscResult:
        await kwargs["on_title_progress"](9, 0.25)
        await kwargs["on_title_progress"](0, 0.5)
        return RipDiscResult(overall_error=None, titles={})

    monkeypatch.setattr(optical_rip_module, "rip_disc", fake_rip_disc)

    events = await _run_rip_all_recording_events(tmp_path, [_track(0)])

    assert [e for e in events if e[0] == "progress"] == [("progress", "trk_0", 0.5)]


# --- rip_all (CD, DATA, fallback, backup progress) ---------------------------


def _stub_rip_cd(
    monkeypatch,
    *,
    fire_done: list[int] | None = None,
    returned: dict[int, RipResult] | None = None,
) -> dict[str, Any]:
    """Replace dispatcher's rip_cd with a fake that records its kwargs, fires
    `on_track_done` for each index in `fire_done` (known to the dispatcher or
    not) with an ok result, and returns `returned`."""
    captured: dict[str, Any] = {}

    async def fake_rip_cd(**kwargs: Any) -> dict[int, RipResult]:
        captured.update(kwargs)
        for idx in fire_done or []:
            await kwargs["on_track_done"](idx, RipResult(ok=True, size_bytes=idx))
        return returned or {}

    monkeypatch.setattr(dispatcher_module, "rip_cd", fake_rip_cd)
    return captured


def _recorders() -> tuple[list[tuple[Any, ...]], Any, Any]:
    events: list[tuple[Any, ...]] = []

    async def on_start(track: TrackView) -> None:
        events.append(("start", track.id))

    async def on_done(track: TrackView, result: RipResult) -> None:
        events.append(("done", track.id, result.ok, result.error, result.size_bytes))

    return events, on_start, on_done


async def test_rip_all_cd_starts_every_track_then_reports_what_rip_cd_fires(monkeypatch, tmp_path):
    captured = _stub_rip_cd(
        monkeypatch,
        fire_done=[1, 2],
        returned={1: RipResult(ok=True, size_bytes=1), 2: RipResult(ok=True, size_bytes=2)},
    )
    events, on_start, on_done = _recorders()

    await rip_all(
        disc_type=DiscType.CD,
        device_path="/dev/sr0",
        tracks=[_track(1), _track(2)],
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
    )

    assert events == [
        ("start", "trk_1"),
        ("start", "trk_2"),
        ("done", "trk_1", True, None, 1),
        ("done", "trk_2", True, None, 2),
    ]
    assert set(captured) == {"device_path", "output_dir", "track_indexes", "on_track_done"}
    assert captured["device_path"] == "/dev/sr0"
    assert captured["output_dir"] == tmp_path
    assert captured["track_indexes"] == [1, 2]


async def test_rip_all_cd_ignores_a_done_index_that_is_not_a_requested_track(monkeypatch, tmp_path):
    _stub_rip_cd(monkeypatch, fire_done=[9, 1], returned={1: RipResult(ok=True, size_bytes=1)})
    events, on_start, on_done = _recorders()

    await rip_all(
        disc_type=DiscType.CD,
        device_path="/dev/sr0",
        tracks=[_track(1)],
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
    )

    assert events == [("start", "trk_1"), ("done", "trk_1", True, None, 1)]


async def test_rip_all_cd_fails_a_track_rip_cd_left_out(monkeypatch, tmp_path):
    _stub_rip_cd(monkeypatch, fire_done=[1], returned={1: RipResult(ok=True, size_bytes=1)})
    events, on_start, on_done = _recorders()

    await rip_all(
        disc_type=DiscType.CD,
        device_path="/dev/sr0",
        tracks=[_track(1), _track(2)],
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
    )

    assert events == [
        ("start", "trk_1"),
        ("start", "trk_2"),
        ("done", "trk_1", True, None, 1),
        ("done", "trk_2", False, "abcde produced no entry for track 2", None),
    ]


async def test_rip_all_cd_with_no_tracks_still_calls_rip_cd_and_fires_nothing(monkeypatch, tmp_path):
    captured = _stub_rip_cd(monkeypatch)
    events, on_start, on_done = _recorders()

    await rip_all(
        disc_type=DiscType.CD,
        device_path="/dev/sr0",
        tracks=[],
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
    )

    assert events == []
    assert captured["track_indexes"] == []


async def test_rip_all_data_with_no_tracks_returns_without_a_callback(monkeypatch, tmp_path):
    async def must_not_run(**_kwargs: Any) -> RipResult:
        raise AssertionError("rip_data must not run without a track")

    monkeypatch.setattr(dispatcher_module, "rip_data", must_not_run)
    events, on_start, on_done = _recorders()

    await rip_all(
        disc_type=DiscType.DATA,
        device_path="/dev/sr0",
        tracks=[],
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
    )

    assert events == []


async def test_rip_all_data_progress_is_dropped_without_a_progress_callback(monkeypatch, tmp_path):
    async def fake_rip_data(*, device_path, output_dir, on_progress=None):
        await on_progress(10, 100)
        return RipResult(ok=True, size_bytes=10)

    monkeypatch.setattr(dispatcher_module, "rip_data", fake_rip_data)
    events, on_start, on_done = _recorders()

    await rip_all(
        disc_type=DiscType.DATA,
        device_path="/dev/sr0",
        tracks=[_track(0)],
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
    )

    assert events == [("start", "trk_0"), ("done", "trk_0", True, None, 10)]


async def test_rip_all_data_progress_has_zero_fraction_and_no_rate_for_unknown_total_and_no_elapsed(
    monkeypatch, tmp_path
):
    """With an unknown total the fraction is 0.0, and with no time elapsed the
    rate is None."""

    async def fake_rip_data(*, device_path, output_dir, on_progress=None):
        await on_progress(10, None)
        return RipResult(ok=True)

    class _FrozenTime:
        @staticmethod
        def monotonic() -> float:
            return 5.0

    monkeypatch.setattr(dispatcher_module, "rip_data", fake_rip_data)
    monkeypatch.setattr(dispatcher_module, "time", _FrozenTime)
    ticks: list[tuple[str, float, Any]] = []

    async def on_progress(track: TrackView, fraction: float, stats: Any = None) -> None:
        ticks.append((track.id, fraction, stats))

    _events, on_start, on_done = _recorders()
    await rip_all(
        disc_type=DiscType.DATA,
        device_path="/dev/sr0",
        tracks=[_track(0)],
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
        on_track_progress=on_progress,
    )

    assert ticks == [("trk_0", 0.0, {"bytes_done": 10, "bytes_total": None, "rate_bps": None})]


async def test_rip_all_unknown_disc_type_fails_every_track_with_no_rip_path(monkeypatch, tmp_path):
    events, on_start, on_done = _recorders()

    await rip_all(
        disc_type=DiscType.UNKNOWN,
        device_path="/dev/sr0",
        tracks=[_track(0), _track(1)],
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
    )

    assert events == [
        ("done", "trk_0", False, "no rip path for disc_type=unknown", None),
        ("done", "trk_1", False, "no rip path for disc_type=unknown", None),
    ]


async def test_rip_all_unknown_disc_type_with_no_tracks_fires_nothing(monkeypatch, tmp_path):
    events, on_start, on_done = _recorders()

    await rip_all(
        disc_type=DiscType.UNKNOWN,
        device_path="/dev/sr0",
        tracks=[],
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
    )

    assert events == []


async def test_rip_all_disc_backup_progress_is_dropped_without_a_progress_callback(monkeypatch, tmp_path):
    async def fake_rip_backup(*, device_path, output_dir, on_progress=None):
        await on_progress(0.5)
        return RipResult(ok=True, size_bytes=7)

    monkeypatch.setattr(dispatcher_module, "rip_backup", fake_rip_backup)
    backup = _track(0, source_ref="full").model_copy(update={"kind": TrackKind.DISC_BACKUP})
    events, on_start, on_done = _recorders()

    await rip_all(
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        tracks=[backup],
        output_dir=tmp_path,
        on_track_start=on_start,
        on_track_done=on_done,
    )

    assert events == [("start", "trk_0"), ("done", "trk_0", True, None, 7)]


def test_index_tracks_maps_a_valid_source_ref_to_its_track() -> None:
    track = _track(1, source_ref="7")
    assert _index_tracks([track], set()) == ({7: track}, [])


def test_index_tracks_skips_an_invalid_source_ref_in_skip_track_ids() -> None:
    bad = _track(1, source_ref="x")
    assert _index_tracks([bad], {bad.id}) == ({}, [])


def test_index_tracks_returns_invalid_source_refs_in_input_order() -> None:
    first, good, second = _track(1, source_ref="x"), _track(2), _track(3, source_ref="y")
    assert _index_tracks([first, good, second], set()) == ({2: good}, [first, second])


def test_eligible_source_indexes_leave_out_a_track_shorter_than_the_minimum() -> None:
    assert _eligible_source_indexes({1: _track(1, duration_seconds=59)}, 60) == []


def test_eligible_source_indexes_keep_tracks_at_or_above_the_minimum() -> None:
    by_index = {1: _track(1, duration_seconds=60), 2: _track(2, duration_seconds=61)}
    assert _eligible_source_indexes(by_index, 60) == [1, 2]


def test_eligible_source_indexes_keep_a_track_of_unknown_length() -> None:
    assert _eligible_source_indexes({1: _track(1, duration_seconds=None)}, 60) == [1]


def test_eligible_source_indexes_are_sorted_whatever_the_insertion_order() -> None:
    by_index = {5: _track(5), 2: _track(2), 9: _track(9)}
    assert _eligible_source_indexes(by_index, 60) == [2, 5, 9]


def test_first_eligible_track_is_none_when_nothing_is_eligible() -> None:
    assert _first_eligible_track({1: _track(1)}, []) is None


def test_first_eligible_track_is_the_track_of_the_first_eligible_index() -> None:
    by_index = {1: _track(1), 4: _track(4), 7: _track(7)}
    assert _first_eligible_track(by_index, [4, 7]) is by_index[4]


def test_no_output_error_says_a_too_short_track_was_skipped() -> None:
    track = _track(3, duration_seconds=59)
    assert _no_output_error(3, track, 60, [3]) == "track duration 59s below minlength=60s; makemkvcon skipped it"


def test_no_output_error_treats_a_track_at_the_minimum_as_producing_nothing() -> None:
    track = _track(3, duration_seconds=60)
    assert _no_output_error(3, track, 60, [3]) == "makemkvcon produced no output for title 3 (eligible=True)"


def test_no_output_error_treats_a_track_of_unknown_length_as_producing_nothing() -> None:
    track = _track(3, duration_seconds=None)
    assert _no_output_error(3, track, 60, [3]) == "makemkvcon produced no output for title 3 (eligible=True)"


def test_no_output_error_reports_an_ineligible_title_as_not_eligible() -> None:
    track = _track(3, duration_seconds=None)
    assert _no_output_error(3, track, 60, [1]) == "makemkvcon produced no output for title 3 (eligible=False)"


def test_finished_file_returns_the_file_at_the_position_and_its_size(tmp_path) -> None:
    (tmp_path / "Disc_t00.mkv").write_bytes(b"abc")
    assert _finished_file(tmp_path, 0, 0) == (tmp_path / "Disc_t00.mkv", 3)


def test_finished_file_indexes_the_files_in_their_tnn_order(tmp_path) -> None:
    (tmp_path / "Disc_t01.mkv").write_bytes(b"second")
    (tmp_path / "Disc_t00.mkv").write_bytes(b"1st")
    assert _finished_file(tmp_path, 7, 1) == (tmp_path / "Disc_t01.mkv", 6)


def test_finished_file_is_none_and_logs_when_the_position_is_past_the_end(tmp_path, caplog) -> None:
    (tmp_path / "Disc_t00.mkv").write_bytes(b"abc")
    with caplog.at_level(logging.DEBUG, logger=optical_rip_module.logger.name):
        assert _finished_file(tmp_path, 4, 1) is None
    assert [r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG] == [
        "on_title_done: file for source_idx=4 position=1 not on disk yet; deferring"
    ]


def test_finished_file_is_none_and_warns_when_the_file_cannot_be_stat_ed(tmp_path, caplog) -> None:
    dangling = tmp_path / "Disc_t00.mkv"
    dangling.symlink_to(tmp_path / "missing_target.mkv")
    with caplog.at_level(logging.DEBUG, logger=optical_rip_module.logger.name):
        assert _finished_file(tmp_path, 0, 0) is None
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert warnings[0].getMessage().startswith(f"on_title_done: stat failed source_idx=0 path={dangling} err=")


def test_effective_disc_type_is_data_when_every_track_is_a_full_disc_dump() -> None:
    dump = _track(0, source_ref="full").model_copy(update={"kind": TrackKind.DATA_DUMP})

    assert _effective_disc_type(DiscType.BLURAY, [dump]) == DiscType.DATA


def test_effective_disc_type_keeps_the_scan_type_for_mixed_kinds() -> None:
    dump = _track(0, source_ref="full").model_copy(update={"kind": TrackKind.DATA_DUMP})

    assert _effective_disc_type(DiscType.BLURAY, [dump, _track(1)]) == DiscType.BLURAY


def test_effective_disc_type_keeps_the_scan_type_without_tracks() -> None:
    assert _effective_disc_type(DiscType.DVD, []) == DiscType.DVD
