"""Playlist-first Blu-ray identify: tracks from the structure, the title map posted by the background MakeMKV
run, Start's dependence on it and the rip-start response's title numbers. DVD behaviour stays as it was."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from arm_backend.identity.proposals import claims_of, record_manual_track
from arm_backend.identity.sources.thediscdb_snapshot import DiscMatch
from arm_backend.metadata.base import MetadataResult
from arm_backend.routers import ripper as ripper_router
from arm_backend.track_selection import select_tracks_for_review
from arm_common import DiscType, JobStatus, TrackStatus
from arm_common.enums import TrackKind
from arm_common.models import Track
from arm_common.schemas import BdPlaylist, DiscFingerprintInput, ScanResult, ScanTitle
from arm_common.title_classes import TitleClass
from tests._fakes import FakeSession
from tests.bd_structure_scans import (
    EXTRA,
    OTHER_ANGLE,
    PICK,
    SUBSET,
    br3d_makemkv_titles,
    br3d_structure_scan,
)
from tests.test_ripper_router import (
    _OWNER_HEADERS,
    _SERVICE_AUTH,
    _config,
    _Dispatcher,
    _drive,
    _Hub,
    _job,
    _make_app,
    _movie_preset,
    _scan_dict,
    _track,
)

JOB_ID = "job_01JZXR7K3M5Q8N4VWA00000001"


def _structure_job(
    scan: ScanResult, *, status: JobStatus = JobStatus.AWAITING_REVIEW, with_tracks: bool = True, db: FakeSession
) -> Any:
    job = _job(JOB_ID, status=status, disc_type=DiscType.BLURAY, meta={"scan_result": scan.model_dump(mode="json")})
    db.rows["drives"] = [_drive()]
    db.rows["jobs"] = [job]
    db.rows["rip_presets"] = [_movie_preset()]
    db.rows["tracks"] = []
    if with_tracks:
        tracks = select_tracks_for_review(JOB_ID, scan, _movie_preset())
        for n, track in enumerate(tracks):
            track.id, track.status, track.attempts = f"trk_{n}", TrackStatus.QUEUED, 0
        db.rows["tracks"] = tracks
    return job


def _post_titles(client: TestClient, body: dict[str, Any]) -> Any:
    return client.post(f"/api/ripper/jobs/{JOB_ID}/titles", json=body, headers=_OWNER_HEADERS)


def _mkv_titles(*, drop: str | None = None) -> list[dict[str, Any]]:
    """MakeMKV's list for the 3D disc; `drop` leaves out the title for that source file."""
    titles = [t for t in br3d_makemkv_titles() if t.source_file != drop]
    return [t.model_dump(mode="json") for t in titles]


def _by_ref(db: FakeSession) -> dict[str, Track]:
    return {t.source_ref: t for t in db.rows["tracks"]}


# --- identify builds tracks from the structure, before MakeMKV has run ---


def test_identify_with_a_structure_scan_parks_the_card_with_tracks_keyed_by_title_ref() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(hold_for_review=True)]
    db.rows["rip_presets"] = [_movie_preset()]
    hub = _Hub()
    app = _make_app(
        db, dispatcher=_Dispatcher(MetadataResult(title="Feature", year=2017, kind="movie", payload={})), hub=hub
    )
    scan = br3d_structure_scan()
    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/identify",
            json={"drive_id": "drv_x", "scan_result": scan.model_dump(mode="json")},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "awaiting_review"
    tracks = {t.source_ref: t for t in db.added if isinstance(t, Track)}
    assert set(tracks) == {EXTRA, PICK, OTHER_ANGLE, SUBSET}
    assert [tracks[r].excluded for r in (EXTRA, PICK, OTHER_ANGLE, SUBSET)] == [False, False, True, True]
    assert (tracks[OTHER_ANGLE].title_class, tracks[OTHER_ANGLE].title_class_ref) == (TitleClass.ANGLE, PICK)
    stored = ScanResult.model_validate(db.rows["jobs"][0].metadata_json["scan_result"])
    assert stored.titles == [] and len(stored.playlists) == 3  # MakeMKV's titles are not there yet


def test_identify_with_a_structure_scan_and_thediscdb_claims_keys_them_by_ref() -> None:
    from arm_backend.identity.sources.thediscdb_snapshot import DiscMatch

    class _Store:
        def lookup(self, _hash: str) -> DiscMatch:
            return DiscMatch(
                kind="movie",
                title_slug="feature-2017",
                release_slug="r",
                disc={"Titles": [{"SourceFile": "00102.mpls", "Duration": "0:04:47", "Item": {"Type": "Featurette"}}]},
                metadata={"Title": "Feature", "Year": 2017},
                release={},
            )

    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(hold_for_review=True, thediscdb_enabled=True)]
    db.rows["rip_presets"] = [_movie_preset()]
    app = _make_app(db, dispatcher=_Dispatcher(MetadataResult(title="Feature", year=2017, kind="movie", payload={})))
    app.state.thediscdb = _Store()
    scan = br3d_structure_scan().model_copy(
        update={"fingerprints": [DiscFingerprintInput(algo="thediscdb", value="ABC")]}
    )
    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/identify",
            json={"drive_id": "drv_x", "scan_result": scan.model_dump(mode="json")},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 200, r.text
    assert set(claims_of(db.rows["jobs"][0]).sources["thediscdb"].tracks) == {EXTRA}


def test_identify_reads_the_structures_titles_for_the_tv_signal() -> None:
    episodes = [
        BdPlaylist(name=f"0000{n}.mpls", clips=[n], clip_seconds=[2400.0], duration_seconds=2400, chapter_count=4)
        for n in range(1, 5)
    ]
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config()]
    dispatcher = _Dispatcher()
    scan = ScanResult(disc_type=DiscType.BLURAY, playlists=episodes)
    with TestClient(_make_app(db, dispatcher=dispatcher)) as client:
        r = client.post(
            "/api/ripper/identify",
            json={"drive_id": "drv_x", "scan_result": scan.model_dump(mode="json")},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 200, r.text
    assert dispatcher.received_kwargs["prefer_tv"] is True


# --- the title map arrives ---


def test_titles_post_stores_makemkvs_titles_and_refreshes_sizes_and_names() -> None:
    db = FakeSession()
    scan = br3d_structure_scan()
    _structure_job(scan, db=db)
    mkv = _mkv_titles()
    mkv[1]["playlist_name"] = "FPL_MainFeature"
    mkv[1]["size_bytes"] = 43_000_000_000
    hub = _Hub()
    with TestClient(_make_app(db, hub=hub)) as client:
        r = _post_titles(client, {"titles": mkv})
    assert r.status_code == 204, r.text
    stored = ScanResult.model_validate(db.rows["jobs"][0].metadata_json["scan_result"])
    assert [t.index for t in stored.titles] == [0, 1, 2, 3] and len(stored.playlists) == 3
    pick = _by_ref(db)[PICK]
    assert (pick.expected_size_bytes, pick.playlist_name) == (43_000_000_000, "FPL_MainFeature")
    assert any(e["event_type"] == "job.identity_updated" for e in hub.events)
    assert {e["payload"]["track_id"] for e in hub.events if e["event_type"] == "track.updated"} >= {"trk_1"}


def test_a_title_makemkv_gives_no_size_keeps_the_structures_estimate() -> None:
    db = FakeSession()
    _structure_job(br3d_structure_scan(), db=db)
    estimate = _by_ref(db)[EXTRA].expected_size_bytes
    mkv = _mkv_titles()
    mkv[0]["size_bytes"] = None
    with TestClient(_make_app(db)) as client:
        _post_titles(client, {"titles": mkv})
    assert estimate is not None and _by_ref(db)[EXTRA].expected_size_bytes == estimate


def test_a_playlist_makemkv_does_not_list_is_unticked_through_the_preset_claim() -> None:
    db = FakeSession()
    scan = br3d_structure_scan()
    job = _structure_job(scan, db=db)
    with TestClient(_make_app(db)) as client:
        r = _post_titles(client, {"titles": _mkv_titles(drop="00102.mpls")})
    assert r.status_code == 204, r.text
    tracks = _by_ref(db)
    assert tracks[EXTRA].excluded is True
    assert tracks[PICK].excluded is False
    assert claims_of(job).sources["preset"].tracks[EXTRA].selected is False


def test_a_thediscdb_tick_on_an_unrippable_ref_does_not_outrank_the_drop() -> None:
    from arm_backend.identity.proposals import put_source
    from arm_common.schemas.identity import SourceClaims, TrackClaim

    db = FakeSession()
    job = _structure_job(br3d_structure_scan(), db=db)
    put_source(job, "thediscdb", SourceClaims(tracks={EXTRA: TrackClaim(selected=True)}, status="ok"))
    with TestClient(_make_app(db)) as client:
        _post_titles(client, {"titles": _mkv_titles(drop="00102.mpls")})
    assert _by_ref(db)[EXTRA].excluded is True
    with TestClient(_make_app(db)) as client:  # a later resolve keeps it dropped
        _post_titles(client, {"titles": _mkv_titles(drop="00102.mpls")})
    assert _by_ref(db)[EXTRA].excluded is True


def test_an_operator_tick_made_before_the_map_is_dropped_for_an_unrippable_ref() -> None:
    db = FakeSession()
    job = _structure_job(br3d_structure_scan(), db=db)
    extra = _by_ref(db)[EXTRA]
    extra.excluded = False
    record_manual_track(job, extra, {"excluded": False})
    with TestClient(_make_app(db)) as client:
        _post_titles(client, {"titles": _mkv_titles(drop="00102.mpls")})
    assert extra.excluded is True


def test_a_titles_failure_is_stored_and_keeps_the_card() -> None:
    db = FakeSession()
    job = _structure_job(br3d_structure_scan(), db=db)
    hub = _Hub()
    with TestClient(_make_app(db, hub=hub)) as client:
        r = _post_titles(client, {"failure": "makemkvcon timed out after 300.0s"})
    assert r.status_code == 204, r.text
    assert job.status == JobStatus.AWAITING_REVIEW
    assert job.metadata_json["makemkv_failure"] == "makemkvcon timed out after 300.0s"
    assert any(e["event_type"] == "job.identity_updated" for e in hub.events)


def test_a_titles_failure_after_start_was_pressed_fails_the_job_with_the_reason() -> None:
    """Start was pressed while MakeMKV was still reading: the job is RIPPING and waiting for a map that will
    never come, so it fails with the reason instead of hanging."""
    db = FakeSession()
    job = _structure_job(br3d_structure_scan(), status=JobStatus.RIPPING, db=db)
    hub = _Hub()
    with TestClient(_make_app(db, hub=hub)) as client:
        r = _post_titles(client, {"failure": "makemkvcon exited 5: no key"})
    assert r.status_code == 204, r.text
    assert job.status == JobStatus.FAILED
    failed = [e for e in hub.events if e["event_type"] == "rip.failed"]
    assert failed and "makemkvcon exited 5: no key" in failed[0]["payload"]["reason"]


def test_a_later_titles_post_clears_an_earlier_failure() -> None:
    db = FakeSession()
    job = _structure_job(br3d_structure_scan(), db=db)
    job.metadata_json = {**job.metadata_json, "makemkv_failure": "old"}
    with TestClient(_make_app(db)) as client:
        _post_titles(client, {"titles": _mkv_titles()})
    assert "makemkv_failure" not in job.metadata_json


def test_titles_post_for_a_disc_without_a_structure_scan_is_refused() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["jobs"] = [_job(JOB_ID, status=JobStatus.AWAITING_REVIEW, meta={"scan_result": _scan_dict()})]
    with TestClient(_make_app(db)) as client:
        r = _post_titles(client, {"titles": _mkv_titles()})
    assert r.status_code == 409


def test_titles_post_without_a_stored_scan_is_refused() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["jobs"] = [_job(JOB_ID, status=JobStatus.AWAITING_REVIEW)]
    with TestClient(_make_app(db)) as client:
        r = _post_titles(client, {"titles": _mkv_titles()})
    assert r.status_code == 409


# --- Start depends on the map ---


def test_rip_start_before_the_titles_arrive_is_refused_as_pending() -> None:
    db = FakeSession()
    _structure_job(br3d_structure_scan(), db=db)
    with TestClient(_make_app(db)) as client:
        r = client.post(f"/api/ripper/jobs/{JOB_ID}/rip-start", headers=_OWNER_HEADERS)
    assert r.status_code == 409
    assert "titles_pending" in r.json()["detail"]


def test_rip_start_after_a_titles_failure_is_refused() -> None:
    db = FakeSession()
    job = _structure_job(br3d_structure_scan(), db=db)
    job.metadata_json = {**job.metadata_json, "makemkv_failure": "no key"}
    with TestClient(_make_app(db)) as client:
        r = client.post(f"/api/ripper/jobs/{JOB_ID}/rip-start", headers=_OWNER_HEADERS)
    assert r.status_code == 409
    assert "no key" in r.json()["detail"]


def test_rip_start_answers_the_title_numbers_of_the_map() -> None:
    db = FakeSession()
    _structure_job(br3d_structure_scan(), db=db)
    with TestClient(_make_app(db)) as client:
        _post_titles(client, {"titles": _mkv_titles()})
        r = client.post(f"/api/ripper/jobs/{JOB_ID}/rip-start", headers=_OWNER_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["title_numbers"] == {EXTRA: 0, PICK: 1, OTHER_ANGLE: 2, SUBSET: 3}
    assert {t["source_ref"] for t in r.json()["tracks"]} == {EXTRA, PICK, OTHER_ANGLE, SUBSET}


def test_resume_answers_the_same_title_numbers() -> None:
    db = FakeSession()
    _structure_job(br3d_structure_scan(), status=JobStatus.RIPPING, db=db)
    with TestClient(_make_app(db)) as client:
        _post_titles(client, {"titles": _mkv_titles()})
        r = client.post(f"/api/ripper/jobs/{JOB_ID}/resume", headers=_OWNER_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["title_numbers"] == {EXTRA: 0, PICK: 1, OTHER_ANGLE: 2, SUBSET: 3}


def test_rip_start_without_review_tracks_selects_from_the_structure_and_skips_unrippable_refs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_select = ripper_router.select_tracks

    def _select_with_db_defaults(*args: Any, **kwargs: Any) -> list[Track]:
        tracks = real_select(*args, **kwargs)
        for n, track in enumerate(tracks):
            track.id, track.status, track.attempts = f"trk_{n}", TrackStatus.QUEUED, 0
        return tracks

    monkeypatch.setattr(ripper_router, "select_tracks", _select_with_db_defaults)
    db = FakeSession()
    _structure_job(br3d_structure_scan(), status=JobStatus.IDENTIFIED, with_tracks=False, db=db)
    with TestClient(_make_app(db)) as client:
        _post_titles(client, {"titles": _mkv_titles(drop="00102.mpls")})
        r = client.post(f"/api/ripper/jobs/{JOB_ID}/rip-start", headers=_OWNER_HEADERS)
    assert r.status_code == 200, r.text
    assert {t["source_ref"] for t in r.json()["tracks"] if not t["excluded"]} == {PICK}


def test_rip_start_of_a_dvd_answers_the_identity_map() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["jobs"] = [_job(JOB_ID, status=JobStatus.RIPPING, meta={"scan_result": _scan_dict()})]
    db.rows["tracks"] = [_track("trk_1", status=TrackStatus.QUEUED, index=1)]
    full = _track("trk_2", status=TrackStatus.QUEUED, index=0)
    full.source_ref, full.kind = "full", TrackKind.DATA_DUMP
    db.rows["tracks"].append(full)
    with TestClient(_make_app(db)) as client:
        r = client.post(f"/api/ripper/jobs/{JOB_ID}/rip-start", headers=_OWNER_HEADERS)
    assert r.status_code == 200, r.text
    assert r.json()["title_numbers"] == {"1": 1}


def test_a_fallback_blu_ray_answers_the_identity_map() -> None:
    db = FakeSession()
    scan = ScanResult(disc_type=DiscType.BLURAY, titles=[ScanTitle(index=4, duration_seconds=7000)])
    _structure_job(scan, status=JobStatus.RIPPING, with_tracks=False, db=db)
    db.rows["tracks"] = [_track("trk_1", status=TrackStatus.QUEUED, index=4)]
    with TestClient(_make_app(db)) as client:
        r = client.post(f"/api/ripper/jobs/{JOB_ID}/rip-start", headers=_OWNER_HEADERS)
    assert r.json()["title_numbers"] == {"4": 4}
