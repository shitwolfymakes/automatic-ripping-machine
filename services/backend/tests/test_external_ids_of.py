"""Every id a provider hit carries lands in the identity, with the TMDb id's
kind, so episode sources can find the show (spec 3.4)."""

from __future__ import annotations

from datetime import datetime, timezone

from arm_backend.metadata.base import MetadataResult, external_ids_of, extract_poster_url, metadata_with_identity


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


def test_external_ids_of_reads_tvmaze_and_tvdb_provider_ids() -> None:
    tvmaze = MetadataResult(
        title="Lost",
        year=2004,
        kind="tv",
        provider="tvmaze",
        payload={"id": 4607, "imdb_id": "tt0411008", "tvdb_id": "73739"},
    )
    ids = external_ids_of(tvmaze)
    assert (ids.tvmaze, ids.imdb, ids.tvdb, ids.tmdb) == ("4607", "tt0411008", "73739", None)
    tvdb = MetadataResult(title="Lost", year=2004, kind="tv", provider="tvdb", payload={"id": 73739})
    assert external_ids_of(tvdb).tvdb == "73739"
    explicit = MetadataResult(
        title="X", year=None, kind="tv", provider="omdb", payload={"tvmaze_id": "9", "tvdb_id": "8"}
    )
    assert (external_ids_of(explicit).tvmaze, external_ids_of(explicit).tvdb) == ("9", "8")
    empty = MetadataResult(title="X", year=None, kind="tv", provider="tvmaze", payload={})
    assert external_ids_of(empty).tvmaze is None


def test_extract_poster_url_accepts_a_generic_poster_url() -> None:
    url = MetadataResult(title="X", year=None, kind="tv", payload={"poster_url": "https://img/x.jpg"})
    assert extract_poster_url(url) == "https://img/x.jpg"
    bad = MetadataResult(title="X", year=None, kind="tv", payload={"poster_url": "not a url"})
    assert extract_poster_url(bad) is None
    both = MetadataResult(
        title="X", year=None, kind="tv", payload={"poster_path": "/a.jpg", "poster_url": "https://img/x.jpg"}
    )
    poster = extract_poster_url(both)
    assert poster is not None and poster.endswith("/a.jpg")
