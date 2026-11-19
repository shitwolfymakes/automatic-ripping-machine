"""track_label: a track's 1-based position among the job's tracks and the title the job's metadata gives it."""

from __future__ import annotations

from arm_backend.track_labels import TrackLabel, track_label, track_position
from arm_common import DiscType, Job, JobStatus, Track, TrackKind, TrackStatus


def _job(meta: dict | None = None) -> Job:
    return Job(id="job_1", drive_id="drv_x", disc_type=DiscType.CD, status=JobStatus.RIPPING, metadata_json=meta or {})


def _track(index: int, **kw: object) -> Track:
    return Track(
        id=f"t{index}",
        job_id="job_1",
        kind=TrackKind.VIDEO_TITLE,
        index=index,
        source_ref=str(index),
        status=TrackStatus.QUEUED,
        attempts=0,
        **kw,  # type: ignore[arg-type]
    )


def test_music_title_comes_from_the_music_track_list() -> None:
    meta = {"music": {"tracks": [{"title": "Don't Bring Me Down"}, {"title": "Xanadu"}]}}
    tracks = [_track(i) for i in range(1, 20)]
    assert track_label(_job(meta), tracks[0], tracks) == TrackLabel(1, 19, "Don't Bring Me Down")
    assert track_label(_job(meta), tracks[1], tracks).title == "Xanadu"


def test_music_track_past_the_list_has_no_title() -> None:
    tracks = [_track(1), _track(2)]
    assert track_label(_job({"music": {"tracks": [{"title": "A"}]}}), tracks[1], tracks).title is None


def test_music_entry_without_a_string_title_has_no_title() -> None:
    tracks = [_track(1)]
    assert track_label(_job({"music": {"tracks": [{"title": 5}, "x"]}}), tracks[0], tracks).title is None
    assert track_label(_job({"music": {"tracks": ["x"]}}), tracks[0], tracks).title is None


def test_malformed_music_section_is_ignored() -> None:
    tracks = [_track(1)]
    assert track_label(_job({"music": "nope"}), tracks[0], tracks).title is None
    assert track_label(_job({"music": {"tracks": "nope"}}), tracks[0], tracks).title is None


def test_episode_name_is_the_title() -> None:
    tracks = [_track(1, episode_name="Pilot", label="Title 1")]
    assert track_label(_job(), tracks[0], tracks) == TrackLabel(1, 1, "Pilot")


def test_label_is_the_fallback_title() -> None:
    tracks = [_track(1, label="Main Feature")]
    assert track_label(_job(), tracks[0], tracks).title == "Main Feature"


def test_unidentified_track_has_no_title() -> None:
    tracks = [_track(1)]
    assert track_label(_job(), tracks[0], tracks).title is None


def test_position_ranks_the_index_among_sparse_indexes_and_total_counts_every_track() -> None:
    tracks = [_track(0), _track(3, excluded=True), _track(5)]
    assert track_label(_job(), tracks[2], tracks) == TrackLabel(3, 3, None)
    assert track_label(_job(), tracks[0], tracks).index == 1


def test_unidentified_job_with_a_label_has_no_title() -> None:
    tracks = [_track(1, label="Title 1", episode_name="x")]
    job = _job({"flags": {"unidentified": True}, "music": {"tracks": [{"title": "A"}]}})
    assert track_label(job, tracks[0], tracks).title is None


def test_track_position_names_the_index_among_the_total() -> None:
    assert track_position(TrackLabel(3, 19, "Telephone Line")) == "track 3/19"
