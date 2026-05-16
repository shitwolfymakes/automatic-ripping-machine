"""Pure-function coverage for transcode_apply: media→kind mapping, the
music track-title context branch, compute_outputs (no candidates +
empty-token raise), find_collisions (empty / existing-task / on-disk /
duplicate-in-request), and stat_exists.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from pathlib import Path  # noqa: E402

import pytest  # noqa: E402

from arm_backend.path_template import TemplateValidationError  # noqa: E402
from arm_backend.transcode_apply import (  # noqa: E402
    _build_track_ctx,
    _track_kinds_for_media,
    compute_outputs,
    find_collisions,
    stat_exists,
)
from arm_common import (  # noqa: E402
    ContainerFormat,
    DiscType,
    Job,
    JobStatus,
    MediaType,
    Session,
    TranscodePreset,
    TranscodeTaskStatus,
    TranscodeTool,
)
from arm_common.enums import TrackKind  # noqa: E402
from arm_common.models import Track, TranscodeTask  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


def _job(meta: dict | None = None) -> Job:
    return Job(
        id="job_x",
        drive_id="drv_x",
        disc_type=DiscType.CD,
        title="Greatest Hits",
        year=1999,
        status=JobStatus.RIPPED,
        metadata_json=meta or {},
        resumed_from_crash=False,
    )


def _track(kind: TrackKind = TrackKind.AUDIO_TRACK, index: int = 1) -> Track:
    return Track(id=f"trk_{index}", job_id="job_x", kind=kind, index=index, source_ref=str(index))


def _session(template: str = "{track_title}.{ext}", mt: MediaType = MediaType.MUSIC) -> Session:
    return Session(
        id="ses_x",
        name="S",
        media_type=mt,
        is_builtin=False,
        rip_preset_id="rpr_x",
        output_path_template=template,
    )


def _tp() -> TranscodePreset:
    return TranscodePreset(
        id="tpr_x",
        name="Plex 1080p",
        media_type=MediaType.MUSIC,
        is_builtin=True,
        tool=TranscodeTool.ABCDE,
        container=ContainerFormat.FLAC,
    )


def test_track_kinds_for_media_all_types() -> None:
    assert _track_kinds_for_media(MediaType.MOVIE) == {TrackKind.VIDEO_TITLE}
    assert _track_kinds_for_media(MediaType.TV) == {TrackKind.VIDEO_TITLE}
    assert _track_kinds_for_media(MediaType.MUSIC) == {TrackKind.AUDIO_TRACK}
    assert _track_kinds_for_media(MediaType.DATA) == {TrackKind.DATA_DUMP, TrackKind.VIDEO_TITLE}
    assert _track_kinds_for_media(MediaType.ISO) == {TrackKind.DATA_DUMP, TrackKind.VIDEO_TITLE}


def test_build_track_ctx_reads_music_title_and_preset() -> None:
    job = _job({"tracks": [{"title": "Opening Theme"}], "artist": "Band", "album": "LP"})
    ctx = _build_track_ctx(job, _track(index=1), _session(), _tp())
    assert ctx["track_title"] == "Opening Theme"
    assert ctx["artist"] == "Band"
    assert ctx["transcode_slug"] == "plex-1080p"
    assert ctx["ext"] == "flac"


def test_build_track_ctx_no_preset_blank_slug() -> None:
    ctx = _build_track_ctx(_job(), _track(), _session(), None)
    assert ctx["transcode_slug"] == ""
    assert ctx["ext"] == ""
    assert ctx["track_title"] == ""  # no metadata tracks list


def test_build_track_ctx_tracks_meta_edge_shapes() -> None:
    # index out of range (72->77), entry not a dict, raw_title not a str
    # (74->77) — each leaves track_title blank without raising.
    assert _build_track_ctx(_job({"tracks": []}), _track(index=1), _session(), None)["track_title"] == ""
    assert _build_track_ctx(_job({"tracks": ["nope"]}), _track(index=1), _session(), None)["track_title"] == ""
    assert _build_track_ctx(_job({"tracks": [{"title": 123}]}), _track(index=1), _session(), None)["track_title"] == ""


def test_compute_outputs_no_relevant_tracks() -> None:
    # Music session but only a VIDEO_TITLE track → no candidates → [].
    out = compute_outputs(_job(), [_track(kind=TrackKind.VIDEO_TITLE)], _session(), _tp())
    assert out == []


def test_compute_outputs_resolves_path() -> None:
    job = _job({"tracks": [{"title": "Song One"}]})
    out = compute_outputs(job, [_track(index=1)], _session(), _tp())
    assert len(out) == 1
    assert out[0].output_path.endswith(".flac")


def test_compute_outputs_empty_token_raises() -> None:
    job = _job({"tracks": [{"title": ""}]})  # track_title resolves empty
    with pytest.raises(TemplateValidationError, match="resolved empty"):
        compute_outputs(job, [_track(index=1)], _session(), _tp())


async def test_find_collisions_empty_paths() -> None:
    assert await find_collisions(FakeSession(), [], Path("/media")) == []  # type: ignore[arg-type]


async def test_find_collisions_existing_task(tmp_path: Path) -> None:
    db = FakeSession()
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_live",
            session_application_id="sap_1",
            source_track_id="trk_1",
            status=TranscodeTaskStatus.IN_PROGRESS,
            output_path="a.flac",
            progress_pct=0,
            attempts=0,
        )
    ]
    cols = await find_collisions(db, ["a.flac"], tmp_path)  # type: ignore[arg-type]
    assert cols[0].reason == "existing_task"
    assert cols[0].existing_task_id == "txt_live"


async def test_find_collisions_on_disk(tmp_path: Path) -> None:
    (tmp_path / "b.flac").write_text("x")
    cols = await find_collisions(FakeSession(), ["b.flac"], tmp_path)  # type: ignore[arg-type]
    assert cols[0].reason == "on_disk"
    assert cols[0].on_filesystem is True


async def test_find_collisions_duplicate_in_request(tmp_path: Path) -> None:
    cols = await find_collisions(FakeSession(), ["dup.flac", "dup.flac"], tmp_path)  # type: ignore[arg-type]
    assert [c.reason for c in cols] == ["duplicate_in_request"]


async def test_find_collisions_existing_task_then_duplicate(tmp_path: Path) -> None:
    """Same path is an existing-task collision AND repeated in the request:
    the second occurrence is already flagged, so no duplicate_in_request is
    added (185->194)."""
    db = FakeSession()
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_live",
            session_application_id="sap_1",
            source_track_id="trk_1",
            status=TranscodeTaskStatus.IN_PROGRESS,
            output_path="c.flac",
            progress_pct=0,
            attempts=0,
        )
    ]
    cols = await find_collisions(db, ["c.flac", "c.flac"], tmp_path)  # type: ignore[arg-type]
    assert [c.reason for c in cols] == ["existing_task"]


def test_stat_exists(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert stat_exists(tmp_path, "") is False
    (tmp_path / "f").write_text("x")
    assert stat_exists(tmp_path, "f") is True
    assert stat_exists(tmp_path, "missing") is False

    def _boom(self: object) -> bool:
        raise OSError("stat failed")

    monkeypatch.setattr(Path, "exists", _boom)
    assert stat_exists(tmp_path, "whatever") is False
