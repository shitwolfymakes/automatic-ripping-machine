"""Claim storage on Job.metadata_json and the manual / preset recorders."""

from datetime import datetime, timezone

from arm_common import DiscType, Job, JobStatus, Track, TrackKind
from arm_common.schemas.identity import JobClaim, SourceClaims, TrackClaim

from arm_backend.identity.resolver import apply_resolution, resolve
from arm_backend.identity.proposals import (
    claims_of,
    clear_pin,
    put_source,
    record_manual_job,
    record_manual_track,
    record_preset,
    revert_manual_track,
    set_pin,
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


def test_put_source_error_keeps_last_good() -> None:
    job = _job()
    put_source(job, "thediscdb", SourceClaims(tracks={"1": TrackClaim(episode=3)}))
    put_source(job, "thediscdb", SourceClaims(run_at=NOW, status="error", detail="TimeoutError: boom"))
    entry = claims_of(job).sources["thediscdb"]
    assert entry.status == "ok" and entry.tracks["1"].episode == 3
    assert entry.extra["last_error"]["detail"] == "TimeoutError: boom"


def test_put_source_error_with_equal_inputs_keeps_last_good() -> None:
    job = _job()
    put_source(
        job,
        "label",
        SourceClaims(status="ok", inputs={"volume_label": "LOST_S2D3"}, tracks={"1": TrackClaim(episode=3)}),
    )
    put_source(job, "label", SourceClaims(status="error", inputs={"volume_label": "LOST_S2D3"}, detail="boom"))
    entry = claims_of(job).sources["label"]
    assert entry.status == "ok" and entry.tracks["1"].episode == 3
    assert entry.extra["last_error"]["detail"] == "boom"


def test_put_source_error_with_different_inputs_replaces() -> None:
    # The kept claims would describe a different disc input: store the error, claims cleared.
    job = _job()
    put_source(
        job,
        "label",
        SourceClaims(status="ok", inputs={"volume_label": "LOST_S2D3"}, tracks={"1": TrackClaim(episode=3)}),
    )
    put_source(job, "label", SourceClaims(status="error", inputs={"volume_label": "LOST_S2D4"}, detail="boom"))
    entry = claims_of(job).sources["label"]
    assert entry.status == "error" and entry.tracks == {}
    assert entry.inputs == {"volume_label": "LOST_S2D4"}


def test_put_source_error_after_skipped_replaces() -> None:
    job = _job()
    put_source(job, "bd_title", SourceClaims(status="skipped", detail="no BDMT disc title"))
    put_source(job, "bd_title", SourceClaims(status="error", detail="boom"))
    entry = claims_of(job).sources["bd_title"]
    assert entry.status == "error" and entry.detail == "boom"


def test_put_source_error_without_prior_ok_is_stored() -> None:
    job = _job()
    put_source(job, "thediscdb", SourceClaims(status="error", detail="x"))
    assert claims_of(job).sources["thediscdb"].status == "error"


def test_put_source_skipped_replaces_ok() -> None:
    job = _job()
    put_source(job, "thediscdb", SourceClaims(tracks={"1": TrackClaim(episode=3)}))
    put_source(job, "thediscdb", SourceClaims(status="skipped", detail="no key"))
    assert claims_of(job).sources["thediscdb"].status == "skipped"


def test_record_manual_track_maps_attributes_and_merges() -> None:
    job, track = _job(), _track("1")
    track.custom_filename = "old.mkv"
    assert record_manual_track(job, track, {"episode_number": 4, "custom_filename": None}) is True
    assert record_manual_track(job, track, {"excluded": True}) is True
    claim = claims_of(job).sources["manual"].tracks["1"]
    assert claim.model_fields_set == {"episode", "filename", "selected"}
    assert claim.episode == 4
    assert claim.filename is None
    assert claim.selected is False  # excluded=True -> selected=False


def test_record_manual_track_skips_restated_automatic_value() -> None:
    """The UI re-sends unchanged values; restating what a source (or nothing)
    already set must not become a sticky manual claim."""
    job, track = _job(), _track("1", excluded=True)
    track.episode_name = "Pilot"
    track.identity_provenance = {"episode_name": "thediscdb"}
    edits = {"episode_name": "Pilot", "custom_filename": None, "excluded": True}
    assert record_manual_track(job, track, edits) is False
    assert job.metadata_json == {}


def test_record_manual_track_restated_manual_value_records() -> None:
    job, track = _job(), _track("1")
    track.episode_name = "Mine"
    track.identity_provenance = {"episode_name": "manual"}
    assert record_manual_track(job, track, {"episode_name": "Mine"}) is True
    assert claims_of(job).sources["manual"].tracks["1"].episode_name == "Mine"


def test_record_manual_track_clearing_a_set_value_records_null() -> None:
    job, track = _job(), _track("1")
    track.title = "Auto"
    track.identity_provenance = {"title": "thediscdb"}
    assert record_manual_track(job, track, {"title": None}) is True
    claim = claims_of(job).sources["manual"].tracks["1"]
    assert claim.model_fields_set == {"title"}
    assert claim.title is None


def test_revert_manual_track_removes_only_named_fields() -> None:
    job = _job()
    record_manual_track(job, _track("1"), {"episode_number": 4, "episode_name": "X"})
    revert_manual_track(job, "1", ["episode_number"])
    claim = claims_of(job).sources["manual"].tracks["1"]
    assert claim.model_fields_set == {"episode_name"}


def test_revert_last_field_drops_track_entry() -> None:
    job = _job()
    record_manual_track(job, _track("1"), {"episode_number": 4})
    revert_manual_track(job, "1", ["episode_number"])
    assert "1" not in claims_of(job).sources["manual"].tracks


def test_revert_on_job_without_manual_claims_is_noop() -> None:
    job = _job()
    revert_manual_track(job, "1", ["title"])
    assert claims_of(job).sources == {}


def test_record_manual_job() -> None:
    job = _job()
    job.disc_number = 1
    assert record_manual_job(job, {"season": 2, "disc_number": None}) is True
    claim = claims_of(job).sources["manual"].job
    assert claim.model_fields_set == {"season"}


def test_record_manual_job_skips_restated_values_unless_manual() -> None:
    job = _job()
    job.season = 2
    assert record_manual_job(job, {"season": 2, "disc_number": None, "disc_total": None}) is False
    assert job.metadata_json == {}
    job.identity_provenance = {"season": "manual"}
    assert record_manual_job(job, {"season": 2, "disc_number": None}) is True
    assert claims_of(job).sources["manual"].job.model_fields_set == {"season"}


def test_record_preset_merges_by_source_ref() -> None:
    job = _job()
    record_preset(job, [_track("1"), _track("2", excluded=True)], now=NOW)
    record_preset(job, [_track("3")], now=NOW)
    tracks = claims_of(job).sources["preset"].tracks
    assert {k: v.selected for k, v in tracks.items()} == {"1": True, "2": False, "3": True}


def test_set_pin_and_clear_pin() -> None:
    job = _job()
    set_pin(job, "episode", "episodes_tmdb")
    assert claims_of(job).pin == {"episode": "episodes_tmdb"}
    clear_pin(job, "episode")
    assert claims_of(job).pin == {}


def test_clear_pin_noop_when_nothing_pinned() -> None:
    job = _job()
    clear_pin(job, "episode")
    assert claims_of(job).pin == {}


TIERS = {"manual": 1, "label": 4}


def test_clearing_a_manual_field_removes_the_claim() -> None:
    job = _job()
    put_source(job, "label", SourceClaims(run_at=NOW, status="ok", job=JobClaim(season=3)))
    record_manual_job(job, {"season": 7})
    assert claims_of(job).sources["manual"].job.season == 7
    assert record_manual_job(job, {"season": None}) is True
    assert "season" not in claims_of(job).sources["manual"].job.model_fields_set
    res = resolve(claims_of(job), tiers=TIERS)
    assert res.job["season"].value == 3 and res.job["season"].source == "label"


def test_clearing_with_no_other_proposer_empties_the_field_and_keeps_track_seasons() -> None:
    job = _job()
    track = _track("1")
    track.season = 7
    record_manual_job(job, {"season": 7})
    apply_resolution(job, [track], resolve(claims_of(job), tiers=TIERS))
    assert job.season == 7
    record_manual_job(job, {"season": None})
    apply_resolution(job, [track], resolve(claims_of(job), tiers=TIERS))
    assert job.season is None and "season" not in (job.identity_provenance or {})
    assert track.season == 7


def test_clearing_a_field_the_claim_never_held_changes_nothing() -> None:
    job = _job()
    record_manual_job(job, {"season": 7})
    assert record_manual_job(job, {"disc_number": None}) is False


def test_clearing_a_legacy_value_without_an_owner_empties_it() -> None:
    job = _job()
    job.season = 5
    assert record_manual_job(job, {"season": None}) is True
    assert job.season is None
    apply_resolution(job, [], resolve(claims_of(job), tiers=TIERS))
    assert job.season is None


def test_clearing_an_owned_value_leaves_the_write_to_the_resolver() -> None:
    job = _job()
    put_source(job, "label", SourceClaims(run_at=NOW, status="ok", job=JobClaim(season=3)))
    record_manual_job(job, {"season": 7})
    apply_resolution(job, [], resolve(claims_of(job), tiers=TIERS))
    assert job.season == 7 and job.identity_provenance == {"season": "manual"}
    assert record_manual_job(job, {"season": None}) is True
    assert job.season == 7  # the resolver, not the recorder, rewrites an owned field
    apply_resolution(job, [], resolve(claims_of(job), tiers=TIERS))
    assert job.season == 3 and job.identity_provenance == {"season": "label"}
