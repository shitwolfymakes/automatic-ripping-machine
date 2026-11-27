"""A CD not yet identified counts as identified only once its identity is
complete: album, artist and a title for every scanned track."""

from typing import Any

import pytest
from arm_common.enums import DiscType, JobStatus
from arm_common.schemas.job_metadata import JobMetadata
from arm_common.schemas.jobs import CdIdentityGaps, JobView, pending_cd_identity

SCAN = {"disc_type": "cd", "titles": [{"index": 1, "duration_seconds": 60}, {"index": 2, "duration_seconds": 61}]}
FULL = {"artist": "Lali", "album": "Two Windows", "tracks": [{"title": "A"}, {"title": "B"}]}


def _md(music: dict[str, Any] | None = None, scan: dict[str, Any] | None = SCAN, **extra: Any) -> JobMetadata:
    return JobMetadata.model_validate({"scan_result": scan, "music": music, **extra})


def test_a_complete_cd_has_no_gaps() -> None:
    assert pending_cd_identity(DiscType.CD, JobStatus.AWAITING_USER_ID, _md(FULL)) is None


def test_a_cd_with_no_music_lacks_everything() -> None:
    assert pending_cd_identity(DiscType.CD, JobStatus.AWAITING_USER_ID, _md()) == CdIdentityGaps(
        album=True, artist=True, untitled_tracks=[1, 2]
    )


def test_blank_album_artist_and_titles_count_as_missing() -> None:
    music = {"artist": " ", "album": "", "tracks": [{"title": "A"}, {"title": "  "}]}
    assert pending_cd_identity(DiscType.CD, JobStatus.RIPPED_AWAITING_IDENTIFY, _md(music)) == CdIdentityGaps(
        album=True, artist=True, untitled_tracks=[2]
    )


def test_every_scanned_track_needs_a_title_even_past_the_stored_list() -> None:
    music = {**FULL, "tracks": [{"title": "A"}]}
    gaps = pending_cd_identity(DiscType.CD, JobStatus.AWAITING_USER_ID, _md(music))
    assert gaps == CdIdentityGaps(album=False, artist=False, untitled_tracks=[2])


def test_stored_tracks_past_the_scan_are_not_required() -> None:
    music = {**FULL, "tracks": [{"title": "A"}, {"title": "B"}, {"title": ""}]}
    assert pending_cd_identity(DiscType.CD, JobStatus.AWAITING_USER_ID, _md(music)) is None


def test_without_a_scan_every_stored_track_needs_a_title() -> None:
    music = {**FULL, "tracks": [{"title": "A"}, {"title": ""}]}
    gaps = pending_cd_identity(DiscType.CD, JobStatus.AWAITING_USER_ID, _md(music, scan=None))
    assert gaps is not None and gaps.untitled_tracks == [2]


@pytest.mark.parametrize(
    ("status", "flags"),
    [
        (JobStatus.RIPPED_PARTIAL, {"unidentified": True}),
        (JobStatus.IDENTIFIED, {"unidentified": True}),
        (JobStatus.AWAITING_REVIEW, {"unidentified": True}),
    ],
)
def test_a_flagged_unidentified_cd_is_pending(status: JobStatus, flags: dict[str, bool]) -> None:
    assert pending_cd_identity(DiscType.CD, status, _md(flags=flags)) is not None


@pytest.mark.parametrize("status", [JobStatus.IDENTIFIED, JobStatus.RIPPED, JobStatus.RIPPED_PARTIAL])
def test_an_identified_cd_is_never_pending(status: JobStatus) -> None:
    assert pending_cd_identity(DiscType.CD, status, _md()) is None


def test_a_video_disc_is_never_pending() -> None:
    assert pending_cd_identity(DiscType.BLURAY, JobStatus.AWAITING_USER_ID, _md()) is None


def _view(disc_type: str, status: str, metadata: dict[str, Any]) -> JobView:
    return JobView.model_validate(
        {
            "id": "job_1",
            "drive_id": None,
            "disc_type": disc_type,
            "status": status,
            "title": None,
            "year": None,
            "metadata_json": metadata,
            "resumed_from_crash": False,
        }
    )


def test_job_view_reports_what_a_cd_still_lacks() -> None:
    view = _view("cd", "awaiting_user_id", {"scan_result": SCAN, "music": {**FULL, "artist": None}})
    assert view.cd_identity_gaps == CdIdentityGaps(album=False, artist=True, untitled_tracks=[])
    assert view.model_dump()["cd_identity_gaps"] == {"album": False, "artist": True, "untitled_tracks": []}


def test_job_view_reports_no_gaps_for_an_identified_cd() -> None:
    assert _view("cd", "ripped", {"scan_result": SCAN}).cd_identity_gaps is None
