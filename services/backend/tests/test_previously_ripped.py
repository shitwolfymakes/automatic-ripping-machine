"""on_previously_ripped (D-132): a disc whose fingerprint matches an earlier rip
is held for the operator, rejected (ejected), or ripped again.

Covers identify's three modes and the one-shot "Rip again" override, the held
job surviving a ripper restart, the drive notice lifecycle, the jobs-router
endpoints (detail previous_rip, rip-again, review-pause) and the config PATCH.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import pytest  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.metadata.base import MetadataResult  # noqa: E402
from arm_backend.routers import config as config_router  # noqa: E402
from arm_backend.routers import jobs as jobs_router  # noqa: E402
from arm_backend.routers import ripper as ripper_router  # noqa: E402
from arm_backend.seeders import CONFIG_SINGLETON_ID  # noqa: E402
from arm_common import (  # noqa: E402
    Config,
    DiscFingerprint,
    DiscType,
    Drive,
    DriveMediaStatus,
    DriveStatus,
    Job,
    JobStatus,
    MediaType,
    PreviouslyRippedAction,
    RetentionPolicy,
    RipPreset,
    TrackStatus,
    TranscodeTask,
    TranscodeTaskStatus,
    User,
)
from arm_common.enums import IdentificationMode, OutputMode, TrackKind, TrackSelection  # noqa: E402
from arm_common.models import Track  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402

_SERVICE_AUTH = {"Authorization": "Bearer tok-service"}
_PRIOR = "job_01M4Q4V53S8AC69YM5CKHE11DX"
_SUGGESTION = {
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
_FP = {"algo": "matrix256", "value": "79eea299"}


class _Hub:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def emit(
        self,
        topic: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        persist: bool = True,
        job_id: str | None = None,
        track_id: str | None = None,
        session: Any = None,
    ) -> None:
        self.events.append({"topic": topic, "event_type": event_type, "payload": payload, "job_id": job_id})


class _Dispatcher:
    last_attempts: list[dict[str, Any]] = []

    def __init__(self, result: MetadataResult | None) -> None:
        self.result = result

    async def identify(self, _scan: Any, _cfg: Any, **_kw: Any) -> MetadataResult | None:
        return self.result


def _config(
    action: PreviouslyRippedAction,
    *,
    hold_for_review: bool = False,
    block_on_miss: bool = True,
    movie_auto_apply: bool = True,
) -> Config:
    return Config(
        id=CONFIG_SINGLETON_ID,
        auto_transcode_on_idle=False,
        auto_rip_on_insert=True,
        block_on_miss=block_on_miss,
        movie_auto_apply=movie_auto_apply,
        hold_for_review=hold_for_review,
        ripping_paused=False,
        thediscdb_enabled=False,
        manual_wait_seconds=60,
        on_previously_ripped=action,
        default_retention_policy=RetentionPolicy.PRUNE_AFTER_SESSION,
        notification_apprise_urls=[],
        notifications_enabled=False,
    )


def _drive(drive_id: str = "drv_new") -> Drive:
    return Drive(id=drive_id, hostname=f"host-{drive_id}", device_path="/dev/sr1", status=DriveStatus.ONLINE)


def _prior(status: JobStatus = JobStatus.RIPPED, meta: dict[str, Any] | None = None) -> Job:
    """The earlier rip, on another drive."""
    return Job(
        id=_PRIOR,
        drive_id="drv_old",
        disc_type=DiscType.BLURAY,
        title="Resident Evil: Retribution",
        year=2012,
        status=status,
        ripped_at=datetime(2026, 10, 12, 6, 35, tzinfo=timezone.utc),
        metadata_json=meta or {},
        resumed_from_crash=False,
    )


def _preset() -> RipPreset:
    return RipPreset(
        id="rpr_builtin_movie_archive",
        name="Movie archive",
        media_type=MediaType.MOVIE,
        is_builtin=True,
        track_selection=TrackSelection.ALL_TRACKS,
        identification_mode=IdentificationMode.SKIP,
        output_mode=OutputMode.TRACKS,
    )


def _db(action: PreviouslyRippedAction, *, prior: Job | None = None, **cfg: Any) -> FakeSession:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(action, **cfg)]
    db.rows["rip_presets"] = [_preset()]
    db.rows["jobs"] = [prior or _prior()]
    db.rows["disc_fingerprints"] = [DiscFingerprint(job_id=_PRIOR, algo=_FP["algo"], value=_FP["value"])]
    return db


def _identify(db: FakeSession, hub: _Hub, *, miss: bool = False) -> Any:
    app = FastAPI()
    app.state.signing_key = secrets.token_bytes(32)
    app.state.dispatcher = _Dispatcher(
        None if miss else MetadataResult(title="Resident Evil", year=2012, kind="movie", payload={})
    )
    app.state.ws_hub = hub
    app.include_router(ripper_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    scan = {
        "disc_type": "bluray",
        "volume_label": "RESIDENT_EVIL_RETRIBUTION",
        "titles": [{"index": 0, "duration_seconds": 5700}],
        "fingerprints": [_FP],
        "raw": {},
    }
    with TestClient(app) as client:
        return client.post(
            "/api/ripper/identify", json={"drive_id": "drv_new", "scan_result": scan}, headers=_SERVICE_AUTH
        )


def _new_jobs(db: FakeSession) -> list[Job]:
    return [r for r in db.added if isinstance(r, Job) and r.id != _PRIOR]


# --- identify -----------------------------------------------------------------


@pytest.mark.parametrize("status", [JobStatus.RIPPED, JobStatus.RIPPED_PARTIAL])
def test_hold_parks_a_disc_ripped_on_another_drive_with_no_countdown(status: JobStatus) -> None:
    db = _db(PreviouslyRippedAction.HOLD, prior=_prior(status))
    hub = _Hub()
    r = _identify(db, hub)
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "awaiting_review"
    assert out["wait_start_time"] is None  # the ripper never auto-starts it
    assert out["metadata_json"]["previously_ripped"] == {"job_id": _PRIOR}
    held = [e for e in hub.events if e["event_type"] == "rip.awaiting_review"]
    assert held and held[0]["payload"]["previous_job_id"] == _PRIOR
    # The review card lists the disc's titles, as with hold_for_review.
    assert [t for t in db.added if isinstance(t, Track)]


def test_hold_overrides_the_timed_review_and_a_missed_identify() -> None:
    db = _db(PreviouslyRippedAction.HOLD, hold_for_review=True)
    r = _identify(db, _Hub())
    assert r.json()["status"] == "awaiting_review"
    assert r.json()["wait_start_time"] is None

    # Without the earlier rip this miss would park at awaiting_user_id.
    missed = _db(PreviouslyRippedAction.HOLD, block_on_miss=True)
    out = _identify(missed, _Hub(), miss=True).json()
    assert out["status"] == "awaiting_review"
    assert out["title"] == "RESIDENT_EVIL_RETRIBUTION"


def test_hold_still_wins_over_a_held_suggestion() -> None:
    """on_previously_ripped=hold + auto-apply off: one AWAITING_REVIEW hold
    carrying both the previously_ripped reason and the suggestion."""
    db = _db(PreviouslyRippedAction.HOLD, movie_auto_apply=False)
    out = _identify(db, _Hub()).json()
    assert out["status"] == "awaiting_review"
    assert out["wait_start_time"] is None
    assert out["metadata_json"]["previously_ripped"]["job_id"] == _PRIOR
    assert out["metadata_json"]["identity_suggestion"]["title"] == "Resident Evil"
    tracks = {id(t) for t in db.added if isinstance(t, Track)}
    assert len(tracks) == 1  # persisted once, not twice


def test_a_failed_or_abandoned_earlier_job_is_not_a_previous_rip() -> None:
    for status in (JobStatus.FAILED, JobStatus.ABANDONED):
        db = _db(PreviouslyRippedAction.HOLD, prior=_prior(status))
        r = _identify(db, _Hub())
        assert r.json()["status"] == "identified"
        assert "previously_ripped" not in r.json()["metadata_json"]


def test_reject_creates_no_job_records_the_event_and_notes_the_drive() -> None:
    db = _db(PreviouslyRippedAction.REJECT)
    hub = _Hub()
    r = _identify(db, hub)
    assert r.status_code == 409
    assert r.json()["detail"] == {"reason": "previously_ripped", "job_id": _PRIOR}
    assert _new_jobs(db) == []
    rejected = [e for e in hub.events if e["event_type"] == "rip.duplicate_rejected"]
    assert len(rejected) == 1
    # Filed against the earlier rip, so the inbox entry names and links it.
    assert rejected[0]["job_id"] == _PRIOR
    assert rejected[0]["payload"]["drive_id"] == "drv_new"
    drive = db.rows["drives"][0]
    assert drive.notice == "Ejected a disc already ripped as Resident Evil: Retribution on 2026-10-12."
    assert db.committed


def test_rip_mode_rips_it_again_without_asking() -> None:
    db = _db(PreviouslyRippedAction.RIP)
    r = _identify(db, _Hub())
    assert r.status_code == 200
    assert r.json()["status"] == "identified"
    assert "previously_ripped" not in r.json()["metadata_json"]


@pytest.mark.parametrize("action", [PreviouslyRippedAction.HOLD, PreviouslyRippedAction.REJECT])
def test_rip_again_lets_the_next_identify_through_once(action: PreviouslyRippedAction) -> None:
    prior = _prior(meta={"flags": {"rerip_allowed": True}})
    db = _db(action, prior=prior)
    r = _identify(db, _Hub())
    assert r.status_code == 200
    assert r.json()["status"] == "identified"
    assert prior.metadata_json["flags"]["rerip_allowed"] is False  # used up

    # That job is abandoned (else the next scan would just reuse it); the disc
    # goes in again and is checked again.
    _new_jobs(db)[0].status = JobStatus.ABANDONED
    again = _identify(db, _Hub())
    assert again.status_code == (200 if action is PreviouslyRippedAction.HOLD else 409)
    if action is PreviouslyRippedAction.HOLD:
        assert again.json()["status"] == "awaiting_review"


_NEWER = "job_01M4Q9V53S8AC69YM5CKHE11DX"


def _newer_rip(db: FakeSession) -> Job:
    """A later rip of the same disc, so the job the operator clicked is not the newest."""
    newer = Job(
        id=_NEWER,
        drive_id="drv_old",
        disc_type=DiscType.BLURAY,
        title="Resident Evil: Retribution",
        status=JobStatus.RIPPED,
        metadata_json={},
        resumed_from_crash=False,
    )
    db.rows["jobs"].append(newer)
    db.rows["disc_fingerprints"].append(DiscFingerprint(job_id=_NEWER, algo=_FP["algo"], value=_FP["value"]))
    return newer


@pytest.mark.parametrize("action", [PreviouslyRippedAction.HOLD, PreviouslyRippedAction.REJECT])
def test_rip_again_on_an_older_rip_of_the_disc_lets_it_through(action: PreviouslyRippedAction) -> None:
    prior = _prior(meta={"flags": {"rerip_allowed": True}})
    db = _db(action, prior=prior)
    _newer_rip(db)
    r = _identify(db, _Hub())
    assert r.status_code == 200
    assert r.json()["status"] == "identified"
    assert prior.metadata_json["flags"]["rerip_allowed"] is False  # used up, not left to fire later


def test_identify_clears_the_drive_notice_for_a_new_disc() -> None:
    db = _db(PreviouslyRippedAction.HOLD)
    db.rows["disc_fingerprints"] = []  # a different disc
    db.rows["drives"][0].notice = "Ejected a disc already ripped as X."
    assert _identify(db, _Hub()).status_code == 200
    assert db.rows["drives"][0].notice is None


# --- ripper restart and the drive notice ---------------------------------------


def _ripper_app(db: FakeSession) -> FastAPI:
    app = FastAPI()
    app.state.signing_key = secrets.token_bytes(32)
    app.state.ws_hub = _Hub()
    app.include_router(ripper_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    return app


def test_a_previously_ripped_hold_survives_a_ripper_restart() -> None:
    db = _db(PreviouslyRippedAction.HOLD)
    db.rows["jobs"].append(
        Job(
            id="job_01M4R7157QDCVQ3MX6M2VK0XX0",
            drive_id="drv_new",
            disc_type=DiscType.BLURAY,
            status=JobStatus.AWAITING_REVIEW,
            metadata_json={"previously_ripped": {"job_id": _PRIOR}},
            resumed_from_crash=False,
        )
    )
    with TestClient(_ripper_app(db)) as client:
        r = client.get("/api/ripper/drives/drv_new/held-job", headers=_SERVICE_AUTH)
    assert r.status_code == 200
    assert r.json()["paused"] is True  # re-parked, never abandoned and re-scanned


@pytest.mark.parametrize(
    ("before", "media_status", "kept"),
    [
        (DriveMediaStatus.LOADED, DriveMediaStatus.TRAY_OPEN, True),  # the eject
        (DriveMediaStatus.TRAY_OPEN, DriveMediaStatus.TRAY_OPEN, True),
        (DriveMediaStatus.TRAY_OPEN, DriveMediaStatus.LOADED, True),
        (DriveMediaStatus.TRAY_OPEN, DriveMediaStatus.NO_DISC, False),  # closed empty
        # A slot-loading drive reads "no disc" straight after the eject: keep it.
        (DriveMediaStatus.LOADED, DriveMediaStatus.NO_DISC, True),
    ],
)
def test_the_drive_notice_lasts_until_the_tray_closes_empty(
    before: DriveMediaStatus, media_status: DriveMediaStatus, kept: bool
) -> None:
    db = _db(PreviouslyRippedAction.REJECT)
    db.rows["drives"][0].notice = "Ejected a disc already ripped as X."
    db.rows["drives"][0].media_status = before
    with TestClient(_ripper_app(db)) as client:
        r = client.post(
            "/api/ripper/heartbeat",
            json={"drive_id": "drv_new", "media_status": media_status.value},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 204
    assert (db.rows["drives"][0].notice is not None) is kept


# --- jobs router ----------------------------------------------------------------


def _jobs_app(db: FakeSession, hub: _Hub) -> tuple[TestClient, dict[str, str]]:
    key = secrets.token_bytes(32)
    app = FastAPI()
    app.state.signing_key = key
    app.state.ws_hub = hub
    app.include_router(jobs_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    db.rows.setdefault("users", []).append(
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)
    )
    token, _ = issue_access_token("usr_admin", "admin", key)
    return TestClient(app), {"Authorization": f"Bearer {token}"}


def _held(job_id: str = "job_01M4R7CH6DK8PA8MPD79PATMPD") -> Job:
    return Job(
        id=job_id,
        drive_id="drv_new",
        disc_type=DiscType.BLURAY,
        title="Resident Evil: Retribution",
        status=JobStatus.AWAITING_REVIEW,
        metadata_json={"previously_ripped": {"job_id": _PRIOR}},
        resumed_from_crash=False,
    )


def _done_task(track_id: str, output_path: str) -> TranscodeTask:
    return TranscodeTask(
        id=f"tt_{track_id}",
        session_application_id="sap_1",
        source_track_id=track_id,
        status=TranscodeTaskStatus.DONE,
        output_path=output_path,
    )


def test_job_detail_describes_the_earlier_rip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(jobs_router.settings, "MEDIA_ROOT", str(tmp_path))
    (tmp_path / "Movies").mkdir()
    (tmp_path / "Movies" / "a.mkv").write_bytes(b"x")
    db = _db(PreviouslyRippedAction.HOLD)
    db.rows["jobs"].append(_held())
    db.rows["tracks"] = [
        Track(id="trk_1", job_id=_PRIOR, kind=TrackKind.VIDEO_TITLE, index=0, source_ref="0", status=TrackStatus.DONE),
        Track(id="trk_2", job_id=_PRIOR, kind=TrackKind.VIDEO_TITLE, index=1, source_ref="1", status=TrackStatus.DONE),
    ]
    db.rows["transcode_tasks"] = [_done_task("trk_1", "Movies/a.mkv")]
    client, auth = _jobs_app(db, _Hub())
    with client:
        r = client.get("/api/jobs/job_01M4R7CH6DK8PA8MPD79PATMPD", headers=auth)
        assert r.status_code == 200
        prev = r.json()["previous_rip"]
        assert prev["job_id"] == _PRIOR
        assert prev["status"] == "ripped"
        assert prev["ripped_at"].startswith("2026-10-12")
        assert prev["outputs_present"] is True

        db.rows["transcode_tasks"].append(_done_task("trk_2", "Movies/gone.mkv"))
        assert (
            client.get("/api/jobs/job_01M4R7CH6DK8PA8MPD79PATMPD", headers=auth).json()["previous_rip"][
                "outputs_present"
            ]
            is False
        )

        db.rows["jobs"] = [j for j in db.rows["jobs"] if j.id != _PRIOR]  # earlier job deleted
        assert client.get("/api/jobs/job_01M4R7CH6DK8PA8MPD79PATMPD", headers=auth).json()["previous_rip"] is None


def test_rip_again_starts_a_held_copy_of_the_disc() -> None:
    db = _db(PreviouslyRippedAction.HOLD)
    held = _held()
    db.rows["jobs"].append(held)
    hub = _Hub()
    client, auth = _jobs_app(db, hub)
    with client:
        r = client.post(f"/api/jobs/{_PRIOR}/rip-again", headers=auth)
    assert r.status_code == 200
    assert r.json() == {"started_job_id": held.id, "armed": False}
    assert held.status == JobStatus.RIPPING
    assert any(e["event_type"] == "rip.start" and e["topic"] == "ripper.commands.drv_new" for e in hub.events)


def test_rip_again_on_an_older_rip_starts_the_copy_held_against_a_newer_one() -> None:
    db = _db(PreviouslyRippedAction.HOLD)
    _newer_rip(db)
    held = _held()
    held.metadata_json = {"previously_ripped": {"job_id": _NEWER}}
    db.rows["jobs"].append(held)
    db.rows["disc_fingerprints"].append(DiscFingerprint(job_id=held.id, algo=_FP["algo"], value=_FP["value"]))
    client, auth = _jobs_app(db, _Hub())
    with client:
        r = client.post(f"/api/jobs/{_PRIOR}/rip-again", headers=auth)
    assert r.status_code == 200
    assert r.json() == {"started_job_id": held.id, "armed": False}
    assert held.status == JobStatus.RIPPING


def test_rip_again_leaves_a_held_copy_of_another_disc_alone() -> None:
    db = _db(PreviouslyRippedAction.HOLD)
    other = _held()
    other.metadata_json = {"previously_ripped": {"job_id": "job_01M4Q2V53S8AC69YM5CKHE11DX"}}
    db.rows["jobs"].append(other)
    db.rows["disc_fingerprints"].append(DiscFingerprint(job_id=other.id, algo="matrix256", value="0ther"))
    client, auth = _jobs_app(db, _Hub())
    with client:
        r = client.post(f"/api/jobs/{_PRIOR}/rip-again", headers=auth)
    assert r.json() == {"started_job_id": None, "armed": True}
    assert other.status == JobStatus.AWAITING_REVIEW


def test_rip_again_arms_the_next_identify_when_nothing_is_held() -> None:
    db = _db(PreviouslyRippedAction.REJECT)
    client, auth = _jobs_app(db, _Hub())
    with client:
        r = client.post(f"/api/jobs/{_PRIOR}/rip-again", headers=auth)
    assert r.status_code == 200
    assert r.json() == {"started_job_id": None, "armed": True}
    assert db.rows["jobs"][0].metadata_json["flags"]["rerip_allowed"] is True


def test_rip_again_needs_a_ripped_job() -> None:
    db = _db(PreviouslyRippedAction.HOLD, prior=_prior(JobStatus.FAILED))
    client, auth = _jobs_app(db, _Hub())
    with client:
        assert client.post(f"/api/jobs/{_PRIOR}/rip-again", headers=auth).status_code == 409
        assert client.post("/api/jobs/job_01M4R7CH6DK8PA8MPD79PATMP0/rip-again", headers=auth).status_code == 404


def test_a_previously_ripped_hold_has_no_countdown_to_pause() -> None:
    db = _db(PreviouslyRippedAction.HOLD)
    db.rows["jobs"].append(_held())
    client, auth = _jobs_app(db, _Hub())
    with client:
        r = client.post("/api/jobs/job_01M4R7CH6DK8PA8MPD79PATMPD/review-pause?paused=false", headers=auth)
    assert r.status_code == 409
    assert db.rows["jobs"][1].wait_start_time is None


# --- config ---------------------------------------------------------------------


def _config_client(db: FakeSession) -> tuple[TestClient, dict[str, str]]:
    key = secrets.token_bytes(32)
    app = FastAPI()
    app.state.signing_key = key
    app.include_router(config_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    db.rows.setdefault("users", []).append(
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)
    )
    token, _ = issue_access_token("usr_admin", "admin", key)
    return TestClient(app), {"Authorization": f"Bearer {token}"}


def test_config_round_trips_on_previously_ripped() -> None:
    db = _db(PreviouslyRippedAction.HOLD)
    client, auth = _config_client(db)
    with client:
        assert client.get("/api/config", headers=auth).json()["on_previously_ripped"] == "hold"
        r = client.patch("/api/config", json={"on_previously_ripped": "reject"}, headers=auth)
        assert r.status_code == 200
        assert r.json()["on_previously_ripped"] == "reject"
        assert client.patch("/api/config", json={"on_previously_ripped": "sometimes"}, headers=auth).status_code == 422
        assert client.patch("/api/config", json={"on_previously_ripped": None}, headers=auth).status_code == 400


def test_unpausing_does_not_start_a_countdown_on_a_previously_ripped_hold() -> None:
    db = _db(PreviouslyRippedAction.HOLD)
    db.rows["config"][0].ripping_paused = True
    held = _held()
    db.rows["jobs"].append(held)
    client, auth = _config_client(db)
    with client:
        assert client.patch("/api/config", json={"ripping_paused": False}, headers=auth).status_code == 200
    assert held.wait_start_time is None


def test_unpausing_does_not_start_a_countdown_on_a_suggestion_hold() -> None:
    db = _db(PreviouslyRippedAction.HOLD)
    db.rows["config"][0].ripping_paused = True
    suggested = _held("job_01M4R7CH6DK8PA8MPD79PATMPS")
    suggested.metadata_json = {"identity_suggestion": _SUGGESTION, "flags": {"unidentified": True}}
    plain = _held("job_01M4R7CH6DK8PA8MPD79PATMPP")
    plain.metadata_json = {}
    db.rows["jobs"].extend([suggested, plain])
    client, auth = _config_client(db)
    with client:
        assert client.patch("/api/config", json={"ripping_paused": False}, headers=auth).status_code == 200
    assert suggested.wait_start_time is None
    assert plain.wait_start_time is not None
