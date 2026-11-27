"""A CD not yet identified counts as identified once it has an album and an
artist; its tracks may stay untitled."""

from typing import Any

import pytest
from arm_common.enums import DiscType, JobStatus
from arm_common.schemas.job_metadata import JobMetadata
from arm_common.schemas.jobs import CdIdentityGaps, JobView, pending_cd_identity


def _md(music: dict[str, Any] | None = None, **extra: Any) -> JobMetadata:
    return JobMetadata.model_validate({"music": music, **extra})


def test_album_and_artist_are_enough_with_tracks_untitled() -> None:
    music = {"artist": "Lali", "album": "Two Windows", "tracks": [{"title": ""}]}
    assert pending_cd_identity(DiscType.CD, JobStatus.AWAITING_USER_ID, _md(music)) is None


def test_a_cd_with_no_music_lacks_both() -> None:
    assert pending_cd_identity(DiscType.CD, JobStatus.AWAITING_USER_ID, _md()) == CdIdentityGaps(
        album=True, artist=True
    )


def test_a_blank_album_or_artist_counts_as_missing() -> None:
    gaps = pending_cd_identity(DiscType.CD, JobStatus.RIPPED_AWAITING_IDENTIFY, _md({"artist": " ", "album": "X"}))
    assert gaps == CdIdentityGaps(album=False, artist=True)


@pytest.mark.parametrize("status", [JobStatus.RIPPED_PARTIAL, JobStatus.IDENTIFIED, JobStatus.AWAITING_REVIEW])
def test_a_flagged_unidentified_cd_is_pending(status: JobStatus) -> None:
    assert pending_cd_identity(DiscType.CD, status, _md(flags={"unidentified": True})) is not None


@pytest.mark.parametrize("status", [JobStatus.IDENTIFIED, JobStatus.RIPPED, JobStatus.RIPPED_PARTIAL])
def test_an_identified_cd_is_never_pending(status: JobStatus) -> None:
    assert pending_cd_identity(DiscType.CD, status, _md()) is None


def test_a_video_disc_is_never_pending() -> None:
    assert pending_cd_identity(DiscType.BLURAY, JobStatus.AWAITING_USER_ID, _md()) is None


def _view(status: str, metadata: dict[str, Any]) -> JobView:
    return JobView.model_validate(
        {
            "id": "job_1",
            "drive_id": None,
            "disc_type": "cd",
            "status": status,
            "title": None,
            "year": None,
            "metadata_json": metadata,
            "resumed_from_crash": False,
        }
    )


def test_job_view_reports_what_a_cd_still_lacks() -> None:
    view = _view("awaiting_user_id", {"music": {"album": "Two Windows"}})
    assert view.model_dump()["cd_identity_gaps"] == {"album": False, "artist": True}


def test_job_view_reports_no_gaps_for_an_identified_cd() -> None:
    assert _view("ripped", {}).cd_identity_gaps is None
