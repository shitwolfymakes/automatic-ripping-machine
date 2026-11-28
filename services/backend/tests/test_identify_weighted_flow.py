"""The identify flow around the weighted search: how each decision becomes a job status, and what is stored."""

from __future__ import annotations

from typing import Any

import httpx
from arm_common import DriveKind
from arm_common.schemas import BdDiscMeta, IdentifyMatch, MatchEvidence, MatchParts, MatchThresholds
from arm_common.schemas.job_metadata import MatchCandidate
from fastapi.testclient import TestClient

from arm_backend.metadata.base import MetadataResult
from arm_backend.metadata.dispatcher import Identification, MetadataDispatcher
from tests._fakes import FakeSession
from tests.bd_structure_scans import br3d_structure_scan
from tests.test_dispatcher_weighted import br2049_provider_responses
from tests.test_ripper_router import (
    _SERVICE_AUTH,
    _config,
    _Dispatcher,
    _drive,
    _make_app,
    _movie_preset,
    _scan_dict,
)


def _candidate(title: str, year: int, score: float, **kw: Any) -> MatchCandidate:
    return MatchCandidate(
        title=title,
        year=year,
        kind="movie",
        providers=["tmdb"],
        provider="tmdb",
        ids={"tmdb": "1"},
        score=score,
        parts=MatchParts(title=score, year=0, runtime=0, kind=0, agreement=0),
        **kw,
    )


def _match(decision: str, *candidates: MatchCandidate, shortlist: int = 0, **kw: Any) -> IdentifyMatch:
    return IdentifyMatch(
        decision=decision,  # type: ignore[arg-type]
        evidence=MatchEvidence(p_tv=0.15, kind_reasons=["single 120-min feature"]),
        candidates=list(candidates),
        shortlist=shortlist,
        thresholds=MatchThresholds(accept=65, margin=10, floor=40, title_min=0.7),
        **kw,
    )


class _Weighted(_Dispatcher):
    """A dispatcher that answers `identify` with a given hit and breakdown."""

    def __init__(self, result: MetadataResult | None, match: IdentifyMatch | None, **kw: Any) -> None:
        super().__init__(result, **kw)
        self.match = match

    async def identify(self, _scan: Any, _cfg: Any, **_kw: Any) -> Identification:
        self.received_kwargs = _kw
        self.last_attempts = list(self.attempts)
        return Identification(self.result, self.match)


def _post(db: FakeSession, dispatcher: Any, scan: dict[str, Any] | None = None) -> Any:
    with TestClient(_make_app(db, dispatcher=dispatcher)) as client:
        return client.post(
            "/api/ripper/identify",
            json={"drive_id": "drv_x", "scan_result": scan or _scan_dict()},
            headers=_SERVICE_AUTH,
        )


def _db(**cfg: Any) -> FakeSession:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(**cfg)]
    db.rows["rip_presets"] = [_movie_preset()]
    return db


HIT = MetadataResult(title="Heat", year=1995, kind="movie", payload={"id": 949}, provider="tmdb")


# --- the Blade Runner 2049 3D disc, end to end -----------------------------------------------------------------------


def test_blade_runner_2049_3d_is_identified_by_its_runtime_and_its_iso_year() -> None:
    db = _db()
    config = db.rows["config"][0]
    config.tmdb_api_key, config.omdb_api_key = "tmdb-k", "omdb-k"
    drive = db.rows["drives"][0]
    drive.kind = DriveKind.VIRTUAL
    drive.source_path = "movies/Blade_Runner_2049_(2017)_[3D].iso"
    scan = br3d_structure_scan().model_copy(
        update={
            "volume_label": None,
            "bd_meta": BdDiscMeta(name="Blade Runner 2049 - 3D Blu-ray™", set_number=1, num_sets=1),
        }
    )
    fake = br2049_provider_responses()
    dispatcher = MetadataDispatcher(httpx.AsyncClient(transport=httpx.MockTransport(fake)))

    r = _post(db, dispatcher, scan.model_dump(mode="json"))

    assert r.status_code == 200, r.text
    out = r.json()
    assert (out["title"], out["year"], out["media_type"]) == ("Blade Runner 2049", 2017, "movie")
    assert out["status"] == "identified"
    meta = out["metadata_json"]
    assert "identify_attempts" not in meta and "identity_suggestion" not in meta
    sources = meta["identity_claims"]["sources"]
    assert sources["bd_title"]["job"] == {"title": "blade runner 2049 3d", "disc_number": 1, "disc_total": 1}
    assert sources["iso_name"]["job"] == {"title": "blade runner 2049", "year": 2017}
    assert sources["label"]["status"] == "skipped"
    match = meta["identify_match"]
    assert match["decision"] == "accept"
    assert [q["text"] for q in match["queries"]] == ["Blade Runner 2049"]
    assert [c["title"] for c in match["candidates"]][0] == "Blade Runner 2049"
    assert all("2099" not in c["title"] for c in match["candidates"])
    assert meta["identity"]["external_ids"]["imdb"] == "tt1856101"


# --- decisions to job states ---------------------------------------------------------------------------------------


def test_an_accepted_hit_is_applied_and_its_breakdown_is_kept() -> None:
    match = _match("accept", _candidate("Heat", 1995, 91.5), runner_up=24.7)
    out = _post(_db(), _Weighted(HIT, match)).json()
    assert (out["status"], out["title"], out["year"]) == ("identified", "Heat", 1995)
    stored = out["metadata_json"]["identify_match"]
    assert stored["decision"] == "accept" and stored["runner_up"] == 24.7
    assert stored["candidates"][0]["score"] == 91.5
    assert "identify_attempts" not in out["metadata_json"]


def test_an_accepted_hit_with_auto_apply_off_is_held_and_keeps_its_breakdown() -> None:
    match = _match("accept", _candidate("Heat", 1995, 91.5))
    out = _post(_db(movie_auto_apply=False), _Weighted(HIT, match)).json()
    assert out["status"] == "awaiting_review" and out["wait_start_time"] is None
    assert out["metadata_json"]["identity_suggestion"]["title"] == "Heat"
    assert out["metadata_json"]["identity_suggestion"]["reason"] == "auto_apply_off"
    assert out["metadata_json"]["identity_suggestion"]["score"] == 91.5
    assert out["metadata_json"]["identify_match"]["decision"] == "accept"


def _total_recall() -> IdentifyMatch:
    return _match(
        "shortlist",
        _candidate("Total Recall", 1990, 72.0),
        _candidate("Total Recall", 2012, 69.5),
        shortlist=2,
        runner_up=69.5,
    )


def test_a_shortlist_holds_the_disc_for_a_pick_with_no_countdown() -> None:
    out = _post(_db(), _Weighted(None, _total_recall(), attempts=[{"source": "tmdb", "outcome": "hit"}])).json()
    assert out["status"] == "awaiting_review" and out["wait_start_time"] is None
    assert out["media_type"] == "movie"
    suggestion = out["metadata_json"]["identity_suggestion"]
    assert (suggestion["reason"], suggestion["score"], suggestion["title"], suggestion["year"]) == (
        "close",
        72.0,
        "Total Recall",
        1990,
    )
    assert [(a["year"], a["provider"], a["ids"], a["score"]) for a in suggestion["alternatives"]] == [
        (1990, "tmdb", {"tmdb": "1"}, 72.0),
        (2012, "tmdb", {"tmdb": "1"}, 69.5),
    ]
    assert out["metadata_json"]["flags"]["unidentified"] is True and "identity" not in out["metadata_json"]
    stored = out["metadata_json"]["identify_match"]
    assert stored["decision"] == "shortlist" and stored["shortlist"] == 2
    # The attempts explain a miss; a shortlist is not one.
    assert "identify_attempts" not in out["metadata_json"]


def test_a_shortlist_offers_at_most_the_shortlisted_rows() -> None:
    match = _match(
        "shortlist",
        _candidate("Total Recall", 1990, 72.0),
        _candidate("Total Recall", 2012, 69.5),
        _candidate("Total Recall 2070", 1999, 12.0),
        shortlist=2,
    )
    out = _post(_db(), _Weighted(None, match)).json()
    assert len(out["metadata_json"]["identity_suggestion"]["alternatives"]) == 2
    assert len(out["metadata_json"]["identify_match"]["candidates"]) == 3


def test_a_shortlist_does_not_block_an_unattended_install() -> None:
    out = _post(_db(block_on_miss=False), _Weighted(None, _total_recall())).json()
    assert out["status"] == "identified"
    assert out["metadata_json"]["flags"]["unidentified"] is True
    # Kept, so the card can still ask after the rip.
    assert out["metadata_json"]["identity_suggestion"]["reason"] == "close"
    assert out["metadata_json"]["identify_match"]["decision"] == "shortlist"


def test_no_match_is_a_miss_with_the_closest_candidate_stored() -> None:
    match = _match("no_match", _candidate("Blade Runner 2099", 2026, -2.0, flags=["numbers_differ"]))
    out = _post(_db(), _Weighted(None, match)).json()
    assert out["status"] == "awaiting_user_id"
    assert out["metadata_json"]["identify_match"]["candidates"][0]["flags"] == ["numbers_differ"]


def test_a_dispatch_timeout_stores_no_breakdown() -> None:
    out = _post(_db(), _Weighted(None, None, raise_timeout=True)).json()
    assert out["status"] == "awaiting_user_id"
    assert "identify_match" not in out["metadata_json"]


def test_a_cd_has_no_breakdown() -> None:
    hit = MetadataResult(title="Album", year=1999, kind="music", payload={}, provider="musicbrainz")
    out = _post(_db(), _Weighted(hit, None), _scan_dict("cd")).json()
    assert "identify_match" not in out["metadata_json"]


def test_a_new_identify_replaces_a_stale_breakdown() -> None:
    db = _db()

    class _Stale(_Weighted):
        async def identify(self, _scan: Any, _cfg: Any, **_kw: Any) -> Identification:
            from arm_common import Job

            for row in db.added:
                if isinstance(row, Job):
                    row.metadata_json = {**(row.metadata_json or {}), "identify_match": {"decision": "stale"}}
            return await super().identify(_scan, _cfg, **_kw)

    out = _post(db, _Stale(HIT, _match("accept", _candidate("Heat", 1995, 91.5)))).json()
    assert out["metadata_json"]["identify_match"]["decision"] == "accept"


# --- exact hits ----------------------------------------------------------------------------------------------------


def _exact_dispatcher(result: MetadataResult) -> MetadataDispatcher:
    class Source:
        id = "tmdb"
        media_types = frozenset({"movie", "tv"})
        requires_key = None

        def configured(self, _cfg: object) -> None:
            return None

        async def lookup_imdb(self, _cfg: object, _imdb: str) -> MetadataResult:
            return result

    return MetadataDispatcher(httpx.AsyncClient(), sources={"tmdb": Source()})  # type: ignore[dict-item]


def _thediscdb_db(**cfg: Any) -> tuple[FakeSession, Any]:
    from tests.test_ripper_router import _FakeStore, _thediscdb_match

    db = _db(thediscdb_enabled=True, **cfg)
    return db, _FakeStore(_thediscdb_match())


def _thediscdb_scan(label: str) -> dict[str, Any]:
    scan = _scan_dict("bluray")
    scan["volume_label"] = label
    scan["titles"] = [{"index": 0, "duration_seconds": 7894, "source_file": "00001.mpls"}]
    scan["fingerprints"] = [{"algo": "thediscdb", "value": "2D61282D8DA5EAC2CA87B451BCE9A055"}]
    return scan


def test_a_thediscdb_hit_wins_with_its_text_score_stored() -> None:
    db, store = _thediscdb_db()
    hit = MetadataResult(title="Round Midnight", year=1986, kind="movie", payload={"id": 5}, provider="tmdb")
    app = _make_app(db, dispatcher=_exact_dispatcher(hit))  # type: ignore[arg-type]
    app.state.thediscdb = store
    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/identify",
            json={"drive_id": "drv_x", "scan_result": _thediscdb_scan("ROUND_MIDNIGHT")},
            headers=_SERVICE_AUTH,
        )
    out = r.json()
    assert (out["title"], out["status"]) == ("Round Midnight", "identified")
    match = out["metadata_json"]["identify_match"]
    assert (match["decision"], match["exact"], match["text_disagrees"]) == ("exact", "thediscdb", False)
    assert match["candidates"][0]["score"] > 20


def test_a_thediscdb_hit_the_disc_text_contradicts_still_applies_and_is_flagged() -> None:
    db, store = _thediscdb_db()
    hit = MetadataResult(title="Cats", year=2019, kind="tv", payload={"id": 6}, provider="tmdb")
    app = _make_app(db, dispatcher=_exact_dispatcher(hit))  # type: ignore[arg-type]
    app.state.thediscdb = store
    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/identify",
            json={"drive_id": "drv_x", "scan_result": _thediscdb_scan("ROUND_MIDNIGHT")},
            headers=_SERVICE_AUTH,
        )
    out = r.json()
    assert out["title"] == "Cats"  # the content hash wins; the scorer never vetoes it
    match = out["metadata_json"]["identify_match"]
    assert match["text_disagrees"] is True and "text_disagrees" in match["candidates"][0]["flags"]
