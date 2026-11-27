"""GET /api/system/environment — grouped env report + container specs."""

from __future__ import annotations

from datetime import datetime, timezone

import json
import secrets
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from arm_backend.db import get_session
from arm_backend.jwt_utils import issue_access_token
from arm_backend.routers import system as system_router
from arm_common import Config, Drive, DriveLifecycle, Gpu, User
from arm_common.models.user import GUEST_ROLE
from arm_common.enums import DriveStatus, GpuVendor

from tests._fakes import FakeSession

_TOKEN = "secret-token"


def _app(monkeypatch: pytest.MonkeyPatch, *, guest_enabled: bool = False) -> tuple[FastAPI, str]:
    monkeypatch.setattr(
        system_router,
        "settings",
        system_router.settings.model_copy(update={"ARM_SERVICE_TOKEN": _TOKEN}),
    )
    db = FakeSession()
    db.rows["users"] = [
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False),
        User(
            id="usr_guest",
            username="guest",
            password_hash="x",
            password_must_change=False,
            role=GUEST_ROLE,
            disabled=not guest_enabled,
        ),
    ]
    db.rows["config"] = [Config(id=1)]
    db.rows["drives"] = [
        Drive(
            id="drv_on0000000000000000000001",
            hostname="h1",
            device_path="/dev/sr0",
            lifecycle=DriveLifecycle.ENROLLED,
            status=DriveStatus.ONLINE,
        )
    ]
    db.rows["gpus"] = [
        Gpu(
            id="gpu_1",
            vendor=GpuVendor.VAAPI,
            device_path="/dev/dri/renderD128",
            enabled=True,
            probed_at=datetime.now(timezone.utc),
        ),
        Gpu(id="gpu_2", vendor=GpuVendor.NVENC, device_path="/dev/nvidia0", enabled=True),
    ]

    app = FastAPI()
    key = secrets.token_bytes(32)
    app.state.signing_key = key
    app.include_router(system_router.router)

    async def _override() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override
    token, _ = issue_access_token("usr_admin", "admin", key)
    return app, token


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    app, token = _app(monkeypatch)
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as c:
        yield c


@pytest.fixture
def client_no_token(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    app, _ = _app(monkeypatch)
    with TestClient(app) as c:
        yield c


def test_requires_auth(client_no_token: TestClient) -> None:
    assert client_no_token.get("/api/system/environment").status_code == 401


def test_anonymous_guest_is_forbidden(monkeypatch: pytest.MonkeyPatch) -> None:
    app, _ = _app(monkeypatch, guest_enabled=True)
    with TestClient(app) as c:
        assert c.get("/api/system/environment").status_code == 403


def test_returns_groups_containers_and_masks(client: TestClient) -> None:
    r = client.get("/api/system/environment")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["version"]
    keys = {v["key"]: v for g in body["groups"] for v in g["vars"]}
    assert keys["DATABASE_URL"]["value"] is None
    assert any(c["kind"] == "ripper" for c in body["containers"])
    assert any(c["label"] == "CPU" for c in body["containers"])
    assert body["summary"]["gpus"] == ["vaapi /dev/dri/renderD128"]
    assert _TOKEN not in json.dumps(body)


def test_no_ripper_manager_still_200(client: TestClient) -> None:
    body = client.get("/api/system/environment").json()
    assert body["summary"]["host_paths_set"] is None


class _Manager:
    def host_paths_set(self) -> bool:
        return True


class _Images:
    def __init__(self) -> None:
        self.asked: list[str] = []

    def image_exists(self, image: str) -> bool:
        self.asked.append(image)
        return True


class _Dispatcher:
    def __init__(self) -> None:
        self.images = _Images()


def test_running_services_feed_the_summary_and_the_transcode_image(monkeypatch: pytest.MonkeyPatch) -> None:
    app, token = _app(monkeypatch)
    monkeypatch.setattr(
        system_router,
        "settings",
        system_router.settings.model_copy(update={"ARM_TRANSCODE_IMAGE": "ghcr.io/x/arm-transcode:3.1.0"}),
    )
    app.state.ripper_manager = _Manager()
    app.state.transcode_dispatcher = dispatcher = _Dispatcher()
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as c:
        body = c.get("/api/system/environment").json()
    assert body["summary"]["host_paths_set"] is True
    images = {c["label"]: c["image"] for c in body["containers"] if c["kind"] == "transcode"}
    assert images["vaapi /dev/dri/renderD128"] == "ghcr.io/x/arm-transcode:3.1.0-amd"
    assert images["CPU"] == "ghcr.io/x/arm-transcode:3.1.0"
    assert dispatcher.images.asked == ["ghcr.io/x/arm-transcode:3.1.0-amd"]


def test_no_dispatcher_shows_the_base_transcode_image(monkeypatch: pytest.MonkeyPatch) -> None:
    app, token = _app(monkeypatch)
    monkeypatch.setattr(
        system_router,
        "settings",
        system_router.settings.model_copy(update={"ARM_TRANSCODE_IMAGE": "ghcr.io/x/arm-transcode:3.1.0"}),
    )
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as c:
        body = c.get("/api/system/environment").json()
    images = {c["image"] for c in body["containers"] if c["kind"] == "transcode"}
    assert images == {"ghcr.io/x/arm-transcode:3.1.0"}
