from datetime import datetime, timezone

from arm_common.schemas.job_metadata import (
    ExternalIds,
    IdentitySuggestion,
    JobMetadata,
    identity_suggestion_of,
    without_identity_suggestion,
)


def _suggestion() -> dict:
    return {
        "provider": "tmdb",
        "title": "Iron Man",
        "year": 2008,
        "kind": "movie",
        "poster_url": "https://image.tmdb.org/t/p/w500/abc.jpg",
        "external_ids": {"imdb": "tt0371746", "tmdb": "1726", "tmdb_kind": "movie"},
        "overview": "Tony Stark.",
        "payload": {"id": 1726, "poster_path": "/abc.jpg"},
        "suggested_at": "2026-10-15T10:00:00Z",
    }


def test_job_metadata_parses_the_suggestion_section():
    md = JobMetadata.model_validate({"identity_suggestion": _suggestion()})
    assert md.identity_suggestion is not None
    assert md.identity_suggestion.title == "Iron Man"
    assert md.identity_suggestion.external_ids.imdb == "tt0371746"
    assert md.identity_suggestion.suggested_at == datetime(2026, 10, 15, 10, tzinfo=timezone.utc)


def test_identity_suggestion_of_reads_a_valid_section():
    s = identity_suggestion_of({"identity_suggestion": _suggestion(), "flags": {"unidentified": True}})
    assert isinstance(s, IdentitySuggestion)
    assert (s.provider, s.kind, s.year) == ("tmdb", "movie", 2008)


def test_identity_suggestion_of_is_none_when_absent_or_malformed():
    assert identity_suggestion_of(None) is None
    assert identity_suggestion_of({}) is None
    assert identity_suggestion_of({"identity_suggestion": "nope"}) is None
    assert identity_suggestion_of({"identity_suggestion": {"title": "no provider"}}) is None


def test_without_identity_suggestion_drops_only_that_section():
    md = {"identity_suggestion": _suggestion(), "flags": {"unidentified": True}, "scan_result": None}
    out = without_identity_suggestion(md)
    assert "identity_suggestion" not in out
    assert out["flags"] == {"unidentified": True}
    assert md["identity_suggestion"] is not None  # input untouched
    assert without_identity_suggestion(None) == {}


def test_identity_suggestion_external_ids_default_empty():
    s = IdentitySuggestion(
        provider="tvmaze", title="Lost", kind="tv", payload={}, suggested_at=datetime.now(timezone.utc)
    )
    assert s.external_ids == ExternalIds()
    assert s.year is None and s.poster_url is None and s.overview is None
