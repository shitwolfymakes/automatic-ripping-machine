import os

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.path_template import TemplateValidationError  # noqa: E402
from arm_backend.transcode_apply import compute_outputs  # noqa: E402
from arm_common import (  # noqa: E402
    ContainerFormat,
    DiscType,
    HwPreference,
    Job,
    JobStatus,
    MediaType,
    Session,
    Track,
    TrackKind,
    TranscodePreset,
    TranscodeTool,
)


def _movie_session(template: str) -> Session:
    return Session(
        id="ses_x",
        name="My Plex 1080p",
        media_type=MediaType.MOVIE,
        rip_preset_id="rpr_x",
        transcode_preset_id="tpr_x",
        output_path_template=template,
    )


def _movie_preset() -> TranscodePreset:
    return TranscodePreset(
        id="tpr_x",
        name="Plex 1080p H.265",
        media_type=MediaType.MOVIE,
        tool=TranscodeTool.HANDBRAKE,
        container=ContainerFormat.MKV,
        hw_preference=HwPreference.CPU_ONLY,
    )


def _job(title: str | None = "Iron Man", year: int | None = 2008, status: JobStatus = JobStatus.RIPPED) -> Job:
    return Job(
        id="job_01JZXR7K3M5Q8N4VWA00000001",
        drive_id="drv_x",
        disc_type=DiscType.DVD,
        title=title,
        year=year,
        status=status,
    )


def _video_track(idx: int, duration: int = 8000) -> Track:
    return Track(
        id=f"trk_{idx}",
        job_id="job_01JZXR7K3M5Q8N4VWA00000001",
        kind=TrackKind.VIDEO_TITLE,
        index=idx,
        source_ref=str(idx),
        expected_duration_seconds=duration,
    )


def test_compute_outputs_movie_happy_path() -> None:
    job = _job()
    sess = _movie_session("{title} ({year})/{title} ({year}) - {transcode_slug}.{ext}")
    tp = _movie_preset()
    resolved = compute_outputs(job, [_video_track(1)], sess, tp)
    assert len(resolved) == 1
    assert resolved[0].track_id == "trk_1"
    assert resolved[0].output_path == "Iron Man (2008)/Iron Man (2008) - plex-1080p-h-265.mkv"


def test_compute_outputs_skips_non_relevant_track_kinds() -> None:
    job = _job()
    sess = _movie_session("{title} ({year})/{title} - {transcode_slug}.{ext}")
    tp = _movie_preset()
    audio = Track(
        id="trk_a", job_id="job_01JZXR7K3M5Q8N4VWA00000001", kind=TrackKind.AUDIO_TRACK, index=2, source_ref="2"
    )
    resolved = compute_outputs(job, [_video_track(1), audio], sess, tp)
    assert len(resolved) == 1
    assert resolved[0].track_id == "trk_1"


def test_compute_outputs_empty_token_raises() -> None:
    job = _job(title=None, year=None)
    sess = _movie_session("{title} ({year})/{title} - {transcode_slug}.{ext}")
    tp = _movie_preset()
    with pytest.raises(TemplateValidationError, match="resolved empty"):
        compute_outputs(job, [_video_track(1)], sess, tp)


def test_compute_outputs_iso_no_transcode_preset() -> None:
    job = _job()
    sess = Session(
        id="ses_iso",
        name="ISO dump",
        media_type=MediaType.ISO,
        rip_preset_id="rpr_iso",
        transcode_preset_id=None,
        output_path_template="{title} ({year})/{title} ({year}).{ext}",
    )
    track = Track(
        id="trk_iso", job_id="job_01JZXR7K3M5Q8N4VWA00000001", kind=TrackKind.VIDEO_TITLE, index=1, source_ref="full"
    )
    # ISO ext is fixed by media_type, not by a transcode preset — but our context
    # populates `ext` from transcode_preset.container. So an ISO session with no
    # preset *will* fail on `{ext}` at apply time. The seeder template uses a
    # literal `.iso` extension instead, which is the right pattern; verify that.
    sess.output_path_template = "{title} ({year})/{title} ({year}).iso"
    resolved = compute_outputs(job, [track], sess, None)
    assert len(resolved) == 1
    assert resolved[0].output_path == "Iron Man (2008)/Iron Man (2008).iso"


def test_compute_outputs_archive_multiple_tracks() -> None:
    job = _job()
    sess = _movie_session(
        "{title} ({year})/{title} ({year}) - Track {track} ({duration_human}) - {transcode_slug}.{ext}"
    )
    tp = _movie_preset()
    tracks = [_video_track(1, 7800), _video_track(2, 1200), _video_track(3, 600)]
    resolved = compute_outputs(job, tracks, sess, tp)
    paths = [r.output_path for r in resolved]
    assert paths[0] == "Iron Man (2008)/Iron Man (2008) - Track 01 (02h10m) - plex-1080p-h-265.mkv"
    assert paths[1] == "Iron Man (2008)/Iron Man (2008) - Track 02 (00h20m) - plex-1080p-h-265.mkv"
    assert paths[2] == "Iron Man (2008)/Iron Man (2008) - Track 03 (00h10m) - plex-1080p-h-265.mkv"


def test_compute_outputs_tv_with_metadata_season_disc() -> None:
    job = Job(
        id="job_01JZXR7K3M5Q8N4VWA0000000E",
        drive_id="drv_x",
        disc_type=DiscType.DVD,
        title="Battlestar Galactica",
        year=2004,
        status=JobStatus.RIPPED,
        metadata_json={"season": "01", "disc": "02"},
    )
    sess = Session(
        id="ses_tv",
        name="Plex TV 1080p H.265",
        media_type=MediaType.TV,
        rip_preset_id="rpr_x",
        transcode_preset_id="tpr_x",
        output_path_template="{show} ({year})/Season {season}/S{season}D{disc}T{track} - {transcode_slug}.{ext}",
    )
    tp = _movie_preset()
    tp.media_type = MediaType.TV
    tp.name = "Plex TV 1080p H.265"
    track = Track(
        id="trk_1",
        job_id="job_01JZXR7K3M5Q8N4VWA0000000E",
        kind=TrackKind.VIDEO_TITLE,
        index=1,
        source_ref="1",
        expected_duration_seconds=2700,
    )
    resolved = compute_outputs(job, [track], sess, tp)
    assert resolved[0].output_path == ("Battlestar Galactica (2004)/Season 01/S01D02T01 - plex-tv-1080p-h-265.mkv")
