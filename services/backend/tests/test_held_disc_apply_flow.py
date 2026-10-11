"""Held disc -> apply session, driven through the real routers.

Replaces a live-stack check: identify with `hold_for_review` on persists review
Track rows (`_persist_review_tracks`) and parks the job in AWAITING_REVIEW; an
operator then applies a session from the review card. The application must
park (`waiting_identify`, no TranscodeTask rows) until rip-complete, even
though Track rows already exist. Both routers share one FakeSession.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path

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
    ContainerFormat,
    MediaType,
    Session,
    SessionApplicationStatus,
    TranscodePreset,
    TranscodeTool,
    User,
)

from tests._fakes import FakeSession  # noqa: E402
from tests.test_ripper_router import (  # noqa: E402
    _SERVICE_AUTH,
    _config,
    _Dispatcher,
    _drive,
    _Hub,
    _movie_preset,
    _scan_dict,
)


def _make_app(db: FakeSession, *, dispatcher: _Dispatcher, hub: _Hub) -> tuple[FastAPI, dict[str, str]]:
    signing_key = secrets.token_bytes(32)
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.dispatcher = dispatcher
    app.state.ws_hub = hub
    app.include_router(ripper_router.router)
    app.include_router(jobs_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return app, {"Authorization": f"Bearer {token}"}


def test_apply_on_held_disc_with_review_tracks_parks_until_rip(tmp_path: Path) -> None:
    from arm_backend import config as bcfg

    bcfg.settings.MEDIA_ROOT = str(tmp_path)

    db = FakeSession()
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config(hold_for_review=True)]
    db.rows["rip_presets"] = [_movie_preset()]
    db.rows["transcode_presets"] = [
        TranscodePreset(
            id="tpr_x",
            name="Plex 1080p H.265",
            media_type=MediaType.MOVIE,
            is_builtin=True,
            tool=TranscodeTool.HANDBRAKE,
            container=ContainerFormat.MKV,
            encoder="preset",
        )
    ]
    db.rows["sessions"] = [
        Session(
            id="ses_x",
            name="My Plex",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_builtin_movie_archive",
            transcode_preset_id="tpr_x",
            output_path_template="{title} ({year})/{title} - {transcode_slug}.{ext}",
        )
    ]
    db.rows["session_applications"] = []
    db.rows["transcode_tasks"] = []

    result = MetadataResult(title="Iron Man", year=2008, kind="movie", payload={})
    app, auth = _make_app(db, dispatcher=_Dispatcher(result), hub=_Hub())

    with TestClient(app) as client:
        r = client.post(
            "/api/ripper/identify",
            json={"drive_id": "drv_x", "scan_result": _scan_dict()},
            headers=_SERVICE_AUTH,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "awaiting_review"
        job_id = r.json()["id"]

        # The hold persisted review tracks: the premise this regression needs.
        review_tracks = [t for t in db.rows.get("tracks", []) if t.job_id == job_id]
        assert review_tracks, "identify with hold_for_review must persist review Track rows"
        assert any(not t.excluded for t in review_tracks)

        r = client.post(f"/api/jobs/{job_id}/transcode", json={"session_id": "ses_x"}, headers=auth)

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["session_application"]["status"] == "waiting_identify"
    assert body["tasks"] == []
    apps = db.rows["session_applications"]
    assert len(apps) == 1
    assert apps[0].status == SessionApplicationStatus.WAITING_IDENTIFY
    assert db.rows["transcode_tasks"] == []
