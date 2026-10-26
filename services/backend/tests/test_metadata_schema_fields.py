from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from arm_common.schemas import MetadataCandidate
from arm_common.schemas.job_metadata import IdentityFacts, JobIdentity, JobMetadata
from arm_common.schemas.jobs import ResolveMatch, ResolveRequest
from arm_common.schemas.metadata import MetadataReleaseDetail, MetadataReleaseTrack


def test_release_track_has_length_and_disc():
    t = MetadataReleaseTrack(position=1, title="Come Together", length_ms=259000, disc_number=1)
    assert t.length_ms == 259000
    assert t.disc_number == 1


def test_release_track_fields_default_none():
    t = MetadataReleaseTrack(title="X")
    assert t.length_ms is None and t.disc_number is None


def test_release_detail_has_enriched_fields():
    d = MetadataReleaseDetail(
        release_id="r1",
        title="Abbey Road",
        catalog_number="PCS 7088",
        barcode="0094638246619",
        country="GB",
        format="CD",
        status="Official",
        disc_count=1,
        track_count=17,
    )
    assert d.catalog_number == "PCS 7088"
    assert d.barcode == "0094638246619"
    assert d.country == "GB"
    assert d.format == "CD"
    assert d.status == "Official"
    assert d.disc_count == 1
    assert d.track_count == 17


def test_identity_facts_defaults_are_empty() -> None:
    f = IdentityFacts()
    assert f.model_dump() == {
        "end_year": None,
        "overview": None,
        "rating": None,
        "rating_source": None,
        "votes": None,
        "genres": [],
        "creators": [],
        "cast": [],
        "episode_count": None,
    }


def test_identity_facts_rejects_unknown_rating_source() -> None:
    with pytest.raises(ValidationError):
        IdentityFacts(rating=7.0, rating_source="tvdb")


def test_candidate_carries_provider_and_facts() -> None:
    c = MetadataCandidate(title="Kolchak", kind="tv", provider="tmdb", facts=IdentityFacts(cast=["Darren McGavin"]))
    assert c.model_dump()["facts"]["cast"] == ["Darren McGavin"]
    assert MetadataCandidate(title="x", kind="movie").facts is None


def test_job_identity_round_trips_a_facts_snapshot() -> None:
    now = datetime(2026, 10, 16, tzinfo=timezone.utc)
    md = JobMetadata.model_validate(
        {"identity": {"provider": "tvmaze", "facts": {"genres": ["Horror"]}, "facts_fetched_at": now.isoformat()}}
    )
    assert md.identity is not None and md.identity.facts == IdentityFacts(genres=["Horror"])
    assert md.identity.facts_fetched_at == now
    assert JobIdentity(provider="manual").facts is None


def test_resolve_request_accepts_match_and_forbids_unknown_keys() -> None:
    req = ResolveRequest.model_validate(
        {"title": "K", "match": {"provider": "tvmaze", "poster_url": "https://static.tvmaze.com/a.jpg"}}
    )
    assert req.match == ResolveMatch(provider="tvmaze", poster_url="https://static.tvmaze.com/a.jpg")
    assert req.match.poster_is_manual is False and req.match.facts is None
    with pytest.raises(ValidationError):
        ResolveMatch.model_validate({"provider": "tvmaze", "bogus": 1})
    with pytest.raises(ValidationError):
        ResolveMatch.model_validate({"provider": "imdb"})
