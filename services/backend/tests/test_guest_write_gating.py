"""Guest-role write gating sweep (spec's Task 4 gate table).

A `role=guest` user must get 403 `"read-only role: write access required"`
on every mutating UI route swapped to `Depends(require_writer)`, and must
NOT get that 403 on the routes intentionally left open to guests (reads,
`sessions/preview`, `jobs/iso/scan`, `notifications/.../compose-url`,
`drives/rescan`, `naming/validate`, `naming/preview`, `login`, `logout`).

The 403 fires in the `require_writer` dependency before the route body or
request validation runs, so gated-route bodies here are minimal (`{}` or
omitted) — they never need to be well-formed. Stay-open routes get the
opposite assertion: any status except the role-403 proves the gate isn't
over-applied (a 404/422/2xx from hitting real route logic is fine).
"""

from __future__ import annotations

import os
import secrets

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import (  # noqa: E402
    auth as auth_router,
    config as config_router,
    drives as drives_router,
    files as files_router,
    images as images_router,
    iso as iso_router,
    jobs as jobs_router,
    notifications as notifications_router,
    rip_presets as rip_presets_router,
    sessions as sessions_router,
    themes as themes_router,
    transcode_presets as transcode_presets_router,
    transcodes as transcodes_router,
)
from arm_common import User  # noqa: E402
from arm_common.models.user import GUEST_ROLE  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402

_KEY = secrets.token_bytes(32)
_ROLE_DENIED_DETAIL = "read-only role: write access required"

# Every router touched by the sweep, wired into one app so a single guest
# JWT can hit any of their routes.
_ALL_ROUTERS = (
    auth_router,
    config_router,
    drives_router,
    files_router,
    images_router,
    iso_router,
    jobs_router,
    notifications_router,
    rip_presets_router,
    sessions_router,
    themes_router,
    transcode_presets_router,
    transcodes_router,
)


def _app() -> tuple[FastAPI, FakeSession]:
    db = FakeSession()
    db.rows["users"] = [
        User(
            id="usr_guest",
            username="guest",
            password_hash="x",
            password_must_change=False,
            role=GUEST_ROLE,
            disabled=False,
        )
    ]
    app = FastAPI()
    app.state.signing_key = _KEY
    app.state.ws_hub = None
    app.state.dispatcher = None
    app.state.notifier = None
    for m in _ALL_ROUTERS:
        app.include_router(m.router)

    async def _ov() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _ov
    return app, db


def _guest_headers() -> dict[str, str]:
    token, _ = issue_access_token("usr_guest", "guest", _KEY)
    return {"Authorization": f"Bearer {token}"}


# --- Gate table (spec §3) — every mutating route swapped to require_writer --

_GATED_ROUTES: list[tuple[str, str, dict[str, object]]] = [
    # jobs
    ("POST", "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/abandon", {}),
    ("DELETE", "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001", {}),
    ("DELETE", "/api/jobs", {}),
    ("POST", "/api/jobs/manual", {}),
    ("PATCH", "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001", {}),
    ("POST", "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/resolve", {}),
    ("POST", "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/transcode", {}),
    # jobs — timed-review-gate stragglers (found in Step 1 sweep; see report)
    ("POST", "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/rip-start-review", {}),
    ("POST", "/api/jobs/job_01JZXR7K3M5Q8N4VWA00000001/review-pause", {}),
    # drives
    ("PATCH", "/api/drives/drv_x", {}),
    ("DELETE", "/api/drives/drv_x", {}),
    # sessions
    ("POST", "/api/sessions", {}),
    ("PATCH", "/api/sessions/ses_x", {}),
    ("DELETE", "/api/sessions/ses_x", {}),
    ("POST", "/api/sessions/ses_x/clone", {}),
    # rip_presets
    ("POST", "/api/rip-presets", {}),
    ("PATCH", "/api/rip-presets/rpr_x", {}),
    ("DELETE", "/api/rip-presets/rpr_x", {}),
    # transcode_presets
    ("POST", "/api/transcode-presets", {}),
    ("PATCH", "/api/transcode-presets/tpr_x", {}),
    ("DELETE", "/api/transcode-presets/tpr_x", {}),
    # config
    ("PATCH", "/api/config", {}),
    # transcodes
    ("POST", "/api/transcodes/tct_x/retry", {}),
    ("DELETE", "/api/transcodes/tct_x", {}),
    # notifications
    ("POST", "/api/notifications/channels", {}),
    ("PATCH", "/api/notifications/channels/ncl_x", {}),
    ("DELETE", "/api/notifications/channels/ncl_x", {}),
    ("POST", "/api/notifications/channels/ncl_x/test", {}),
    ("POST", "/api/notifications/test", {}),
    ("POST", "/api/notifications/inbox/dismiss-all", {}),
    ("POST", "/api/notifications/inbox/purge", {}),
    ("PATCH", "/api/notifications/inbox/nib_x", {}),
    # themes
    ("DELETE", "/api/themes/thm_x", {}),
    # images
    ("POST", "/api/images/cache/clear", {}),
    # files
    ("POST", "/api/files/mkdir", {}),
    ("POST", "/api/files/rename", {}),
    ("POST", "/api/files/move", {}),
    ("POST", "/api/files/fix-permissions", {}),
    ("DELETE", "/api/files", {}),
    # auth
    ("POST", "/api/auth/password", {}),
]

# themes.py's POST is multipart (UploadFile + Form), not JSON — needs its own
# request shape, so it's exercised separately below rather than in the table.

_STAY_OPEN_ROUTES: list[tuple[str, str, dict[str, object] | None]] = [
    # one GET per swept router
    ("GET", "/api/jobs", None),
    ("GET", "/api/drives", None),
    ("GET", "/api/sessions", None),
    ("GET", "/api/rip-presets", None),
    ("GET", "/api/transcode-presets", None),
    ("GET", "/api/config", None),
    ("GET", "/api/transcodes", None),
    ("GET", "/api/notifications/channels", None),
    ("GET", "/api/themes", None),
    ("GET", "/api/images/cache", None),
    ("GET", "/api/files/roots", None),
    # explicitly-open mutating routes
    ("POST", "/api/sessions/preview", {"template": "{title}", "media_type": "movie", "has_transcode_preset": False}),
    ("POST", "/api/jobs/iso/scan", {"path": "does-not-exist.iso"}),
]


@pytest.mark.parametrize("method,path,body", _GATED_ROUTES)
def test_guest_denied_write_route(method: str, path: str, body: dict[str, object]) -> None:
    app, _db = _app()
    with TestClient(app) as client:
        if path == "/api/files":
            # files.delete takes root/subpath as query params, not a JSON body.
            r = client.request(method, path, params={"root": "media", "subpath": "x"}, headers=_guest_headers())
        else:
            r = client.request(method, path, json=body, headers=_guest_headers())
    assert r.status_code == 403, f"{method} {path} -> {r.status_code} (expected 403): {r.text}"
    assert r.json()["detail"] == _ROLE_DENIED_DETAIL


@pytest.mark.parametrize("method,path,body", _STAY_OPEN_ROUTES)
def test_guest_allowed_stay_open_route(method: str, path: str, body: dict[str, object] | None) -> None:
    app, _db = _app()
    with TestClient(app) as client:
        if body is None:
            r = client.request(method, path, headers=_guest_headers())
        else:
            r = client.request(method, path, json=body, headers=_guest_headers())
    assert r.status_code != 403 or r.json().get("detail") != _ROLE_DENIED_DETAIL, (
        f"{method} {path} -> unexpectedly denied by role gate: {r.text}"
    )


def test_guest_denied_theme_upload() -> None:
    """themes.py POST "" is multipart; exercised outside the JSON-body table."""
    app, _db = _app()
    with TestClient(app) as client:
        r = client.post(
            "/api/themes",
            files={"theme_json": ("t.json", b"{}", "application/json")},
            headers=_guest_headers(),
        )
    assert r.status_code == 403
    assert r.json()["detail"] == _ROLE_DENIED_DETAIL


def test_admin_must_change_password_can_still_change_password() -> None:
    """require_writer composes require_jwt, whose must-change whitelist already
    allows /api/auth/password; an admin mid-password_must_change passes the
    role check too, so the route must stay reachable (spec Task 4 Step 4 note).
    """
    from argon2 import PasswordHasher

    hasher = PasswordHasher()
    db = FakeSession()
    admin = User(
        id="usr_admin_mc",
        username="admin_mc",
        password_hash=hasher.hash("hunter2-correct"),
        password_must_change=True,
        role="admin",
        disabled=False,
    )
    db.rows["users"] = [admin]
    app = FastAPI()
    app.state.signing_key = _KEY
    app.include_router(auth_router.router)

    async def _ov() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _ov
    token, _ = issue_access_token(admin.id, admin.username, _KEY)

    with TestClient(app) as client:
        r = client.post(
            "/api/auth/password",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": "hunter2-correct", "new_password": "newpassword123"},
        )
    assert r.status_code == 200
    assert admin.password_must_change is False
