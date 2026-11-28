"""The job detail's title facts for the review card: whether MakeMKV's titles are in, which tracks it cannot
rip and which are 3D."""

from __future__ import annotations

import secrets
from typing import Any

import pytest
from fastapi.testclient import TestClient

from arm_backend.job_failure import scan_failure_text
from arm_backend.track_selection import select_tracks_for_review
from arm_common import DiscType, JobStatus, TrackStatus
from arm_common.schemas import ScanFailure, ScanResult
from tests._fakes import FakeSession
from tests.bd_structure_scans import EXTRA, OTHER_ANGLE, PICK, SUBSET, br3d_makemkv_titles, br3d_structure_scan
from tests.test_jobs_router import _auth, _job, _make_app
from tests.test_ripper_router import _movie_preset

JOB_ID = "job_01JZXR7K3M5Q8N4VWA00000001"


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _detail(signing_key: bytes, scan: ScanResult, *, extra_meta: dict[str, Any] | None = None) -> dict[str, Any]:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    job = _job(
        JOB_ID,
        status=JobStatus.AWAITING_REVIEW,
        meta={"scan_result": scan.model_dump(mode="json"), **(extra_meta or {})},
    )
    job.disc_type = DiscType.BLURAY
    db.rows["jobs"] = [job]
    tracks = select_tracks_for_review(JOB_ID, scan, _movie_preset())
    for n, track in enumerate(tracks):
        track.id, track.status, track.attempts = f"trk_{n}", TrackStatus.QUEUED, 0
    db.rows["tracks"] = tracks
    with TestClient(app) as client:
        r = client.get(f"/api/jobs/{JOB_ID}", headers=_auth(token))
    assert r.status_code == 200, r.text
    body: dict[str, Any] = r.json()
    return body


def _by_ref(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {t["source_ref"]: t for t in body["tracks"]}


def test_a_structure_scan_without_makemkvs_titles_is_pending(signing_key: bytes) -> None:
    body = _detail(signing_key, br3d_structure_scan())
    assert body["titles_read"] == {"state": "pending", "failure": None, "message": None}
    assert not any(t["unrippable"] for t in body["tracks"])


def test_a_makemkv_failure_is_reported_with_its_reason(signing_key: bytes) -> None:
    failure = ScanFailure(reason="timed_out", detail="makemkv timed out")  # type: ignore[arg-type]
    body = _detail(signing_key, br3d_structure_scan(), extra_meta={"makemkv_failure": failure.model_dump(mode="json")})
    assert body["titles_read"]["state"] == "failed"
    assert body["titles_read"]["failure"]["reason"] == "timed_out"
    assert body["titles_read"]["message"] == scan_failure_text(failure)


def test_titles_in_and_a_playlist_makemkv_does_not_list_is_unrippable(signing_key: bytes) -> None:
    scan = br3d_structure_scan().model_copy(
        update={"titles": [t for t in br3d_makemkv_titles() if t.source_file != "00102.mpls"]}
    )
    body = _detail(signing_key, scan)
    assert body["titles_read"] == {"state": "ready", "failure": None, "message": None}
    tracks = _by_ref(body)
    assert tracks[EXTRA]["unrippable"] is True
    assert not any(tracks[ref]["unrippable"] for ref in (PICK, OTHER_ANGLE, SUBSET))


def test_the_3d_playlists_are_marked(signing_key: bytes) -> None:
    tracks = _by_ref(_detail(signing_key, br3d_structure_scan()))
    assert [tracks[ref]["stereo_3d"] for ref in (EXTRA, PICK, OTHER_ANGLE, SUBSET)] == [False, True, True, True]


def test_a_job_without_a_structure_scan_is_ready_with_nothing_flagged(signing_key: bytes) -> None:
    db = FakeSession()
    app, token = _make_app(signing_key, db)
    db.rows["jobs"] = [_job(JOB_ID, status=JobStatus.AWAITING_REVIEW)]
    db.rows["tracks"] = []
    with TestClient(app) as client:
        body = client.get(f"/api/jobs/{JOB_ID}", headers=_auth(token)).json()
    assert body["titles_read"] == {"state": "ready", "failure": None, "message": None}
