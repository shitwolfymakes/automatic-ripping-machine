"""A rip keeps a 3D title's MVC dependent view only when the backend says so: the makemkvcon run's selection, per
title and in one `mkv all`, and the size the output is checked against."""

import os
from pathlib import Path
from typing import Any

import pytest

from arm_common.enums import TrackKind, TrackStatus
from arm_common.schemas import TrackView
from arm_ripper.rip import makemkv_rip
from arm_ripper.rip import optical_rip as optical_rip_module
from arm_ripper.rip.makemkv_rip import RipDiscResult
from arm_ripper.rip.makemkv_selection import KEEP_MVC_SELECTION, SELECTION_KEY, keep_mvc_environment
from arm_ripper.rip.makemkv_settle import suspect_output
from arm_ripper.rip.optical_rip import expected_output_size
from arm_ripper.rip.options import RipOptions
from arm_ripper.rip.result import RipResult

_JOB = "job_01M4R7157QDCVQ3MX6M2VK0XX0"
_DEFAULT_SELECTION = "-sel:all,+sel:(favlang|nolang),-sel:mvcvideo,=100:all,-10:favlang"
_SCAN_SIZE = 45_642_405_888
_BASE_ONLY_SIZE = 28_535_928_530


def _track(
    idx: int, *, ref: str | None = None, stereo: bool = False, status: TrackStatus = TrackStatus.QUEUED
) -> TrackView:
    return TrackView(
        id=f"trk_{idx}",
        job_id=_JOB,
        kind=TrackKind.VIDEO_TITLE,
        index=idx,
        source_ref=ref or f"0033{idx}.mpls",
        status=status,
        output_path=None,
        size_bytes=None,
        duration_seconds=1800,
        expected_size_bytes=_SCAN_SIZE,
        attempts=0,
        last_error=None,
        stereo_3d=stereo,
    )


@pytest.fixture
def shared_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    settings = home / ".MakeMKV"
    settings.mkdir(parents=True)
    (settings / "settings.conf").write_text(f'app_Key = "T-key"\n{SELECTION_KEY} = "{_DEFAULT_SELECTION}"\n')
    (settings / "keydb.cfg").write_text("keys")
    monkeypatch.setenv("HOME", str(home))
    return home


def test_the_keep_selection_is_makemkvs_default_with_mvc_video_added() -> None:
    assert "-sel:mvcvideo" not in KEEP_MVC_SELECTION
    assert KEEP_MVC_SELECTION == _DEFAULT_SELECTION.replace("-sel:mvcvideo", "+sel:mvcvideo")


def test_the_keep_environment_selects_mvc_in_a_private_home_and_leaves_the_shared_settings(shared_home: Path) -> None:
    shared_conf = shared_home / ".MakeMKV" / "settings.conf"
    before = shared_conf.read_text()
    with keep_mvc_environment() as env:
        run_home = Path(env["HOME"])
        conf = (run_home / ".MakeMKV" / "settings.conf").read_text().splitlines()
        assert conf == ['app_Key = "T-key"', f'{SELECTION_KEY} = "{KEEP_MVC_SELECTION}"']
        assert (run_home / ".MakeMKV" / "keydb.cfg").read_text() == "keys"
        assert env["PATH"] == os.environ["PATH"]
    assert not run_home.exists()
    assert shared_conf.read_text() == before


async def _run_rip_disc(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, keep_3d: bool, **kw: Any) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    async def fake_run(cmd: list[str], state: Any, *, env: Any = None, **_kw: Any) -> None:
        seen["cmd"] = cmd
        seen["env"] = None if env is None else dict(env)
        if env is not None:
            seen["conf"] = (Path(env["HOME"]) / ".MakeMKV" / "settings.conf").read_text()
        return None

    monkeypatch.setattr(makemkv_rip, "run_makemkvcon", fake_run)
    await makemkv_rip.rip_disc("/dev/sr0", tmp_path / "out", keep_3d=keep_3d, **kw)
    return seen


@pytest.mark.parametrize("title", [None, 1])
async def test_makemkvcon_runs_with_mvc_selected_only_when_asked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, shared_home: Path, title: int | None
) -> None:
    kept = await _run_rip_disc(monkeypatch, tmp_path, keep_3d=True, title=title)
    assert KEEP_MVC_SELECTION in kept["conf"]
    assert kept["env"]["HOME"] != str(shared_home)

    plain = await _run_rip_disc(monkeypatch, tmp_path, keep_3d=False, title=title)
    assert plain["env"] is None
    assert "conf" not in plain


class _Rig:
    """Fakes rip_disc and records the keep_3d each makemkvcon run was given."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: list[dict[str, Any]] = []

        async def fake_rip_disc(**kw: Any) -> RipDiscResult:
            self.calls.append(kw)
            out: Path = kw["output_dir"]
            out.mkdir(parents=True, exist_ok=True)
            path = out / "Disc_t00.mkv"
            path.write_bytes(b"x")
            return RipDiscResult(
                overall_error=None,
                titles={i: RipResult(ok=True, output_path=path, size_bytes=1) for i in kw["eligible_source_indexes"]},
            )

        async def ready(_path: str) -> Any:
            return optical_rip_module.ReadyOutcome.READY

        monkeypatch.setattr(optical_rip_module, "rip_disc", fake_rip_disc)
        monkeypatch.setattr(optical_rip_module, "wait_until_readable", ready)

    async def rip(self, tmp_path: Path, tracks: list[TrackView], options: RipOptions) -> None:
        async def noop(*_a: Any, **_k: Any) -> None:
            return None

        await optical_rip_module.rip_optical(
            device_path="/dev/sr0",
            tracks=tracks,
            output_dir=tmp_path,
            on_track_start=noop,
            on_track_done=noop,
            on_track_progress=None,
            min_length_seconds=60,
            title_numbers={t.source_ref: t.index for t in tracks},
            options=options,
        )


async def test_per_title_mode_selects_mvc_for_the_flagged_title_only(monkeypatch, tmp_path) -> None:
    rig = _Rig(monkeypatch)
    tracks = [_track(1, stereo=True), _track(2), _track(3, stereo=True)]
    options = RipOptions(per_title=True, keep_3d_refs=frozenset({tracks[0].source_ref}))
    await rig.rip(tmp_path, tracks, options)
    assert [(c["title"], c["keep_3d"]) for c in rig.calls] == [(1, True), (2, False), (3, False)]


async def test_mkv_all_mode_selects_mvc_for_the_run_when_any_ticked_title_needs_it(monkeypatch, tmp_path) -> None:
    rig = _Rig(monkeypatch)
    tracks = [_track(1), _track(2, stereo=True)]
    await rig.rip(tmp_path, tracks, RipOptions(keep_3d_refs=frozenset({tracks[1].source_ref})))
    assert [c["keep_3d"] for c in rig.calls] == [True]


async def test_mkv_all_mode_ignores_an_unticked_3d_title(monkeypatch, tmp_path) -> None:
    rig = _Rig(monkeypatch)
    tracks = [_track(1), _track(2, stereo=True, status=TrackStatus.SKIPPED)]
    await rig.rip(tmp_path, tracks, RipOptions(keep_3d_refs=frozenset({tracks[1].source_ref})))
    assert [c["keep_3d"] for c in rig.calls] == [False]


async def test_a_rip_with_no_3d_refs_leaves_makemkvs_default(monkeypatch, tmp_path) -> None:
    rig = _Rig(monkeypatch)
    await rig.rip(tmp_path, [_track(1, stereo=True)], RipOptions())
    assert [c["keep_3d"] for c in rig.calls] == [False]


def test_a_3d_title_ripped_as_2d_has_no_size_to_check() -> None:
    track = _track(1, stereo=True)
    assert expected_output_size(track, keep_3d=False) is None


def test_a_3d_title_ripped_with_mvc_is_checked_against_the_scan_size() -> None:
    assert expected_output_size(_track(1, stereo=True), keep_3d=True) == _SCAN_SIZE


def test_a_2d_title_is_checked_against_the_scan_size_either_way() -> None:
    track = _track(1)
    assert expected_output_size(track, keep_3d=False) == _SCAN_SIZE
    assert expected_output_size(track, keep_3d=True) == _SCAN_SIZE


def test_a_3d_rip_that_lost_its_mvc_view_is_suspect_and_a_2d_rip_of_the_title_is_not(tmp_path: Path) -> None:
    path = tmp_path / "t.mkv"
    path.write_bytes(b"")
    track = _track(1, stereo=True)
    lost = suspect_output(path, _BASE_ONLY_SIZE, expected_output_size(track, keep_3d=True))
    assert any("under 90%" in p for p in lost)
    as_2d = suspect_output(path, _BASE_ONLY_SIZE, expected_output_size(track, keep_3d=False))
    assert not any("under 90%" in p for p in as_2d)
