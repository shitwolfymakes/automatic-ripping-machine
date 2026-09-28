"""identity_claims schemas: presence semantics survive a JSON round trip."""

from arm_common.enums import TrackRole
from arm_common.schemas import JobMetadata
from arm_common.schemas.identity import (
    JOB_CLAIM_FIELDS,
    TRACK_CLAIM_FIELDS,
    IdentityClaims,
    SourceClaims,
    TrackClaim,
)


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
