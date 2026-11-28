"""D60 on the rip-start answer: which ticked tracks the ripper keeps the MVC dependent view of. A 3D title keeps it
when the job does not transcode (a passthrough or no session); a transcode session drops it."""

from __future__ import annotations

from typing import Any

import pytest

from arm_backend.routers import ripper as ripper_router
from arm_common import DiscType, Job, JobStatus, MediaType, Session, TrackKind, TrackStatus, TranscodePreset
from arm_common.enums import ContainerFormat, TranscodeTool
from arm_common.models import Track
from arm_common.schemas import BdClip, BdPlaylist, ScanResult

from tests._fakes import FakeSession

_JOB = "job_01JZXR7K3M5Q8N4VWA00000002"


def _scan() -> ScanResult:
    def playlist(name: str, mvc: list[int]) -> BdPlaylist:
        return BdPlaylist(
            name=name,
            clips=[10, 11],
            clip_seconds=[3600.0, 3600.0],
            duration_seconds=7200,
            chapter_count=20,
            mvc_clips=mvc,
        )

    return ScanResult(
        disc_type=DiscType.BLURAY,
        playlists=[playlist("00100.mpls", []), playlist("00101.mpls", [12])],
        clips=[
            BdClip(number=10, seconds=3600.0, size_bytes=1),
            BdClip(number=11, seconds=3600.0, size_bytes=1),
            BdClip(number=12, seconds=3600.0, size_bytes=1, mvc=True),
        ],
    )


def _track(index: int, ref: str) -> Track:
    return Track(
        id=f"trk_{index}",
        job_id=_JOB,
        kind=TrackKind.VIDEO_TITLE,
        index=index,
        source_ref=ref,
        status=TrackStatus.QUEUED,
        attempts=0,
    )


def _job() -> Job:
    return Job(
        id=_JOB,
        drive_id="drv_x",
        disc_type=DiscType.BLURAY,
        title="X",
        year=2000,
        status=JobStatus.RIPPING,
        metadata_json={"scan_result": _scan().model_dump(mode="json")},
    )


def _session(tool: TranscodeTool | None) -> tuple[Session, list[TranscodePreset]]:
    presets = []
    if tool is not None:
        presets = [
            TranscodePreset(
                id="tpr_x",
                name="x",
                media_type=MediaType.MOVIE,
                is_builtin=False,
                tool=tool,
                container=ContainerFormat.MKV,
            )
        ]
    sess = Session(
        id="ses_x",
        name="s",
        media_type=MediaType.MOVIE,
        rip_preset_id="rpr_builtin_movie_archive",
        transcode_preset_id=None if tool is None else "tpr_x",
        output_path_template="{title}",
    )
    return sess, presets


async def _answer(monkeypatch: pytest.MonkeyPatch, tool: TranscodeTool | None) -> Any:
    sess, presets = _session(tool)
    db = FakeSession()
    db.rows["transcode_presets"] = presets

    async def routed(_db: Any, _job: Job) -> Session:
        return sess

    monkeypatch.setattr(ripper_router, "load_routed_session", routed)
    monkeypatch.setattr(ripper_router, "rip_preset_id_from_session", lambda *_a: "rpr_x")
    job = _job()
    preset_id, min_length, prefers_3d = await ripper_router._routed_rip_choice(db, job)  # type: ignore[arg-type]
    tracks = [_track(1, "00100.mpls"), _track(2, "00101.mpls")]
    return await ripper_router._rip_start_response(db, job, preset_id, tracks, min_length, prefers_3d)  # type: ignore[arg-type]


@pytest.mark.anyio
@pytest.mark.parametrize("tool", [None, TranscodeTool.NONE])
async def test_an_archiving_job_keeps_the_3d_title_and_only_it(monkeypatch: pytest.MonkeyPatch, tool: Any) -> None:
    answer = await _answer(monkeypatch, tool)
    assert answer.keep_3d_refs == ["00101.mpls"]
    assert {t.source_ref: t.stereo_3d for t in answer.tracks} == {"00100.mpls": False, "00101.mpls": True}


@pytest.mark.anyio
async def test_a_transcoding_job_keeps_no_3d_but_still_marks_the_3d_track(monkeypatch: pytest.MonkeyPatch) -> None:
    answer = await _answer(monkeypatch, TranscodeTool.HANDBRAKE)
    assert answer.keep_3d_refs == []
    assert {t.source_ref: t.stereo_3d for t in answer.tracks} == {"00100.mpls": False, "00101.mpls": True}
