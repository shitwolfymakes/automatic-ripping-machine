"""POST /api/jobs/{id}/resolve with a `match` block (match picker spec 3.6)."""
# ruff: noqa: F811

from __future__ import annotations

from fastapi.testclient import TestClient

from arm_common import JobStatus
from tests._fakes import FakeSession
from tests.test_jobs_router import _StageRunner, _auth, _job, _make_app, signing_key  # noqa: F401

_FACTS = {"genres": ["Horror"], "cast": ["Darren McGavin"], "overview": "A reporter.", "episode_count": 20}


def _identified(ids: dict[str, str]) -> object:
    job = _job(status=JobStatus.IDENTIFIED, meta={"identity": {"provider": "tmdb", "external_ids": ids}})
    job.poster_url = "https://image.tmdb.org/old.jpg"
    job.poster_url_manual = "https://image.tmdb.org/manual-old.jpg"
    return job


def _post(signing_key: bytes, job: object, body: dict) -> tuple[dict, _StageRunner, FakeSession]:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["jobs"] = [job]
    runner = _StageRunner()
    app.state.episode_stage = runner
    with TestClient(app) as client:
        r = client.post(f"/api/jobs/{job.id}/resolve", json=body, headers=_auth(token))  # type: ignore[attr-defined]
    assert r.status_code == 200, r.text
    return r.json()["job"], runner, db


def _match_body(**match: object) -> dict:
    return {
        "title": "Kolchak: The Night Stalker",
        "year": 1974,
        "media_type": "tv",
        "external_ids": {"imdb": "tt0071003", "tmdb": None, "tmdb_kind": None, "tvdb": "77170", "tvmaze": "1"},
        "match": {"provider": "tvmaze", "poster_url": "https://static.tvmaze.com/k.jpg", "facts": _FACTS, **match},
    }


def test_match_replaces_ids_wholesale_and_clears_a_stale_tmdb(signing_key: bytes) -> None:
    job = _identified({"tmdb": "999", "tmdb_kind": "tv", "imdb": "tt9", "musicbrainz_release": "mb1"})
    out, runner, _ = _post(signing_key, job, _match_body())
    ids = out["metadata_json"]["identity"]["external_ids"]
    assert ids["imdb"] == "tt0071003" and ids["tvdb"] == "77170" and ids["tvmaze"] == "1"
    assert ids.get("tmdb") is None and ids.get("tmdb_kind") is None
    assert ids["musicbrainz_release"] == "mb1"  # not a show id; kept
    assert runner.scheduled == [job.id]


def test_match_records_provider_overview_facts_and_time(signing_key: bytes) -> None:
    out, _, _ = _post(signing_key, _identified({"tmdb": "999"}), _match_body())
    identity = out["metadata_json"]["identity"]
    assert identity["provider"] == "tvmaze"
    assert identity["overview"] == "A reporter."
    assert identity["facts"]["cast"] == ["Darren McGavin"] and identity["facts"]["episode_count"] == 20
    assert identity["facts_fetched_at"] and identity["identified_at"]


def test_match_poster_goes_to_poster_url_and_clears_manual(signing_key: bytes) -> None:
    out, _, _ = _post(signing_key, _identified({"tmdb": "999"}), _match_body())
    assert out["poster_url"] == "https://static.tvmaze.com/k.jpg"
    assert out["poster_url_manual"] is None


def test_match_with_edited_poster_saves_it_as_manual(signing_key: bytes) -> None:
    out, _, _ = _post(
        signing_key,
        _identified({"tmdb": "999"}),
        _match_body(poster_url="https://x.example/p.jpg", poster_is_manual=True),
    )
    assert out["poster_url_manual"] == "https://x.example/p.jpg"
    assert out["poster_url"] == "https://image.tmdb.org/old.jpg"


def test_match_without_facts_leaves_snapshot_empty(signing_key: bytes) -> None:
    out, _, _ = _post(signing_key, _identified({}), _match_body(facts=None))
    identity = out["metadata_json"]["identity"]
    assert identity.get("facts") is None and identity.get("facts_fetched_at") is None


def test_match_show_change_forgets_episode_show_ids(signing_key: bytes, monkeypatch) -> None:
    from arm_backend.routers import jobs as jobs_router

    forgotten: list[str] = []
    monkeypatch.setattr(jobs_router, "forget_episode_show_ids", lambda job: forgotten.append(job.id))
    job = _identified({"tmdb": "999", "tmdb_kind": "tv"})
    _post(signing_key, job, _match_body())
    assert forgotten == [job.id]


def test_same_show_match_does_not_forget_episode_ids(signing_key: bytes, monkeypatch) -> None:
    from arm_backend.routers import jobs as jobs_router

    forgotten: list[str] = []
    monkeypatch.setattr(jobs_router, "forget_episode_show_ids", lambda job: forgotten.append(job.id))
    job = _identified({"imdb": "tt0071003", "tvdb": "77170", "tvmaze": "1"})
    _post(signing_key, job, _match_body())
    assert forgotten == []


def test_match_on_a_job_with_no_identity(signing_key: bytes) -> None:
    job = _job(status=JobStatus.AWAITING_REVIEW, meta={})
    out, _, _ = _post(signing_key, job, _match_body())
    assert out["metadata_json"]["identity"]["external_ids"]["tvmaze"] == "1"


def test_resolve_without_match_still_merges(signing_key: bytes) -> None:
    job = _identified({"tmdb": "999", "tmdb_kind": "tv"})
    out, _, _ = _post(signing_key, job, {"title": "X", "external_ids": {"tvdb": "5"}})
    ids = out["metadata_json"]["identity"]["external_ids"]
    assert ids["tmdb"] == "999" and ids["tvdb"] == "5"
    assert out["metadata_json"]["identity"]["provider"] == "tmdb"
    assert out["poster_url_manual"] == "https://image.tmdb.org/manual-old.jpg"
