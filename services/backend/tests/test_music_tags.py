"""`music_tags_for`: the tags a music track's encoded file carries, from the job's stored identity."""

from typing import Any

from arm_backend.transcode_apply import music_tags_for
from arm_common import DiscType, Job, JobStatus, MediaType, Track, TrackKind
from arm_common.schemas import MusicTags

_RELEASE = "b84ee12a-09ef-421b-82de-0441a926375b"


def _cd_job(metadata: dict[str, Any] | None = None, **kw: Any) -> Job:
    return Job(
        id="job_01JZXR7K3M5Q8N4VWA00000002",
        drive_id="drv_x",
        disc_type=DiscType.CD,
        status=JobStatus.RIPPED,
        metadata_json=metadata if metadata is not None else {},
        **kw,
    )


def _audio_track(index: int) -> Track:
    return Track(
        id=f"trk_{index}",
        job_id="job_01JZXR7K3M5Q8N4VWA00000002",
        kind=TrackKind.AUDIO_TRACK,
        index=index,
        source_ref=str(index),
    )


def _identified_metadata() -> dict[str, Any]:
    return {
        "identity": {"provider": "musicbrainz", "external_ids": {"musicbrainz_release": _RELEASE}},
        "music": {
            "artist": "Radiohead",
            "album": "OK Computer",
            "tracks": [
                {"title": "Airbag", "position": 1, "disc_number": 1},
                {"title": "Paranoid Android", "position": 2, "disc_number": 1},
                {"title": "Subterranean Homesick Alien", "position": 3, "disc_number": 1},
            ],
        },
    }


def test_identified_cd_track_gets_every_tag() -> None:
    job = _cd_job(_identified_metadata(), title="OK Computer", year=1997, disc_number=1, media_type=MediaType.MUSIC)

    assert music_tags_for(job, _audio_track(2)) == MusicTags(
        artist="Radiohead",
        album="OK Computer",
        title="Paranoid Android",
        year=1997,
        disc_number=1,
        track_number=2,
        track_total=3,
        musicbrainz_release_id=_RELEASE,
    )


def test_unidentified_cd_track_gets_only_its_track_number() -> None:
    # An audio CD is music whether or not MusicBrainz knew it; nothing else is known.
    assert music_tags_for(_cd_job(), _audio_track(4)) == MusicTags(track_number=4)


def test_track_past_the_listing_has_no_title() -> None:
    tags = music_tags_for(_cd_job(_identified_metadata()), _audio_track(9))

    assert tags is not None
    assert tags.title is None
    assert tags.track_number == 9
    assert tags.track_total == 3


def test_disc_number_falls_back_to_the_track_listing() -> None:
    md = _identified_metadata()
    md["music"]["tracks"][0]["disc_number"] = 2

    tags = music_tags_for(_cd_job(md), _audio_track(1))

    assert tags is not None
    assert tags.disc_number == 2


def test_job_disc_number_wins_over_the_track_listing() -> None:
    md = _identified_metadata()
    md["music"]["tracks"][0]["disc_number"] = 2

    tags = music_tags_for(_cd_job(md, disc_number=3), _audio_track(1))

    assert tags is not None
    assert tags.disc_number == 3


def test_pre_0032_top_level_keys_still_tag() -> None:
    # The same fallback the output filename uses.
    md = {"artist": "Björk", "album": "Homogenic", "tracks": [{"title": "Hunter"}]}

    tags = music_tags_for(_cd_job(md), _audio_track(1))

    assert tags == MusicTags(artist="Björk", album="Homogenic", title="Hunter", track_number=1, track_total=1)


def test_malformed_identity_section_drops_only_the_release_id() -> None:
    md = _identified_metadata()
    md["identity"] = "not a dict"

    tags = music_tags_for(_cd_job(md), _audio_track(1))

    assert tags is not None
    assert tags.musicbrainz_release_id is None
    assert tags.artist == "Radiohead"


def test_video_job_gets_no_tags() -> None:
    job = Job(
        id="job_01JZXR7K3M5Q8N4VWA00000001",
        drive_id="drv_x",
        disc_type=DiscType.DVD,
        title="Iron Man",
        year=2008,
        status=JobStatus.RIPPED,
        metadata_json={},
    )

    assert music_tags_for(job, _audio_track(1)) is None


def test_job_identified_as_music_on_a_non_cd_disc_gets_tags() -> None:
    job = Job(
        id="job_01JZXR7K3M5Q8N4VWA00000003",
        drive_id="drv_x",
        disc_type=DiscType.DATA,
        media_type=MediaType.MUSIC,
        status=JobStatus.RIPPED,
        metadata_json=_identified_metadata(),
    )

    tags = music_tags_for(job, _audio_track(1))

    assert tags is not None
    assert tags.title == "Airbag"
