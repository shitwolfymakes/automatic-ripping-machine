"""Every id a provider hit carries lands in the identity, with the TMDb id's
kind, so episode sources can find the show (spec 3.4)."""

from __future__ import annotations

from datetime import datetime, timezone

from arm_backend.metadata.base import MetadataResult, external_ids_of, metadata_with_identity


def test_tmdb_tv_hit_records_all_ids_and_kind() -> None:
    hit = MetadataResult(
        title="Kolchak: The Night Stalker",
        year=1974,
        kind="tv",
        payload={"id": 5084, "imdb_id": "tt0071003", "tvdb_id": 77170},
        provider="tmdb",
    )
    ids = external_ids_of(hit)
    assert (ids.tmdb, ids.imdb, ids.tvdb, ids.tmdb_kind) == ("5084", "tt0071003", "77170", "tv")


def test_tmdb_movie_hit_records_movie_kind() -> None:
    hit = MetadataResult(title="Arrival", year=2016, kind="movie", payload={"id": 329865}, provider="tmdb")
    assert external_ids_of(hit).tmdb_kind == "movie"


def test_no_tmdb_id_means_no_kind() -> None:
    hit = MetadataResult(title="Lost", year=2004, kind="tv", payload={"imdbID": "tt0411008"}, provider="omdb")
    ids = external_ids_of(hit)
    assert (ids.imdb, ids.tmdb, ids.tmdb_kind) == ("tt0411008", None, None)


def test_metadata_with_identity_stores_the_kind() -> None:
    hit = MetadataResult(title="X", year=2000, kind="tv", payload={"id": 1}, provider="tmdb")
    md = metadata_with_identity({}, hit, identified_at=datetime.now(timezone.utc))
    assert md["identity"]["external_ids"] == {"tmdb": "1", "tmdb_kind": "tv"}
