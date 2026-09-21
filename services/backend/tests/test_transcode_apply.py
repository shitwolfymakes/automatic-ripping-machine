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


# ── helpers for per-track identity / episode / excluded / custom_filename tests ──


def _tv_session(template: str) -> Session:
    return Session(
        id="ses_tv2",
        name="TV 1080p",
        media_type=MediaType.TV,
        rip_preset_id="rpr_x",
        transcode_preset_id="tpr_x",
        output_path_template=template,
    )


def _tv_preset() -> TranscodePreset:
    tp = _movie_preset()
    tp.media_type = MediaType.TV
    tp.name = "TV 1080p H.265"
    return tp


def _tv_job(title: str = "My Show", year: int = 2020) -> Job:
    return Job(
        id="job_01JZXR7K3M5Q8N4VWA0000000T",
        drive_id="drv_x",
        disc_type=DiscType.DVD,
        title=title,
        year=year,
        status=JobStatus.RIPPED,
        metadata_json={"season": "01", "disc": "01"},
    )


def _tv_track(
    idx: int,
    *,
    episode_number: int | None = None,
    episode_name: str | None = None,
    title: str | None = None,
    excluded: bool = False,
    custom_filename: str | None = None,
) -> Track:
    return Track(
        id=f"trk_{idx}",
        job_id="job_01JZXR7K3M5Q8N4VWA0000000T",
        kind=TrackKind.VIDEO_TITLE,
        index=idx,
        source_ref=str(idx),
        episode_number=episode_number,
        episode_name=episode_name,
        title=title,
        excluded=excluded,
        custom_filename=custom_filename,
    )


# ── 1. excluded skips transcode ──


def test_excluded_track_skipped() -> None:
    job = _tv_job()
    sess = _tv_session("{show} ({year})/S01E{track} - {transcode_slug}.{ext}")
    tp = _tv_preset()
    tracks = [_tv_track(1), _tv_track(2, excluded=True)]
    resolved = compute_outputs(job, tracks, sess, tp)
    assert len(resolved) == 1
    assert resolved[0].track_id == "trk_1"


# ── 2. per-track title overrides job ──


def test_per_track_title_overrides_job() -> None:
    job = _job()  # title="Iron Man"
    sess = _movie_session("{title} ({year})/{title}.{ext}")
    tp = _movie_preset()
    track = Track(
        id="trk_1",
        job_id="job_01JZXR7K3M5Q8N4VWA00000001",
        kind=TrackKind.VIDEO_TITLE,
        index=1,
        source_ref="1",
        title="Episode A",
    )
    resolved = compute_outputs(job, [track], sess, tp)
    assert "Episode A" in resolved[0].output_path
    assert "Iron Man" not in resolved[0].output_path


# ── 3. null title inherits job ──


def test_null_track_title_inherits_job() -> None:
    job = _job()  # title="Iron Man"
    sess = _movie_session("{title} ({year})/{title}.{ext}")
    tp = _movie_preset()
    track = Track(
        id="trk_1",
        job_id="job_01JZXR7K3M5Q8N4VWA00000001",
        kind=TrackKind.VIDEO_TITLE,
        index=1,
        source_ref="1",
        title=None,
    )
    resolved = compute_outputs(job, [track], sess, tp)
    assert "Iron Man" in resolved[0].output_path


# ── 4. episode tokens render per-track ──


def test_episode_tokens_render_per_track() -> None:
    job = _tv_job()
    sess = _tv_session(
        "{show} ({year})/Season {season}/{show} S01E{episode} - {episode_title} - {transcode_slug}.{ext}"
    )
    tp = _tv_preset()
    tracks = [
        _tv_track(1, episode_number=1, episode_name="Pilot"),
        _tv_track(2, episode_number=2, episode_name="Part Two"),
    ]
    resolved = compute_outputs(job, tracks, sess, tp)
    assert len(resolved) == 2
    assert "01" in resolved[0].output_path and "Pilot" in resolved[0].output_path
    assert "02" in resolved[1].output_path and "Part Two" in resolved[1].output_path
    assert resolved[0].output_path != resolved[1].output_path


# ── 5. unedited episode (episode_number=None) fails loudly ──


def test_unedited_episode_token_raises() -> None:
    job = _tv_job()
    sess = _tv_session("{show} ({year})/S01E{episode} - {transcode_slug}.{ext}")
    tp = _tv_preset()
    # episode_number is None → episode token resolves to "" → TemplateValidationError
    tracks = [_tv_track(1, episode_number=None)]
    with pytest.raises(TemplateValidationError, match="resolved empty"):
        compute_outputs(job, tracks, sess, tp)


# ── 6. custom_filename overrides rendered name, preserves directory ──


def test_custom_filename_overrides_name_keeps_dir() -> None:
    job = _tv_job()
    sess = _tv_session("{show} ({year})/Season {season}/{show} S01E{track} - {transcode_slug}.{ext}")
    tp = _tv_preset()
    track = _tv_track(1, custom_filename="S01E01")
    resolved = compute_outputs(job, [track], sess, tp)
    path = resolved[0].output_path
    # Filename should be "S01E01.mkv"; directory should be template-rendered
    assert path.endswith("S01E01.mkv")
    assert "My Show (2020)/Season 01" in path


def test_custom_filename_already_has_correct_ext_no_double() -> None:
    # custom_filename already carries the right extension — must not double it
    job = _tv_job()
    sess = _tv_session("{show} ({year})/Season {season}/{show} S01E{track} - {transcode_slug}.{ext}")
    tp = _tv_preset()
    track = _tv_track(1, custom_filename="S01E01.mkv")
    resolved = compute_outputs(job, [track], sess, tp)
    path = resolved[0].output_path
    assert path.endswith("S01E01.mkv")
    assert not path.endswith(".mkv.mkv")


def test_custom_filename_different_ext_stripped_and_resolved_ext_appended() -> None:
    # custom_filename carries a different extension — strip it, append the resolved one
    job = _tv_job()
    sess = _tv_session("{show} ({year})/Season {season}/{show} S01E{track} - {transcode_slug}.{ext}")
    tp = _tv_preset()
    track = _tv_track(1, custom_filename="S01E01.avi")
    resolved = compute_outputs(job, [track], sess, tp)
    path = resolved[0].output_path
    assert path.endswith("S01E01.mkv")
    assert not path.endswith(".avi.mkv")
