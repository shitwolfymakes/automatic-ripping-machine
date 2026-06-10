"""Pause-gate coverage: Config.ripping_paused=True must produce 409 at both
entry points (identify + manual_trigger); ripping_paused=False must pass through
normally.
"""

from __future__ import annotations

import os
import secrets
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.metadata.base import MetadataResult  # noqa: E402
from arm_backend.routers import jobs as jobs_router  # noqa: E402
from arm_backend.routers import ripper as ripper_router  # noqa: E402
from arm_common import (  # noqa: E402
    Config,
    Drive,
    DriveMediaStatus,
    DriveStatus,
    MediaType,
    RetentionPolicy,
    Session,
)

from tests._fakes import FakeSession  # noqa: E402

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_SERVICE_AUTH = {"Authorization": "Bearer tok-service"}


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
        self.events.append({"topic": topic, "event_type": event_type, "payload": payload})


class _Dispatcher:
    def __init__(self, result: MetadataResult | None = None) -> None:
        self.result = result

    async def identify(self, _scan: Any, _cfg: Any) -> MetadataResult | None:
        return self.result


def _config(*, ripping_paused: bool = False) -> Config:
    return Config(
        id=1,
        auto_transcode_on_idle=False,
        auto_rip_on_insert=True,
        block_on_miss=False,
        ripping_paused=ripping_paused,
        default_retention_policy=RetentionPolicy.PRUNE_AFTER_SESSION,
    )


def _drive_row(*, media: DriveMediaStatus | None = None) -> Drive:
    from datetime import datetime, timezone

    d = Drive(id="drv_x", hostname="ripper-host", device_path="/dev/sr0", status=DriveStatus.ONLINE)
    if media is not None:
        d.media_status = media
        d.media_status_at = datetime.now(timezone.utc)
    return d


def _scan_dict(disc_type: str = "dvd") -> dict[str, Any]:
    return {
        "disc_type": disc_type,
        "volume_label": "MY_DISC",
        "titles": [{"index": 1, "duration_seconds": 4200}],
        "fingerprints": [],
        "raw": {},
    }


# ---------------------------------------------------------------------------
# Ripper-router app (service-token auth)
# ---------------------------------------------------------------------------


def _make_ripper_app(
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

    async def _override() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override
    return app


# ---------------------------------------------------------------------------
# Jobs-router app (JWT auth)
# ---------------------------------------------------------------------------


def _make_jobs_app(db: FakeSession, hub: _Hub | None = None) -> tuple[FastAPI, str]:
    signing_key = secrets.token_bytes(32)
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.ws_hub = hub or _Hub()
    app.include_router(jobs_router.router)

    async def _override() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override

    from arm_common import User

    db.rows.setdefault("users", []).append(
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)
    )
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, token


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Gate 1: identify — ripping_paused=True -> 409
# ---------------------------------------------------------------------------


def test_identify_paused_returns_409() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive_row()]
    db.rows["config"] = [_config(ripping_paused=True)]
    app = _make_ripper_app(db)
    body = {"drive_id": "drv_x", "scan_result": _scan_dict()}
    with TestClient(app) as client:
        r = client.post("/api/ripper/identify", json=body, headers=_SERVICE_AUTH)
    assert r.status_code == 409
    assert "paused" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Gate 1: identify — ripping_paused=False -> NOT 409 (job is created)
# ---------------------------------------------------------------------------


def test_identify_not_paused_succeeds() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive_row()]
    db.rows["config"] = [_config(ripping_paused=False)]
    result = MetadataResult(title="Dune", year=2021, kind="movie", payload={})
    app = _make_ripper_app(db, dispatcher=_Dispatcher(result))
    body = {"drive_id": "drv_x", "scan_result": _scan_dict()}
    with TestClient(app) as client:
        r = client.post("/api/ripper/identify", json=body, headers=_SERVICE_AUTH)
    assert r.status_code == 200
    assert r.json()["status"] == "identified"


# ---------------------------------------------------------------------------
# Gate 2: manual_trigger — ripping_paused=True -> 409
# ---------------------------------------------------------------------------


def test_manual_trigger_paused_returns_409() -> None:
    db = FakeSession()
    db.rows["drives"] = [_drive_row(media=DriveMediaStatus.LOADED)]
    db.rows["jobs"] = []
    db.rows["config"] = [_config(ripping_paused=True)]
    app, token = _make_jobs_app(db)
    with TestClient(app) as client:
        r = client.post("/api/jobs/manual", json={"drive_id": "drv_x"}, headers=_auth(token))
    assert r.status_code == 409
    assert "paused" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Gate 2: manual_trigger — ripping_paused=False -> 202
# ---------------------------------------------------------------------------


def test_manual_trigger_not_paused_succeeds() -> None:
    db = FakeSession()
    hub = _Hub()
    db.rows["drives"] = [_drive_row(media=DriveMediaStatus.LOADED)]
    db.rows["jobs"] = []
    db.rows["config"] = [_config(ripping_paused=False)]
    db.rows["sessions"] = [
        Session(
            id="ses_1",
            name="S",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_1",
            output_path_template="{title}.{ext}",
        )
    ]
    app, token = _make_jobs_app(db, hub)
    with TestClient(app) as client:
        r = client.post(
            "/api/jobs/manual",
            json={"drive_id": "drv_x", "session_id": "ses_1"},
            headers=_auth(token),
        )
    assert r.status_code == 202
    assert any(e["event_type"] == "manual.trigger" for e in hub.events)
