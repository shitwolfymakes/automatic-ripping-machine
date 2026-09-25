"""GPU inventory router (/api/gpus): list, enable/disable, delete, and the
claimed-row delete guard. The table is DB-authoritative (seed-once is covered
in test_main_unit); this drives the management surface the Settings > GPUs
card calls."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import secrets  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import gpus as gpus_router  # noqa: E402
from arm_common import Gpu, User  # noqa: E402
from arm_common.enums import GpuStatus, GpuVendor  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


def _app(gpus: list[Gpu]) -> tuple[FastAPI, str, FakeSession]:
    key = secrets.token_bytes(32)
    db = FakeSession()
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows["gpus"] = gpus

    app = FastAPI()
    app.state.signing_key = key
    app.include_router(gpus_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", key)
    return app, token, db


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _gpu(gpu_id: str = "gpu_1", vendor: GpuVendor = GpuVendor.QSV, **kw: object) -> Gpu:
    defaults: dict = {
        "id": gpu_id,
        "vendor": vendor,
        "device_path": "/dev/dri/renderD128",
        "encoder_kinds": ["h264", "h265"],
        "status": GpuStatus.AVAILABLE,
        "enabled": True,
    }
    defaults.update(kw)
    return Gpu(**defaults)


def test_list_returns_inventory() -> None:
    app, token, _db = _app([_gpu(), _gpu("gpu_2", GpuVendor.VAAPI, device_path="/dev/dri/renderD129")])
    with TestClient(app) as c:
        r = c.get("/api/gpus", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 2
    assert {g["vendor"] for g in body} == {"qsv", "vaapi"}
    assert all(g["enabled"] is True for g in body)


def test_patch_toggles_enabled() -> None:
    app, token, db = _app([_gpu()])
    with TestClient(app) as c:
        r = c.patch("/api/gpus/gpu_1", json={"enabled": False}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is False
    assert db.rows["gpus"][0].enabled is False


def test_patch_rejects_unknown_fields() -> None:
    # extra="forbid": only the operator switch is editable — hardware facts
    # (vendor, path, encoder kinds) are re-seeded, never patched.
    app, token, _db = _app([_gpu()])
    with TestClient(app) as c:
        r = c.patch("/api/gpus/gpu_1", json={"enabled": False, "vendor": "nvenc"}, headers=_auth(token))
    assert r.status_code == 422


def test_patch_unknown_gpu_404() -> None:
    app, token, _db = _app([])
    with TestClient(app) as c:
        r = c.patch("/api/gpus/gpu_missing", json={"enabled": False}, headers=_auth(token))
    assert r.status_code == 404


def test_delete_removes_row() -> None:
    app, token, db = _app([_gpu()])
    with TestClient(app) as c:
        r = c.delete("/api/gpus/gpu_1", headers=_auth(token))
    assert r.status_code == 204
    assert db.rows["gpus"] == []


def test_delete_claimed_gpu_409() -> None:
    app, token, db = _app([_gpu(status=GpuStatus.BUSY, claimed_by_task_id="tt_running")])
    with TestClient(app) as c:
        r = c.delete("/api/gpus/gpu_1", headers=_auth(token))
    assert r.status_code == 409
    assert len(db.rows["gpus"]) == 1  # row survives
