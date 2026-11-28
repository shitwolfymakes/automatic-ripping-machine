from datetime import datetime, timezone

from arm_backend.identity.apply import apply_identity_result, suggest_identity, suggest_shortlist, suggestion_to_result
from arm_backend.metadata.base import MetadataResult
from arm_common import Job
from arm_common.enums import DiscType, JobStatus, MediaType
from arm_common.schemas.job_metadata import (
    IdentifyMatch,
    MatchCandidate,
    MatchEvidence,
    MatchParts,
    MatchThresholds,
    flag_is_set,
    identity_suggestion_of,
)

_NOW = datetime(2026, 10, 15, 10, tzinfo=timezone.utc)


def _job() -> Job:
    return Job(
        id="job_1", drive_id="drv_x", disc_type=DiscType.DVD, status=JobStatus.CREATED, metadata_json={"flags": {}}
    )


def _iron_man() -> MetadataResult:
    return MetadataResult(
        title="Iron Man",
        year=2008,
        kind="movie",
        payload={"id": 1726, "poster_path": "/abc.jpg", "overview": "Tony."},
        provider="tmdb",
    )


def test_apply_identity_result_sets_the_job_fields_and_identity_section() -> None:
    job = _job()
    apply_identity_result(job, _iron_man(), now=_NOW)
    assert (job.title, job.year, job.media_type) == ("Iron Man", 2008, MediaType.MOVIE)
    assert job.poster_url == "https://image.tmdb.org/t/p/w500/abc.jpg"
    assert job.metadata_json["identity"]["provider"] == "tmdb"
    assert job.metadata_json["identity"]["external_ids"]["tmdb"] == "1726"
    assert job.metadata_json["provider_raw"]["tmdb"]["id"] == 1726


def test_apply_identity_result_music_disc_number() -> None:
    job = _job()
    result = MetadataResult(title="Album", year=1999, kind="music", payload={"disc": 2}, provider="musicbrainz")
    apply_identity_result(job, result, now=_NOW)
    assert job.disc_number == 2
    job2 = _job()
    job2.disc_number = 1
    apply_identity_result(job2, result, now=_NOW)
    assert job2.disc_number == 1  # an existing disc number is kept
    job3 = _job()
    apply_identity_result(job3, MetadataResult(title="A", year=None, kind="music", payload={"disc": True}), now=_NOW)
    assert job3.disc_number is None  # a bool is not a disc number


def test_suggest_identity_stores_the_hit_and_flags_unidentified() -> None:
    md = suggest_identity({"scan_result": {"x": 1}}, _iron_man(), now=_NOW, reason="auto_apply_off", score=91.5)
    s = identity_suggestion_of(md)
    assert s is not None
    assert (s.provider, s.title, s.year, s.kind) == ("tmdb", "Iron Man", 2008, "movie")
    assert (s.reason, s.score, s.alternatives) == ("auto_apply_off", 91.5, [])
    assert s.poster_url == "https://image.tmdb.org/t/p/w500/abc.jpg"
    assert s.external_ids.tmdb == "1726" and s.external_ids.tmdb_kind == "movie"
    assert s.overview == "Tony." and s.payload["id"] == 1726 and s.suggested_at == _NOW
    assert flag_is_set(md, "unidentified")
    assert md["scan_result"] == {"x": 1}
    assert "identity" not in md  # nothing applied


def test_suggestion_round_trips_to_a_result() -> None:
    result = MetadataResult(title="Lost", year=2004, kind="tv", payload={"id": 123, "name": "Lost"}, provider="tvmaze")
    s = identity_suggestion_of(suggest_identity(None, result, now=_NOW, reason="ambiguous_toc"))
    assert s is not None
    back = suggestion_to_result(s)
    assert (back.title, back.year, back.kind, back.provider) == ("Lost", 2004, "tv", "tvmaze")
    assert back.payload == {"id": 123, "name": "Lost"}


def _candidate(title: str, year: int, score: float, tmdb: str) -> MatchCandidate:
    return MatchCandidate(
        title=title,
        year=year,
        kind="movie",
        runtime=113.0,
        providers=["tmdb", "omdb"],
        provider="tmdb",
        ids={"tmdb": tmdb},
        score=score,
        parts=MatchParts(title=40, year=0, runtime=20, kind=7, agreement=4),
    )


def test_suggest_shortlist_stores_the_rows_without_a_provider_record() -> None:
    match = IdentifyMatch(
        decision="shortlist",
        evidence=MatchEvidence(p_tv=0.1),
        candidates=[
            _candidate("Total Recall", 1990, 71.0, "861"),
            _candidate("Total Recall", 2012, 66.5, "64635"),
            _candidate("Total Recall 2070", 1999, 41.0, "9"),
        ],
        shortlist=2,
        thresholds=MatchThresholds(accept=65, margin=10, floor=40, title_min=0.7),
    )
    md = suggest_shortlist({"scan_result": {"x": 1}}, match, now=_NOW)
    s = identity_suggestion_of(md)
    assert s is not None
    assert (s.reason, s.score, s.title, s.year, s.provider, s.payload) == (
        "close",
        71.0,
        "Total Recall",
        1990,
        "tmdb",
        {},
    )
    assert [(a.year, a.ids, a.providers, a.runtime) for a in s.alternatives] == [
        (1990, {"tmdb": "861"}, ["tmdb", "omdb"], 113.0),
        (2012, {"tmdb": "64635"}, ["tmdb", "omdb"], 113.0),
    ]
    assert flag_is_set(md, "unidentified") and md["scan_result"] == {"x": 1} and "identity" not in md
