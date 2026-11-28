"""A disc identify could not match, identified by the operator's search: it follows the review gate a matched disc
follows. With `hold_for_review` on it parks in AWAITING_REVIEW with its titles on the card, and only Start (or the
countdown) rips it; with the gate off it goes straight to IDENTIFIED as before.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from arm_common import Track, User
from arm_common.schemas import ScanResult
from tests._fakes import FakeSession
from tests.bd_structure_scans import EXTRA, PICK, br3d_makemkv_titles, br3d_structure_scan
from tests.test_held_disc_apply_flow import _make_app
from tests.test_ripper_router import (
    _OWNER_HEADERS,
    _SERVICE_AUTH,
    _config,
    _Dispatcher,
    _drive,
    _Hub,
    _movie_preset,
    _scan_dict,
)

_RESOLVE = {"title": "Blade Runner 2049", "year": 2017, "media_type": "movie"}


def _db(**config: bool) -> FakeSession:
    db = FakeSession()
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(**config)]
    db.rows["rip_presets"] = [_movie_preset()]
    db.rows["session_applications"] = []
    return db


def _identify_miss(client: TestClient, db: FakeSession, scan: dict[str, Any]) -> str:
    r = client.post("/api/ripper/identify", json={"drive_id": "drv_x", "scan_result": scan}, headers=_SERVICE_AUTH)
    assert r.status_code == 200, r.text
    # A missed video disc parks on its card, blocked until it is identified.
    assert r.json()["status"] == "awaiting_review"
    assert r.json()["metadata_json"]["flags"]["blocked_miss"] is True
    # The column's server default, which the fake session does not apply.
    db.rows["jobs"][0].resumed_from_crash = False
    return str(r.json()["id"])


def _tracks(db: FakeSession, job_id: str) -> dict[str, Track]:
    return {t.source_ref: t for t in db.rows.get("tracks", []) if t.job_id == job_id}


def test_a_searched_match_with_the_review_gate_on_parks_for_review_with_its_titles() -> None:
    db = _db(hold_for_review=True)
    app, auth = _make_app(db, dispatcher=_Dispatcher(None), hub=_Hub())
    with TestClient(app) as client:
        job_id = _identify_miss(client, db, _scan_dict())
        r = client.post(f"/api/jobs/{job_id}/resolve", json=_RESOLVE, headers=auth)
    assert r.status_code == 200, r.text
    job = db.rows["jobs"][0]
    assert r.json()["job"]["status"] == "awaiting_review"
    assert job.wait_start_time is not None
    tracks = _tracks(db, job_id)
    assert tracks and any(not t.excluded for t in tracks.values())


def test_a_searched_match_while_paused_parks_for_review_with_no_countdown() -> None:
    db = _db(hold_for_review=True, ripping_paused=True)
    app, auth = _make_app(db, dispatcher=_Dispatcher(None), hub=_Hub())
    with TestClient(app) as client:
        job_id = _identify_miss(client, db, _scan_dict())
        r = client.post(f"/api/jobs/{job_id}/resolve", json=_RESOLVE, headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["job"]["status"] == "awaiting_review"
    assert db.rows["jobs"][0].wait_start_time is None


def test_a_searched_match_with_the_review_gate_off_stays_on_its_card_for_start() -> None:
    """A missed video disc already shows its card (#645): identified there, it waits for Start with no countdown."""
    db = _db(hold_for_review=False)
    app, auth = _make_app(db, dispatcher=_Dispatcher(None), hub=_Hub())
    with TestClient(app) as client:
        job_id = _identify_miss(client, db, _scan_dict())
        r = client.post(f"/api/jobs/{job_id}/resolve", json=_RESOLVE, headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["job"]["status"] == "awaiting_review"
    assert r.json()["job"]["metadata_json"]["flags"]["blocked_miss"] is False
    assert db.rows["jobs"][0].wait_start_time is None


@pytest.mark.parametrize("ripping_paused", [False, True])
def test_review_titles_persisted_after_makemkvs_titles_arrived_follow_the_title_map(ripping_paused: bool) -> None:
    db = _db(hold_for_review=True, ripping_paused=ripping_paused)
    app, auth = _make_app(db, dispatcher=_Dispatcher(None), hub=_Hub())
    scan: ScanResult = br3d_structure_scan()
    titles = [t.model_dump(mode="json") for t in br3d_makemkv_titles() if t.source_file != "00102.mpls"]
    with TestClient(app) as client:
        job_id = _identify_miss(client, db, scan.model_dump(mode="json"))
        r = client.post(f"/api/ripper/jobs/{job_id}/titles", json={"titles": titles}, headers=_OWNER_HEADERS)
        assert r.status_code == 204, r.text
        r = client.post(f"/api/jobs/{job_id}/resolve", json=_RESOLVE, headers=auth)
    assert r.status_code == 200, r.text
    tracks = _tracks(db, job_id)
    # MakeMKV did not list 00102.mpls: the card shows it unticked, as a disc held at identify would after the map.
    assert tracks[EXTRA].excluded is True
    assert tracks[PICK].excluded is False
