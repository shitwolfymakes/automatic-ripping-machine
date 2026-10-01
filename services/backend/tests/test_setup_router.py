"""Setup router: first-run walkthrough state (setup spec 2026-10-01 §6.1)."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import setup as setup_router  # noqa: E402
from arm_common import Config, User  # noqa: E402
from arm_common.models.user import GUEST_ROLE  # noqa: E402
from arm_common.schemas import SystemDiagnosticCheck, SystemDiagnosticsResponse  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


@pytest.fixture
def signing_key() -> bytes:
    return secrets.token_bytes(32)


@pytest.fixture
def admin_user() -> User:
    return User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)


@pytest.fixture
def guest_user() -> User:
    return User(
        id="usr_guest", username="guest", password_hash="x", password_must_change=False, role=GUEST_ROLE, disabled=True
    )


def _seeded(admin_user: User, guest_user: User) -> FakeSession:
    db = FakeSession()
    db.rows["config"] = [Config(id=1, setup_progress={})]
    db.rows["users"] = [admin_user, guest_user]
    return db


def _make_app(signing_key: bytes, db: FakeSession) -> FastAPI:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.include_router(setup_router.router)

    async def _override() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override
    return app


def _auth(signing_key: bytes, user: User) -> dict[str, str]:
    token, _ = issue_access_token(user.id, user.username, signing_key)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _no_real_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    async def not_ok(request, db) -> bool:
        return False

    monkeypatch.setattr(setup_router, "_diagnostics_ok", not_ok)


# --- public status ---


def test_status_is_public_and_first_run_when_not_completed(signing_key, admin_user, guest_user) -> None:
    db = _seeded(admin_user, guest_user)
    with TestClient(_make_app(signing_key, db)) as c:
        r = c.get("/api/setup/status")
    assert r.status_code == 200
    assert r.json()["first_run"] is True
    assert isinstance(r.json()["arm_version"], str)


def test_status_false_when_completed(signing_key, admin_user, guest_user) -> None:
    db = _seeded(admin_user, guest_user)
    db.rows["config"][0].setup_completed_at = datetime.now(timezone.utc)
    with TestClient(_make_app(signing_key, db)) as c:
        assert c.get("/api/setup/status").json()["first_run"] is False


def test_status_fails_closed_on_db_error(signing_key, admin_user, guest_user, monkeypatch) -> None:
    db = _seeded(admin_user, guest_user)

    async def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(db, "execute", boom)
    with TestClient(_make_app(signing_key, db)) as c:
        r = c.get("/api/setup/status")
    assert r.status_code == 200
    assert r.json()["first_run"] is False


def test_status_fails_closed_when_config_missing(signing_key, admin_user, guest_user) -> None:
    db = _seeded(admin_user, guest_user)
    db.rows["config"] = []
    with TestClient(_make_app(signing_key, db)) as c:
        assert c.get("/api/setup/status").json()["first_run"] is False


# --- admin view ---


def test_get_setup_reports_current_step_and_default_password(signing_key, admin_user, guest_user) -> None:
    admin_user.password_must_change = True
    db = _seeded(admin_user, guest_user)
    with TestClient(_make_app(signing_key, db)) as c:
        r = c.get("/api/setup", headers=_auth(signing_key, admin_user))
    assert r.status_code == 200, r.text  # GET /api/setup is on the must-change allow-list
    body = r.json()
    assert body["current_step"] == "account"
    assert body["admin_default_password"] is True
    assert body["progress"] == {}
    assert body["completed_at"] is None
    assert body["checklist_dismissed"] is False


def test_account_reads_done_once_password_changed(signing_key, admin_user, guest_user) -> None:
    db = _seeded(admin_user, guest_user)
    with TestClient(_make_app(signing_key, db)) as c:
        body = c.get("/api/setup", headers=_auth(signing_key, admin_user)).json()
    assert body["progress"]["account"]["state"] == "done"
    assert body["current_step"] == "system"
    assert body["admin_default_password"] is False


def test_current_step_is_finish_when_every_step_recorded(signing_key, admin_user, guest_user) -> None:
    db = _seeded(admin_user, guest_user)
    db.rows["config"][0].setup_progress = {
        s: {"state": "done", "at": None}
        for s in (
            "account",
            "system",
            "drives",
            "makemkv",
            "metadata",
            "discs",
            "transcoding",
            "notifications",
            "finish",
        )
    }
    with TestClient(_make_app(signing_key, db)) as c:
        assert c.get("/api/setup", headers=_auth(signing_key, admin_user)).json()["current_step"] == "finish"


def test_put_step_records_state_and_advances(signing_key, admin_user, guest_user) -> None:
    db = _seeded(admin_user, guest_user)
    with TestClient(_make_app(signing_key, db)) as c:
        r = c.put("/api/setup/steps/system", json={"state": "attention"}, headers=_auth(signing_key, admin_user))
    assert r.status_code == 200, r.text
    assert r.json()["progress"]["system"]["state"] == "attention"
    assert r.json()["current_step"] == "drives"
    assert db.rows["config"][0].setup_progress["system"]["state"] == "attention"
    assert db.committed


def test_put_unknown_step_404(signing_key, admin_user, guest_user) -> None:
    db = _seeded(admin_user, guest_user)
    with TestClient(_make_app(signing_key, db)) as c:
        r = c.put("/api/setup/steps/bogus", json={"state": "done"}, headers=_auth(signing_key, admin_user))
    assert r.status_code == 404


def test_put_rejects_unknown_state(signing_key, admin_user, guest_user) -> None:
    db = _seeded(admin_user, guest_user)
    with TestClient(_make_app(signing_key, db)) as c:
        r = c.put("/api/setup/steps/drives", json={"state": "maybe"}, headers=_auth(signing_key, admin_user))
    assert r.status_code == 422


def test_put_refused_while_password_must_change(signing_key, admin_user, guest_user) -> None:
    admin_user.password_must_change = True
    db = _seeded(admin_user, guest_user)
    with TestClient(_make_app(signing_key, db)) as c:
        r = c.put("/api/setup/steps/system", json={"state": "done"}, headers=_auth(signing_key, admin_user))
    assert r.status_code == 403  # PUT is not on the must-change allow-list


def test_put_account_only_done(signing_key, admin_user, guest_user) -> None:
    db = _seeded(admin_user, guest_user)
    with TestClient(_make_app(signing_key, db)) as c:
        r = c.put("/api/setup/steps/account", json={"state": "skipped"}, headers=_auth(signing_key, admin_user))
        ok = c.put("/api/setup/steps/account", json={"state": "done"}, headers=_auth(signing_key, admin_user))
    assert r.status_code == 409
    assert ok.status_code == 200


def test_complete_marks_pending_skipped_and_finish_done(signing_key, admin_user, guest_user) -> None:
    db = _seeded(admin_user, guest_user)
    db.rows["config"][0].setup_progress = {"drives": {"state": "attention", "at": None}}
    with TestClient(_make_app(signing_key, db)) as c:
        body = c.post("/api/setup/complete", headers=_auth(signing_key, admin_user)).json()
    assert body["completed_at"] is not None
    assert body["progress"]["drives"]["state"] == "attention"
    assert body["progress"]["notifications"]["state"] == "skipped"
    assert body["progress"]["finish"]["state"] == "done"
    assert db.rows["config"][0].setup_completed_at is not None


def test_restart_clears_completion_and_dismissal_keeps_progress(signing_key, admin_user, guest_user) -> None:
    db = _seeded(admin_user, guest_user)
    cfg = db.rows["config"][0]
    cfg.setup_completed_at = datetime.now(timezone.utc)
    cfg.setup_checklist_dismissed_at = datetime.now(timezone.utc)
    cfg.setup_progress = {"drives": {"state": "done", "at": None}, "finish": {"state": "done", "at": None}}
    with TestClient(_make_app(signing_key, db)) as c:
        body = c.post("/api/setup/restart", headers=_auth(signing_key, admin_user)).json()
    assert body["completed_at"] is None
    assert body["checklist_dismissed"] is False
    assert body["progress"]["drives"]["state"] == "done"
    assert "finish" not in body["progress"]
    assert body["current_step"] == "system"


def test_dismiss_checklist(signing_key, admin_user, guest_user) -> None:
    db = _seeded(admin_user, guest_user)
    with TestClient(_make_app(signing_key, db)) as c:
        body = c.post("/api/setup/checklist/dismiss", headers=_auth(signing_key, admin_user)).json()
    assert body["checklist_dismissed"] is True
    assert db.rows["config"][0].setup_checklist_dismissed_at is not None


def test_system_attention_reconciles_to_done_when_checks_pass(signing_key, admin_user, guest_user, monkeypatch) -> None:
    db = _seeded(admin_user, guest_user)
    db.rows["config"][0].setup_progress = {"system": {"state": "attention", "at": None}}

    async def ok(request, session) -> bool:
        return True

    monkeypatch.setattr(setup_router, "_diagnostics_ok", ok)
    with TestClient(_make_app(signing_key, db)) as c:
        body = c.get("/api/setup", headers=_auth(signing_key, admin_user)).json()
    assert body["progress"]["system"]["state"] == "done"
    assert db.rows["config"][0].setup_progress["system"]["state"] == "done"


def test_system_attention_stays_when_checks_still_fail(signing_key, admin_user, guest_user) -> None:
    db = _seeded(admin_user, guest_user)
    db.rows["config"][0].setup_progress = {"system": {"state": "attention", "at": None}}
    with TestClient(_make_app(signing_key, db)) as c:
        body = c.get("/api/setup", headers=_auth(signing_key, admin_user)).json()
    assert body["progress"]["system"]["state"] == "attention"


def test_config_missing_is_500(signing_key, admin_user, guest_user) -> None:
    db = _seeded(admin_user, guest_user)
    db.rows["config"] = []
    with TestClient(_make_app(signing_key, db)) as c:
        assert c.get("/api/setup", headers=_auth(signing_key, admin_user)).status_code == 500


def test_guest_cannot_read_or_write(signing_key, admin_user, guest_user) -> None:
    guest_user.disabled = False
    db = _seeded(admin_user, guest_user)
    with TestClient(_make_app(signing_key, db)) as c:
        assert c.get("/api/setup").status_code == 403
        assert c.post("/api/setup/complete").status_code == 403


# --- system-step relevance (shared with the UI's SystemStep) ---


def _diag(*checks: tuple[str, str]) -> SystemDiagnosticsResponse:
    return SystemDiagnosticsResponse(
        status="warning", checks=[SystemDiagnosticCheck(name=n, status=s) for n, s in checks], paths=[]
    )


def test_system_checks_ok_ignores_later_step_warnings() -> None:
    # drives / makemkv / keydb / sdf belong to later steps; they never block "system".
    resp = _diag(("config", "ok"), ("MEDIA_ROOT", "ok"), ("drives", "warning"), ("makemkv_key", "warning"))
    assert setup_router.system_checks_ok(resp) is True


def test_system_checks_ok_false_on_ripper_or_root_problem() -> None:
    assert setup_router.system_checks_ok(_diag(("ripper_manager", "warning"))) is False
    assert setup_router.system_checks_ok(_diag(("RAW_ROOT", "error"))) is False


async def test_diagnostics_ok_uses_collect_diagnostics(monkeypatch) -> None:
    monkeypatch.undo()  # drop the autouse stub for this test

    async def fake_collect(request, db) -> SystemDiagnosticsResponse:
        return _diag(("config", "ok"), ("transcoder", "ok"))

    monkeypatch.setattr(setup_router, "collect_diagnostics", fake_collect)
    assert await setup_router._diagnostics_ok(object(), object()) is True
