"""GET /api/ripper/drives/{id} and PATCH .../device-path — the two calls Plan 1's ripper already makes."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from fastapi.testclient import TestClient  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402
from tests.test_ripper_heartbeat import _make_app, _seed, _service_auth  # noqa: E402


def test_get_drive_returns_the_table_model_shape() -> None:
    db = FakeSession()
    _seed(db)
    with TestClient(_make_app(db)) as client:
        r = client.get("/api/ripper/drives/drv_x", headers=_service_auth())
    assert r.status_code == 200
    body = r.json()
    # Plan 1's client does Drive.model_validate(body): every column must be present, nullable ones as null.
    for key in ("id", "hostname", "device_path", "status", "lifecycle", "present", "by_id_name", "last_seen_at"):
        assert key in body, key


def test_get_drive_unknown_is_404() -> None:
    db = FakeSession()
    with TestClient(_make_app(db)) as client:
        assert client.get("/api/ripper/drives/drv_nope", headers=_service_auth()).status_code == 404


def test_get_drive_requires_service_token() -> None:
    db = FakeSession()
    _seed(db)
    with TestClient(_make_app(db)) as client:
        assert client.get("/api/ripper/drives/drv_x").status_code in (401, 403)


def test_patch_device_path_updates_the_row() -> None:
    db = FakeSession()
    drive = _seed(db)
    with TestClient(_make_app(db)) as client:
        r = client.patch(
            "/api/ripper/drives/drv_x/device-path", json={"device_path": "/dev/sr2"}, headers=_service_auth()
        )
    assert r.status_code == 204
    assert drive.device_path == "/dev/sr2"


def test_patch_device_path_unknown_is_404() -> None:
    db = FakeSession()
    with TestClient(_make_app(db)) as client:
        r = client.patch(
            "/api/ripper/drives/drv_nope/device-path", json={"device_path": "/dev/sr2"}, headers=_service_auth()
        )
    assert r.status_code == 404
