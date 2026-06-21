"""Ripper router endpoint coverage: config, identify, get_job, in-flight-job,
rip-start, update-track state machine, rip-complete. Fake-session + mocked
dispatcher/hub, service-token and drive-owner auth.

(register/heartbeat/resume/min-length are covered by their own modules;
register's pg_insert path is not Fake-session-expressible and is left to the
real-DB e2e tier.)
"""

from __future__ import annotations

import asyncio
import os
import secrets
from datetime import datetime, timezone
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import pytest  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.metadata.base import MetadataResult  # noqa: E402
from arm_backend.routers import ripper as ripper_router  # noqa: E402
from arm_common import (  # noqa: E402
    Config,
    DiscType,
    Drive,
    DriveStatus,
    Job,
    JobStatus,
    MediaType,
    RetentionPolicy,
    RipPreset,
    TrackStatus,
)
from arm_common.enums import IdentificationMode, OutputMode, TrackKind, TrackSelection  # noqa: E402
from arm_common.models import Track  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402

_HOSTNAME = "ripper-host"
_SERVICE_AUTH = {"Authorization": "Bearer tok-service"}
_OWNER_HEADERS = {"Authorization": "Bearer tok-service", "X-ARM-Hostname": _HOSTNAME}


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
        self.events.append({"event_type": event_type, "payload": payload})


class _Dispatcher:
    """Mock MetadataDispatcher. `result` is returned from identify; set
    `raise_timeout` to simulate the asyncio.wait_for timeout path."""

    def __init__(self, result: MetadataResult | None = None, *, raise_timeout: bool = False) -> None:
        self.result = result
        self.raise_timeout = raise_timeout

    async def identify(self, _scan: Any, _cfg: Any) -> MetadataResult | None:
        if self.raise_timeout:
            raise asyncio.TimeoutError
        return self.result


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


def _make_app(
    db: FakeSession,
    *,
    dispatcher: _Dispatcher | None = None,
    hub: _Hub | None = None,
) -> FastAPI:
    app = FastAPI()
    app.state.signing_key = secrets.token_bytes(32)
    app.state.dispatcher = dispatcher or _Dispatcher()
    app.state.ws_hub = hub or _Hub()
    app.include_router(ripper_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    return app


def _config(
    *,
    block_on_miss: bool = True,
    community_keydb_enabled: bool = True,
    hold_for_review: bool = False,
    ripping_paused: bool = False,
) -> Config:
    return Config(
        id=1,
        auto_transcode_on_idle=False,
        auto_rip_on_insert=True,
        block_on_miss=block_on_miss,
        community_keydb_enabled=community_keydb_enabled,
        hold_for_review=hold_for_review,
        ripping_paused=ripping_paused,
        manual_wait_seconds=60,
        default_retention_policy=RetentionPolicy.PRUNE_AFTER_SESSION,
    )


def _drive() -> Drive:
    return Drive(id="drv_x", hostname=_HOSTNAME, device_path="/dev/sr0", status=DriveStatus.ONLINE)


def _job(
    job_id: str = "job_01JZXR7K3M5Q8N4VWA00000001",
    *,
    status: JobStatus,
    disc_type: DiscType = DiscType.DVD,
    meta: dict | None = None,
) -> Job:
    return Job(
        id=job_id,
        drive_id="drv_x",
        disc_type=disc_type,
        title="X",
        year=2000,
        status=status,
        metadata_json=meta if meta is not None else {},
        resumed_from_crash=False,
    )


def _track(
    track_id: str, *, status: TrackStatus, job_id: str = "job_01JZXR7K3M5Q8N4VWA00000001", index: int = 1
) -> Track:
    return Track(
        id=track_id,
        job_id=job_id,
        kind=TrackKind.VIDEO_TITLE,
        index=index,
        source_ref=str(index),
        status=status,
        attempts=0,
    )


def _movie_preset(preset_id: str = "rpr_builtin_movie_archive") -> RipPreset:
    return RipPreset(
        id=preset_id,
        name="Movie archive",
        media_type=MediaType.MOVIE,
        is_builtin=True,
        track_selection=TrackSelection.ALL_TRACKS,
        identification_mode=IdentificationMode.SKIP,
        output_mode=OutputMode.TRACKS,
    )


def _scan_dict(disc_type: str = "dvd") -> dict[str, Any]:
    return {
        "disc_type": disc_type,
        "volume_label": "MY_DISC",
        "titles": [{"index": 1, "duration_seconds": 4200}],
        "fingerprints": [],
        "raw": {},
    }


# --- /config -----------------------------------------------------------------


def test_get_config_returns_flag() -> None:
    db = FakeSession()
    db.rows["config"] = [_config()]
    with TestClient(_make_app(db)) as client:
        r = client.get("/api/ripper/config", headers=_SERVICE_AUTH)
    assert r.status_code == 200
    assert r.json() == {
        "auto_rip_on_insert": True,
        "makemkv_key": None,
        "community_keydb_enabled": True,
        "ripping_paused": False,
        "manual_wait_seconds": 60,
    }


def test_get_config_reflects_community_keydb_disabled() -> None:
    db = FakeSession()
    db.rows["config"] = [_config(community_keydb_enabled=False)]
    with TestClient(_make_app(db)) as client:
        r = client.get("/api/ripper/config", headers=_SERVICE_AUTH)
    assert r.status_code == 200
    assert r.json()["community_keydb_enabled"] is False


def test_get_config_includes_makemkv_key() -> None:
    db = FakeSession()
    cfg = _config()
    cfg.makemkv_key = "T-abc123"
    db.rows["config"] = [cfg]
    with TestClient(_make_app(db)) as client:
        r = client.get("/api/ripper/config", headers=_SERVICE_AUTH)
    assert r.status_code == 200
    assert r.json()["makemkv_key"] == "T-abc123"


def test_get_config_missing_singleton_500() -> None:
    db = FakeSession()
    db.rows["config"] = []
    with TestClient(_make_app(db)) as client:
        r = client.get("/api/ripper/config", headers=_SERVICE_AUTH)
    assert r.status_code == 500
    assert "config singleton missing" in r.json()["detail"]


# --- /register ---------------------------------------------------------------


class _RegisterSession(FakeSession):
    """`register` upserts via `pg_insert(...).on_conflict_do_update(...)`,
    which neither FakeSession nor SQLite can compile. Special-case the
    non-Select upsert to return the new drive id; the follow-up
    `select(Drive)` falls through to normal FakeSession behaviour. This
    covers the handler flow; the ON CONFLICT semantics are a Postgres
    concern left to the integration tier."""

    async def execute(self, stmt: Any) -> Any:
        from sqlalchemy.sql import Select

        if not isinstance(stmt, Select):
            self.rows.setdefault("drives", []).append(
                Drive(id="drv_new", hostname=_HOSTNAME, device_path="/dev/sr0", status=DriveStatus.ONLINE)
            )

            class _R:
                @staticmethod
                def scalar_one() -> str:
                    return "drv_new"

            return _R()
        return await super().execute(stmt)


def test_register_upserts_and_returns_drive() -> None:
    db = _RegisterSession()
    body = {
        "hostname": _HOSTNAME,
        "device_path": "/dev/sr0",
        "ripper_version": "3.0.0",
        "hw_caps": {"makemkv": True},
    }
    with TestClient(_make_app(db)) as client:
        r = client.post("/api/ripper/register", json=body, headers=_SERVICE_AUTH)
    assert r.status_code == 200
    assert r.json()["id"] == "drv_new"
    assert r.json()["hostname"] == _HOSTNAME


# --- /identify ---------------------------------------------------------------


def test_identify_unknown_drive_404() -> None:
    db = FakeSession()
    db.rows["drives"] = []
    body = {"drive_id": "drv_missing", "scan_result": _scan_dict()}
    with TestClient(_make_app(db)) as client:
        r = client.post("/api/ripper/identify", json=body, headers=_SERVICE_AUTH)
    assert r.status_code == 404


def test_identify_success_sets_identified_and_poster() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config()]
    result = MetadataResult(title="Iron Man", year=2008, kind="movie", payload={"poster_path": "/abc.jpg"})
    app = _make_app(db, dispatcher=_Dispatcher(result))
    scan = _scan_dict()
    scan["fingerprints"] = [
        {"algo": "crc64", "value": "deadbeef"},
        {"algo": "CRC64", "value": "dup-ignored"},
        {"algo": "", "value": "skip"},
    ]
    body = {"drive_id": "drv_x", "scan_result": scan, "pending_session_id": "ses_1"}
    with TestClient(app) as client:
        r = client.post("/api/ripper/identify", json=body, headers=_SERVICE_AUTH)
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "identified"
    assert out["title"] == "Iron Man"
    assert out["poster_url"] == "https://image.tmdb.org/t/p/w500/abc.jpg"
    assert out["metadata_json"]["pending_session_id"] == "ses_1"
    fps = [r for r in db.added if type(r).__name__ == "DiscFingerprint"]
    assert {f.algo for f in fps} == {"crc64"}  # dedup + empty skipped


def test_identify_with_hold_parks_review(signing_key: bytes) -> None:
    """hold_for_review on + a genuine identify success -> AWAITING_REVIEW with a
    countdown anchor, a rip.awaiting_review event, AND the scan's titles persisted
    as Track rows (every title; preset-rejected ones excluded by default)."""
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(hold_for_review=True)]
    db.rows["rip_presets"] = [_movie_preset()]  # ALL_TRACKS default (drops <60s)
    result = MetadataResult(title="Iron Man", year=2008, kind="movie", payload={})
    hub = _Hub()
    app = _make_app(db, dispatcher=_Dispatcher(result), hub=hub)
    scan = _scan_dict()
    # Two titles: a long feature (kept) + a sub-minlength stub (excluded default).
    scan["titles"] = [
        {"index": 1, "duration_seconds": 4200},
        {"index": 2, "duration_seconds": 5},
    ]
    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/identify",
            json={"drive_id": "drv_x", "scan_result": scan},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "awaiting_review"
    assert out["title"] == "Iron Man"
    assert out["wait_start_time"] is not None
    assert any(e["event_type"] == "rip.awaiting_review" for e in hub.events)
    tracks = [row for row in db.added if type(row).__name__ == "Track"]
    assert {t.source_ref for t in tracks} == {"1", "2"}  # every title persisted
    by_ref = {t.source_ref: t for t in tracks}
    assert by_ref["1"].excluded is False  # main feature kept by default
    assert by_ref["2"].excluded is True  # short extra excluded by default


async def test_persist_review_tracks_is_idempotent() -> None:
    """Idempotency (audit M1): a title whose Track row already exists (ripper
    re-POSTed identify on the same held disc) is NOT re-inserted."""
    from arm_backend.routers.ripper import _persist_review_tracks
    from arm_common import Job as _Job, Track as _Track, TrackKind as _TrackKind
    from arm_common.schemas import ScanResult as _ScanResult, ScanTitle as _ScanTitle

    db = FakeSession()
    db.rows["rip_presets"] = [_movie_preset()]
    job = _Job(
        id="job_01JZXR7K3M5Q8N4VWA0000I01", drive_id="drv_x", disc_type=DiscType.DVD, status=JobStatus.AWAITING_REVIEW
    )
    # Title index 1 already persisted (source_ref "1"); index 2 is new.
    db.rows["tracks"] = [_Track(id="trk_pre", job_id=job.id, kind=_TrackKind.VIDEO_TITLE, index=1, source_ref="1")]
    scan = _ScanResult(
        disc_type=DiscType.DVD,
        titles=[_ScanTitle(index=1, duration_seconds=4200), _ScanTitle(index=2, duration_seconds=3600)],
    )
    await _persist_review_tracks(db, job, scan)
    added_refs = {t.source_ref for t in db.added if type(t).__name__ == "Track"}
    assert added_refs == {"2"}  # index 1 skipped (already exists), only 2 added


def test_identify_with_hold_parks_without_preset_seeded() -> None:
    """hold_for_review on but the default rip preset isn't seeded -> still parks in
    AWAITING_REVIEW (review-track persistence is skipped, logged) rather than
    failing identify."""
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(hold_for_review=True)]
    db.rows["rip_presets"] = []  # not seeded
    result = MetadataResult(title="Iron Man", year=2008, kind="movie", payload={})
    app = _make_app(db, dispatcher=_Dispatcher(result))
    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/identify",
            json={"drive_id": "drv_x", "scan_result": _scan_dict()},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 200
    assert r.json()["status"] == "awaiting_review"
    assert [row for row in db.added if type(row).__name__ == "Track"] == []


def test_identify_with_hold_parks_even_when_paused() -> None:
    """When hold_for_review is on, a paused machine still scans + identifies +
    parks (pause only suppresses auto-start at expiry) — it does NOT 409."""
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(hold_for_review=True, ripping_paused=True)]
    result = MetadataResult(title="Iron Man", year=2008, kind="movie", payload={})
    app = _make_app(db, dispatcher=_Dispatcher(result))
    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/identify",
            json={"drive_id": "drv_x", "scan_result": _scan_dict()},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 200
    assert r.json()["status"] == "awaiting_review"


def test_identify_paused_without_hold_still_409s() -> None:
    """With hold_for_review off, pause keeps its original meaning: reject."""
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(hold_for_review=False, ripping_paused=True)]
    app = _make_app(db, dispatcher=_Dispatcher(None))
    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/identify",
            json={"drive_id": "drv_x", "scan_result": _scan_dict()},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 409


def test_identify_unidentified_with_hold_does_not_park(signing_key: bytes) -> None:
    """hold_for_review on but identify MISSES (block_on_miss off) -> the synthetic
    IDENTIFIED-unidentified must NOT park in review (audit H5: gate on genuine
    success, not status==IDENTIFIED)."""
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(hold_for_review=True, block_on_miss=False)]
    app = _make_app(db, dispatcher=_Dispatcher(None))
    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/identify",
            json={"drive_id": "drv_x", "scan_result": _scan_dict()},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 200
    out = r.json()
    assert out["status"] == "identified"  # not awaiting_review
    assert out["metadata_json"].get("unidentified") is True


def test_identify_miss_with_block_on_miss_awaits_user(signing_key: bytes) -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(block_on_miss=True)]
    hub = _Hub()
    app = _make_app(db, dispatcher=_Dispatcher(None), hub=hub)
    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/identify",
            json={"drive_id": "drv_x", "scan_result": _scan_dict()},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 200
    assert r.json()["status"] == "awaiting_user_id"
    assert r.json()["title"] == "MY_DISC"
    assert any(e["event_type"] == "rip.needs_user_input" for e in hub.events)


def test_identify_miss_without_block_marks_identified_unidentified() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(block_on_miss=False)]
    app = _make_app(db, dispatcher=_Dispatcher(None))
    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/identify",
            json={"drive_id": "drv_x", "scan_result": _scan_dict()},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 200
    assert r.json()["status"] == "identified"
    assert r.json()["metadata_json"]["unidentified"] is True


def test_identify_timeout_records_diagnostic() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(block_on_miss=True)]
    app = _make_app(db, dispatcher=_Dispatcher(raise_timeout=True))
    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/identify",
            json={"drive_id": "drv_x", "scan_result": _scan_dict()},
            headers=_SERVICE_AUTH,
        )
    assert r.status_code == 200
    assert r.json()["status"] == "awaiting_user_id"
    assert r.json()["metadata_json"]["dispatch_timeout"] is True


# --- /jobs/{id} & in-flight --------------------------------------------------


def test_get_job_found_and_404() -> None:
    db = FakeSession()
    db.rows["jobs"] = [_job(status=JobStatus.IDENTIFIED)]
    with TestClient(_make_app(db)) as client:
        found = client.get("/api/ripper/jobs/job_01JZXR7K3M5Q8N4VWA00000001", headers=_SERVICE_AUTH)
        missing = client.get("/api/ripper/jobs/job_01JZXR7K3M5Q8N4VWA0000000M", headers=_SERVICE_AUTH)
    assert found.status_code == 200
    assert found.json()["id"] == "job_01JZXR7K3M5Q8N4VWA00000001"
    assert missing.status_code == 404


def test_in_flight_unknown_drive_404() -> None:
    db = FakeSession()
    db.rows["drives"] = []
    with TestClient(_make_app(db)) as client:
        r = client.get("/api/ripper/drives/drv_x/in-flight-job", headers=_SERVICE_AUTH)
    assert r.status_code == 404
    assert "unknown drive_id" in r.json()["detail"]


def test_in_flight_no_job_404() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["jobs"] = [_job(status=JobStatus.IDENTIFIED)]
    with TestClient(_make_app(db)) as client:
        r = client.get("/api/ripper/drives/drv_x/in-flight-job", headers=_SERVICE_AUTH)
    assert r.status_code == 404
    assert "no in-flight job" in r.json()["detail"]


def test_in_flight_single_returns_job() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["jobs"] = [_job("job_01JZXR7K3M5Q8N4VWA00000002", status=JobStatus.RIPPING)]
    with TestClient(_make_app(db)) as client:
        r = client.get("/api/ripper/drives/drv_x/in-flight-job", headers=_SERVICE_AUTH)
    assert r.status_code == 200
    assert r.json()["id"] == "job_01JZXR7K3M5Q8N4VWA00000002"


def test_in_flight_single_and_multi(caplog: pytest.LogCaptureFixture) -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["jobs"] = [
        _job("job_01JZXR7K3M5Q8N4VWA00000002", status=JobStatus.RIPPING),
        _job("job_01JZXR7K3M5Q8N4VWA00000003", status=JobStatus.RIPPING),
    ]
    with TestClient(_make_app(db)) as client:
        with caplog.at_level("ERROR", logger="arm_backend.routers.ripper"):
            r = client.get("/api/ripper/drives/drv_x/in-flight-job", headers=_SERVICE_AUTH)
    assert r.status_code == 200
    assert r.json()["id"] == "job_01JZXR7K3M5Q8N4VWA00000002"
    assert any("data-model violation" in rec.message for rec in caplog.records)


# --- /held-job + /recovery-abandon (timed review gate reboot recovery) --------


def test_held_job_unknown_drive_404() -> None:
    db = FakeSession()
    db.rows["drives"] = []
    with TestClient(_make_app(db)) as client:
        r = client.get("/api/ripper/drives/drv_x/held-job", headers=_SERVICE_AUTH)
    assert r.status_code == 404
    assert "unknown drive_id" in r.json()["detail"]


def test_held_job_none_404() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["jobs"] = [_job(status=JobStatus.RIPPING)]
    with TestClient(_make_app(db)) as client:
        r = client.get("/api/ripper/drives/drv_x/held-job", headers=_SERVICE_AUTH)
    assert r.status_code == 404
    assert "no held job" in r.json()["detail"]


def test_held_job_returns_job_unpaused() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(ripping_paused=False)]
    db.rows["jobs"] = [_job("job_01JZXR7K3M5Q8N4VWA0000H01", status=JobStatus.AWAITING_REVIEW)]
    with TestClient(_make_app(db)) as client:
        r = client.get("/api/ripper/drives/drv_x/held-job", headers=_SERVICE_AUTH)
    assert r.status_code == 200
    out = r.json()
    assert out["job"]["id"] == "job_01JZXR7K3M5Q8N4VWA0000H01"
    assert out["paused"] is False


def test_held_job_paused_flag_from_global() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(ripping_paused=True)]
    db.rows["jobs"] = [_job("job_01JZXR7K3M5Q8N4VWA0000H02", status=JobStatus.AWAITING_REVIEW)]
    with TestClient(_make_app(db)) as client:
        r = client.get("/api/ripper/drives/drv_x/held-job", headers=_SERVICE_AUTH)
    assert r.status_code == 200
    assert r.json()["paused"] is True


def test_held_job_paused_flag_from_per_job_manual_pause() -> None:
    """paused is global ripping_paused OR this disc's manual_pause — a per-job
    pause alone (global off) still marks it paused for reboot recovery."""
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(ripping_paused=False)]
    held = _job("job_01JZXR7K3M5Q8N4VWA0000H07", status=JobStatus.AWAITING_REVIEW)
    held.manual_pause = True
    db.rows["jobs"] = [held]
    with TestClient(_make_app(db)) as client:
        r = client.get("/api/ripper/drives/drv_x/held-job", headers=_SERVICE_AUTH)
    assert r.status_code == 200
    assert r.json()["paused"] is True


def test_held_job_multi_row_logs_and_returns_first(caplog: pytest.LogCaptureFixture) -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config()]
    db.rows["jobs"] = [
        _job("job_01JZXR7K3M5Q8N4VWA0000H03", status=JobStatus.AWAITING_REVIEW),
        _job("job_01JZXR7K3M5Q8N4VWA0000H04", status=JobStatus.AWAITING_REVIEW),
    ]
    with TestClient(_make_app(db)) as client:
        with caplog.at_level("ERROR", logger="arm_backend.routers.ripper"):
            r = client.get("/api/ripper/drives/drv_x/held-job", headers=_SERVICE_AUTH)
    assert r.status_code == 200
    assert r.json()["job"]["id"] == "job_01JZXR7K3M5Q8N4VWA0000H03"
    assert any("data-model violation" in rec.message for rec in caplog.records)


def test_recovery_abandon_transitions_and_emits() -> None:
    db = FakeSession()
    hub = _Hub()
    db.rows["jobs"] = [_job("job_01JZXR7K3M5Q8N4VWA0000H05", status=JobStatus.AWAITING_REVIEW)]
    with TestClient(_make_app(db, hub=hub)) as client:
        r = client.post("/api/ripper/jobs/job_01JZXR7K3M5Q8N4VWA0000H05/recovery-abandon", headers=_SERVICE_AUTH)
    assert r.status_code == 200
    assert r.json()["status"] == "abandoned"
    assert any(e["event_type"] == "rip.abandoned" for e in hub.events)


def test_recovery_abandon_unknown_404() -> None:
    db = FakeSession()
    with TestClient(_make_app(db)) as client:
        r = client.post("/api/ripper/jobs/job_01JZXR7K3M5Q8N4VWA0000404/recovery-abandon", headers=_SERVICE_AUTH)
    assert r.status_code == 404


def test_recovery_abandon_wrong_status_409() -> None:
    db = FakeSession()
    db.rows["jobs"] = [_job("job_01JZXR7K3M5Q8N4VWA0000H06", status=JobStatus.RIPPING)]
    with TestClient(_make_app(db)) as client:
        r = client.post("/api/ripper/jobs/job_01JZXR7K3M5Q8N4VWA0000H06/recovery-abandon", headers=_SERVICE_AUTH)
    assert r.status_code == 409
    assert "awaiting_review" in r.json()["detail"]


def test_recovery_abandon_unknown_status_409_not_500() -> None:
    """A forward-incompatible status (raw str from _StrEnumString) must yield the
    intended 409 here, not an AttributeError 500 from f-string `.value`."""
    db = FakeSession()
    job = _job("job_01JZXR7K3M5Q8N4VWA0000H08", status=JobStatus.RIPPING)
    object.__setattr__(job, "status", "some_future_status")
    db.rows["jobs"] = [job]
    with TestClient(_make_app(db)) as client:
        r = client.post("/api/ripper/jobs/job_01JZXR7K3M5Q8N4VWA0000H08/recovery-abandon", headers=_SERVICE_AUTH)
    assert r.status_code == 409
    assert "some_future_status" in r.json()["detail"]


# --- /rip-start --------------------------------------------------------------


def test_rip_start_no_default_preset_422() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["jobs"] = [_job(status=JobStatus.IDENTIFIED, disc_type=DiscType.UNKNOWN)]
    with TestClient(_make_app(db)) as client:
        r = client.post("/api/ripper/jobs/job_01JZXR7K3M5Q8N4VWA00000001/rip-start", headers=_OWNER_HEADERS)
    assert r.status_code == 422
    assert "no default rip preset" in r.json()["detail"]


def test_rip_start_returns_existing_tracks() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["jobs"] = [_job(status=JobStatus.RIPPING)]
    db.rows["tracks"] = [_track("trk_1", status=TrackStatus.IN_PROGRESS)]
    with TestClient(_make_app(db)) as client:
        r = client.post("/api/ripper/jobs/job_01JZXR7K3M5Q8N4VWA00000001/rip-start", headers=_OWNER_HEADERS)
    assert r.status_code == 200
    assert [t["id"] for t in r.json()["tracks"]] == ["trk_1"]


def test_rip_start_existing_tracks_transitions_non_ripping() -> None:
    """Timed-review auto-start: rip-start on a held job whose review tracks were
    pre-persisted must transition AWAITING_REVIEW -> RIPPING (audit B2), not
    return early without transitioning. started_at is stamped (was None)."""
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["jobs"] = [_job(status=JobStatus.AWAITING_REVIEW)]
    db.rows["tracks"] = [_track("trk_1", status=TrackStatus.QUEUED)]
    with TestClient(_make_app(db)) as client:
        r = client.post("/api/ripper/jobs/job_01JZXR7K3M5Q8N4VWA00000001/rip-start", headers=_OWNER_HEADERS)
    assert r.status_code == 200
    assert db.rows["jobs"][0].status == JobStatus.RIPPING
    assert db.rows["jobs"][0].started_at is not None


def test_rip_start_existing_tracks_preserves_started_at() -> None:
    """The transition keeps an already-set started_at (covers the started_at-not-
    None branch) rather than overwriting it."""
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    job = _job(status=JobStatus.AWAITING_REVIEW)
    stamped = datetime(2026, 1, 1, tzinfo=timezone.utc)
    job.started_at = stamped
    db.rows["jobs"] = [job]
    db.rows["tracks"] = [_track("trk_1", status=TrackStatus.QUEUED)]
    with TestClient(_make_app(db)) as client:
        r = client.post("/api/ripper/jobs/job_01JZXR7K3M5Q8N4VWA00000001/rip-start", headers=_OWNER_HEADERS)
    assert r.status_code == 200
    assert db.rows["jobs"][0].status == JobStatus.RIPPING
    assert db.rows["jobs"][0].started_at == stamped  # preserved, not overwritten


def test_rip_start_awaiting_review_no_tracks_selects_and_rips() -> None:
    """Timed-review auto-start where NO review tracks were persisted (a genuinely
    identified disc whose scan yielded zero persistable titles -> select_tracks_for_review
    added nothing). rip-start must fall through and select tracks now, exactly as
    for a never-parked IDENTIFIED disc — NOT 409. A 409 here is non-retryable on the
    ripper, so the disc would be stuck in AWAITING_REVIEW forever."""
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["jobs"] = [_job(status=JobStatus.AWAITING_REVIEW, meta={"scan_result": _scan_dict()})]
    db.rows["tracks"] = []
    db.rows["rip_presets"] = [_movie_preset()]
    new = [_track("trk_new", status=TrackStatus.QUEUED)]
    with TestClient(_make_app(db)) as client, _patch_select_tracks(new):
        r = client.post("/api/ripper/jobs/job_01JZXR7K3M5Q8N4VWA00000001/rip-start", headers=_OWNER_HEADERS)
    assert r.status_code == 200
    assert [t["id"] for t in r.json()["tracks"]] == ["trk_new"]
    assert db.rows["jobs"][0].status == JobStatus.RIPPING


def test_rip_start_not_identified_409() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["jobs"] = [_job(status=JobStatus.CREATED)]
    db.rows["tracks"] = []
    with TestClient(_make_app(db)) as client:
        r = client.post("/api/ripper/jobs/job_01JZXR7K3M5Q8N4VWA00000001/rip-start", headers=_OWNER_HEADERS)
    assert r.status_code == 409
    assert "not in identified state" in r.json()["detail"]


def test_rip_start_unknown_status_409_not_500() -> None:
    """A forward-incompatible status (loaded as a raw str by _StrEnumString) on the
    no-existing-tracks branch must produce the intended 409, not an AttributeError
    500 from f-string `.value` access. enum_value_str renders the raw string."""
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    job = _job(status=JobStatus.IDENTIFIED)
    object.__setattr__(job, "status", "some_future_status")  # simulate post-load raw string
    db.rows["jobs"] = [job]
    db.rows["tracks"] = []
    with TestClient(_make_app(db)) as client:
        r = client.post("/api/ripper/jobs/job_01JZXR7K3M5Q8N4VWA00000001/rip-start", headers=_OWNER_HEADERS)
    assert r.status_code == 409
    assert "some_future_status" in r.json()["detail"]


def test_rip_start_missing_scan_result_409() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["jobs"] = [_job(status=JobStatus.IDENTIFIED, meta={})]
    db.rows["tracks"] = []
    with TestClient(_make_app(db)) as client:
        r = client.post("/api/ripper/jobs/job_01JZXR7K3M5Q8N4VWA00000001/rip-start", headers=_OWNER_HEADERS)
    assert r.status_code == 409
    assert "missing scan_result" in r.json()["detail"]


def test_rip_start_preset_not_seeded_500() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["jobs"] = [_job(status=JobStatus.IDENTIFIED, meta={"scan_result": _scan_dict()})]
    db.rows["tracks"] = []
    db.rows["rip_presets"] = []
    with TestClient(_make_app(db)) as client:
        r = client.post("/api/ripper/jobs/job_01JZXR7K3M5Q8N4VWA00000001/rip-start", headers=_OWNER_HEADERS)
    assert r.status_code == 500
    assert "not seeded" in r.json()["detail"]


def test_rip_start_zero_tracks_422() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["jobs"] = [_job(status=JobStatus.IDENTIFIED, meta={"scan_result": _scan_dict()})]
    db.rows["tracks"] = []
    db.rows["rip_presets"] = [_movie_preset()]
    with TestClient(_make_app(db)) as client, _patch_select_tracks([]):
        r = client.post("/api/ripper/jobs/job_01JZXR7K3M5Q8N4VWA00000001/rip-start", headers=_OWNER_HEADERS)
    assert r.status_code == 422
    assert "zero tracks" in r.json()["detail"]


def test_rip_start_success_creates_tracks_and_emits() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["jobs"] = [_job(status=JobStatus.IDENTIFIED, meta={"scan_result": _scan_dict()})]
    db.rows["tracks"] = []
    db.rows["rip_presets"] = [_movie_preset()]
    hub = _Hub()
    app = _make_app(db, hub=hub)
    new = [_track("trk_new", status=TrackStatus.QUEUED)]
    with TestClient(app) as client, _patch_select_tracks(new):
        r = client.post("/api/ripper/jobs/job_01JZXR7K3M5Q8N4VWA00000001/rip-start", headers=_OWNER_HEADERS)
    assert r.status_code == 200
    assert [t["id"] for t in r.json()["tracks"]] == ["trk_new"]
    assert any(e["event_type"] == "rip.started" for e in hub.events)


# --- /resume (no-default-preset branch; happy path is in test_ripper_resume) --


def test_resume_no_default_preset_422() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["jobs"] = [_job(status=JobStatus.RIPPING, disc_type=DiscType.UNKNOWN)]
    with TestClient(_make_app(db)) as client:
        r = client.post("/api/ripper/jobs/job_01JZXR7K3M5Q8N4VWA00000001/resume", headers=_OWNER_HEADERS)
    assert r.status_code == 422
    assert "no default rip preset" in r.json()["detail"]


# --- /tracks/{id} state machine ----------------------------------------------


def _track_app(db: FakeSession, track: Track, hub: _Hub | None = None) -> FastAPI:
    db.rows["tracks"] = [track]
    db.rows["jobs"] = [_job(status=JobStatus.RIPPING)]
    db.rows["drives"] = [_drive()]
    return _make_app(db, hub=hub)


def test_update_track_queued_to_in_progress() -> None:
    db = FakeSession()
    app = _track_app(db, _track("trk_1", status=TrackStatus.QUEUED))
    with TestClient(app) as client:
        r = client.patch("/api/ripper/tracks/trk_1", json={"status": "in_progress"}, headers=_OWNER_HEADERS)
    assert r.status_code == 200
    assert r.json()["status"] == "in_progress"


def test_update_track_bad_to_in_progress_409() -> None:
    db = FakeSession()
    app = _track_app(db, _track("trk_1", status=TrackStatus.DONE))
    with TestClient(app) as client:
        r = client.patch("/api/ripper/tracks/trk_1", json={"status": "in_progress"}, headers=_OWNER_HEADERS)
    assert r.status_code == 409
    assert "-> in_progress" in r.json()["detail"]


def test_update_track_done_emits_completed() -> None:
    db = FakeSession()
    hub = _Hub()
    app = _track_app(db, _track("trk_1", status=TrackStatus.IN_PROGRESS), hub=hub)
    body = {"status": "done", "output_path": "/m/a.mkv", "size_bytes": 99, "sha256": "ab", "duration_seconds": 42}
    with TestClient(app) as client:
        r = client.patch("/api/ripper/tracks/trk_1", json=body, headers=_OWNER_HEADERS)
    assert r.status_code == 200
    assert r.json()["output_path"] == "/m/a.mkv"
    assert any(e["event_type"] == "track.completed" for e in hub.events)


def test_update_track_done_without_optional_fields() -> None:
    """status=done with no output_path/size/sha/duration — every `is not
    None` guard takes its false branch."""
    db = FakeSession()
    hub = _Hub()
    app = _track_app(db, _track("trk_1", status=TrackStatus.IN_PROGRESS), hub=hub)
    with TestClient(app) as client:
        r = client.patch("/api/ripper/tracks/trk_1", json={"status": "done"}, headers=_OWNER_HEADERS)
    assert r.status_code == 200
    assert r.json()["status"] == "done"
    assert r.json()["output_path"] is None


def test_update_track_failed_without_last_error() -> None:
    db = FakeSession()
    app = _track_app(db, _track("trk_1", status=TrackStatus.IN_PROGRESS))
    with TestClient(app) as client:
        r = client.patch("/api/ripper/tracks/trk_1", json={"status": "failed"}, headers=_OWNER_HEADERS)
    assert r.status_code == 200
    assert r.json()["status"] == "failed"


def test_update_track_bad_to_done_409() -> None:
    db = FakeSession()
    app = _track_app(db, _track("trk_1", status=TrackStatus.QUEUED))
    with TestClient(app) as client:
        r = client.patch("/api/ripper/tracks/trk_1", json={"status": "done"}, headers=_OWNER_HEADERS)
    assert r.status_code == 409


def test_update_track_failed_emits_failed() -> None:
    db = FakeSession()
    hub = _Hub()
    app = _track_app(db, _track("trk_1", status=TrackStatus.IN_PROGRESS), hub=hub)
    with TestClient(app) as client:
        r = client.patch(
            "/api/ripper/tracks/trk_1",
            json={"status": "failed", "last_error": "boom"},
            headers=_OWNER_HEADERS,
        )
    assert r.status_code == 200
    assert any(e["event_type"] == "track.failed" for e in hub.events)


def test_update_track_bad_to_failed_409() -> None:
    db = FakeSession()
    app = _track_app(db, _track("trk_1", status=TrackStatus.QUEUED))
    with TestClient(app) as client:
        r = client.patch("/api/ripper/tracks/trk_1", json={"status": "failed"}, headers=_OWNER_HEADERS)
    assert r.status_code == 409


def test_update_track_invalid_target_409() -> None:
    db = FakeSession()
    app = _track_app(db, _track("trk_1", status=TrackStatus.IN_PROGRESS))
    with TestClient(app) as client:
        r = client.patch("/api/ripper/tracks/trk_1", json={"status": "queued"}, headers=_OWNER_HEADERS)
    assert r.status_code == 409
    assert "not allowed via PATCH" in r.json()["detail"]


# --- /rip-complete -----------------------------------------------------------


def _rip_complete(db: FakeSession, hub: _Hub, monkeypatch: pytest.MonkeyPatch) -> Any:
    async def _noop(*_a: Any, **_k: Any) -> None:
        return None

    monkeypatch.setattr(ripper_router, "maybe_auto_apply_session", _noop)
    app = _make_app(db, hub=hub)
    with TestClient(app) as client:
        return client.post(
            "/api/ripper/jobs/job_01JZXR7K3M5Q8N4VWA00000001/rip-complete", json={}, headers=_OWNER_HEADERS
        )


def test_rip_complete_not_ripping_409(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeSession()
    db.rows["jobs"] = [_job(status=JobStatus.IDENTIFIED)]
    db.rows["drives"] = [_drive()]
    r = _rip_complete(db, _Hub(), monkeypatch)
    assert r.status_code == 409
    assert "not in ripping state" in r.json()["detail"]


def test_rip_complete_all_done_ripped(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeSession()
    db.rows["jobs"] = [_job(status=JobStatus.RIPPING)]
    db.rows["drives"] = [_drive()]
    db.rows["tracks"] = [_track("t1", status=TrackStatus.DONE)]
    hub = _Hub()
    r = _rip_complete(db, hub, monkeypatch)
    assert r.status_code == 200
    assert r.json()["status"] == "ripped"
    assert any(e["event_type"] == "rip.completed" for e in hub.events)


def test_rip_complete_partial(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeSession()
    db.rows["jobs"] = [_job(status=JobStatus.RIPPING)]
    db.rows["drives"] = [_drive()]
    db.rows["tracks"] = [
        _track("t1", status=TrackStatus.DONE, index=1),
        _track("t2", status=TrackStatus.FAILED, index=2),
    ]
    hub = _Hub()
    r = _rip_complete(db, hub, monkeypatch)
    assert r.status_code == 200
    assert r.json()["status"] == "ripped_partial"
    assert any(e["event_type"] == "rip.partial" for e in hub.events)


def test_rip_complete_no_done_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeSession()
    db.rows["jobs"] = [_job(status=JobStatus.RIPPING)]
    db.rows["drives"] = [_drive()]
    db.rows["tracks"] = [_track("t1", status=TrackStatus.FAILED)]
    hub = _Hub()
    r = _rip_complete(db, hub, monkeypatch)
    assert r.status_code == 200
    assert r.json()["status"] == "failed"
    assert any(e["event_type"] == "rip.failed" for e in hub.events)


def test_rip_complete_zero_tracks_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeSession()
    db.rows["jobs"] = [_job(status=JobStatus.RIPPING)]
    db.rows["drives"] = [_drive()]
    db.rows["tracks"] = []
    r = _rip_complete(db, _Hub(), monkeypatch)
    assert r.status_code == 200
    assert r.json()["status"] == "failed"


# --- helpers -----------------------------------------------------------------


class _patch_select_tracks:
    """Context manager swapping ripper_router.select_tracks for a fixed list."""

    def __init__(self, tracks: list[Track]) -> None:
        self._tracks = tracks
        self._orig: Any = None

    def __enter__(self) -> None:
        self._orig = ripper_router.select_tracks
        ripper_router.select_tracks = lambda *_a, **_k: self._tracks  # type: ignore[assignment]

    def __exit__(self, *_exc: Any) -> None:
        ripper_router.select_tracks = self._orig  # type: ignore[assignment]
