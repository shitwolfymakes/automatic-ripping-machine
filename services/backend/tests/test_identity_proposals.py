"""Claim storage on Job.metadata_json and the manual / preset recorders."""

from datetime import datetime, timezone

from arm_common import DiscType, Job, JobStatus, Track, TrackKind
from arm_common.schemas.identity import SourceClaims, TrackClaim

from arm_backend.identity.proposals import (
    claims_of,
    put_source,
    record_manual_job,
    record_manual_track,
    record_preset,
    revert_manual_track,
)

NOW = datetime(2026, 9, 28, tzinfo=timezone.utc)


def _job(meta: dict | None = None) -> Job:
    return Job(
        id="job_1",
        drive_id="drv_1",
        disc_type=DiscType.BLURAY,
        status=JobStatus.IDENTIFIED,
        metadata_json=meta or {},
    )


def _track(ref: str, excluded: bool = False) -> Track:
    return Track(
        id=f"trk_{ref}", job_id="job_1", kind=TrackKind.VIDEO_TITLE, index=int(ref), source_ref=ref, excluded=excluded
    )


def test_claims_of_empty_job() -> None:
    assert claims_of(_job()).sources == {}


def test_claims_of_corrupt_section_is_empty_not_raising(caplog) -> None:
    job = _job({"identity_claims": {"sources": "garbage"}})
    assert claims_of(job).sources == {}
    assert "identity_claims invalid" in caplog.text


def test_put_source_preserves_other_metadata_and_reassigns_dict() -> None:
    job = _job({"scan_result": {"x": 1}})
    before = job.metadata_json
    put_source(job, "thediscdb", SourceClaims(tracks={"1": TrackClaim(episode=3)}))
    assert job.metadata_json is not before  # SQLAlchemy JSON change detection needs a new object
    assert job.metadata_json["scan_result"] == {"x": 1}
    assert job.metadata_json["identity_claims"]["sources"]["thediscdb"]["tracks"]["1"] == {"episode": 3}


def test_record_manual_track_maps_attributes_and_merges() -> None:
    job = _job()
    record_manual_track(job, "1", {"episode_number": 4, "custom_filename": None})
    record_manual_track(job, "1", {"excluded": True})
    claim = claims_of(job).sources["manual"].tracks["1"]
    assert claim.model_fields_set == {"episode", "filename", "selected"}
    assert claim.episode == 4
    assert claim.filename is None
    assert claim.selected is False  # excluded=True -> selected=False


def test_revert_manual_track_removes_only_named_fields() -> None:
    job = _job()
    record_manual_track(job, "1", {"episode_number": 4, "episode_name": "X"})
    revert_manual_track(job, "1", ["episode_number"])
    claim = claims_of(job).sources["manual"].tracks["1"]
    assert claim.model_fields_set == {"episode_name"}


def test_revert_last_field_drops_track_entry() -> None:
    job = _job()
    record_manual_track(job, "1", {"episode_number": 4})
    revert_manual_track(job, "1", ["episode_number"])
    assert "1" not in claims_of(job).sources["manual"].tracks


def test_revert_on_job_without_manual_claims_is_noop() -> None:
    job = _job()
    revert_manual_track(job, "1", ["title"])
    assert claims_of(job).sources == {}


def test_record_manual_job() -> None:
    job = _job()
    record_manual_job(job, {"season": 2, "disc_number": None})
    claim = claims_of(job).sources["manual"].job
    assert claim.model_fields_set == {"season", "disc_number"}


def test_record_preset_merges_by_source_ref() -> None:
    job = _job()
    record_preset(job, [_track("1"), _track("2", excluded=True)], now=NOW)
    record_preset(job, [_track("3")], now=NOW)
    tracks = claims_of(job).sources["preset"].tracks
    assert {k: v.selected for k, v in tracks.items()} == {"1": True, "2": False, "3": True}
