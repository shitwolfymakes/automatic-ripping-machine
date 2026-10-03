"""identity_claims schemas: presence semantics survive a JSON round trip."""

from typing import get_args

from arm_common.enums import TrackRole
from arm_common.schemas import JobMetadata
from arm_common.schemas.jobs import TrackRevertField
from arm_common.schemas.identity import (
    JOB_CLAIM_FIELDS,
    TRACK_CLAIM_FIELDS,
    IdentityClaims,
    SourceClaims,
    TrackClaim,
)
from arm_common.schemas.job_metadata import ExternalIds


def test_track_claim_presence_survives_round_trip() -> None:
    claim = TrackClaim(title=None, episode=5)
    dumped = claim.model_dump(mode="json", exclude_unset=True)
    assert dumped == {"title": None, "episode": 5}
    again = TrackClaim.model_validate(dumped)
    assert again.model_fields_set == {"title", "episode"}


def test_identity_claims_round_trip_through_job_metadata() -> None:
    claims = IdentityClaims(
        sources={"thediscdb": SourceClaims(tracks={"1": TrackClaim(role=TrackRole.MAIN, selected=True)})},
    )
    md = JobMetadata(identity_claims=claims)
    raw = md.model_dump(mode="json", exclude_unset=True)
    assert raw["identity_claims"]["sources"]["thediscdb"]["tracks"]["1"] == {"role": "main", "selected": True}
    back = JobMetadata.model_validate(raw)
    assert back.identity_claims is not None
    assert back.identity_claims.sources["thediscdb"].tracks["1"].role is TrackRole.MAIN


def test_field_maps_cover_resolver_managed_fields() -> None:
    assert set(TRACK_CLAIM_FIELDS.values()) == {
        "role",
        "title",
        "season",
        "episode_number",
        "episode_number_end",
        "episode_name",
        "custom_filename",
        "excluded",
    }
    assert set(JOB_CLAIM_FIELDS.values()) == {"season", "disc_number", "disc_total"}


def test_job_metadata_has_no_thediscdb_section() -> None:
    assert "thediscdb" not in JobMetadata.model_fields


def test_job_metadata_identity_claims_valid_parses_invalid_passes_through() -> None:
    valid = JobMetadata.model_validate({"identity_claims": {"sources": {"manual": {"tracks": {"1": {"title": None}}}}}})
    assert isinstance(valid.identity_claims, IdentityClaims)
    corrupt = {"sources": "garbage", "future_key": 1}
    raw = JobMetadata.model_validate({"identity_claims": corrupt})
    assert raw.identity_claims == corrupt
    assert raw.model_dump(mode="json", exclude_unset=True)["identity_claims"] == corrupt


def test_track_revert_field_literal_matches_track_claim_attrs() -> None:
    assert set(get_args(TrackRevertField)) == set(TRACK_CLAIM_FIELDS.values())


def test_router_identity_attr_sets_derive_from_claim_fields() -> None:
    from arm_backend.routers import jobs as jobs_router

    assert jobs_router._IDENTITY_TRACK_ATTRS == frozenset(TRACK_CLAIM_FIELDS.values())
    # JobUpdateRequest has no season (season is set through /resolve).
    assert jobs_router._IDENTITY_JOB_ATTRS == frozenset({"disc_number", "disc_total"})


def test_source_claims_suggestion_and_new_external_ids_round_trip() -> None:
    sc = SourceClaims(suggestion=True)
    assert SourceClaims.model_validate(sc.model_dump(mode="json", exclude_unset=True)).suggestion is True
    assert ExternalIds(tvmaze="82", anidb="1").model_dump(exclude_none=True) == {"tvmaze": "82", "anidb": "1"}
