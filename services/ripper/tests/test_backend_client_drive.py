import json
import os

os.environ.setdefault("ARM_DRIVE_DEV", "/dev/sr0")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

import httpx
import pytest

from arm_ripper.backend_client import BackendClient


def _client(handler) -> BackendClient:
    c = BackendClient("https://backend", "tok", hostname="h")
    c._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://backend")
    return c


async def test_update_device_path_patches_the_ripper_endpoint() -> None:
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        seen["body"] = json.loads(req.read())
        return httpx.Response(204)

    c = _client(handler)
    await c.update_device_path(drive_id="drv_1", device_path="/dev/sr2")
    assert seen == {
        "method": "PATCH",
        "path": "/api/ripper/drives/drv_1/device-path",
        "body": {"device_path": "/dev/sr2"},
    }


async def test_update_device_path_swallows_404_until_the_backend_side_lands() -> None:
    c = _client(lambda req: httpx.Response(404))
    await c.update_device_path(drive_id="drv_1", device_path="/dev/sr2")  # must not raise


async def test_update_device_path_raises_on_server_error() -> None:
    c = _client(lambda req: httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await c.update_device_path(drive_id="drv_1", device_path="/dev/sr2")


async def test_get_drive_returns_none_on_404() -> None:
    c = _client(lambda req: httpx.Response(404))
    assert await c.get_drive("drv_1") is None


async def test_get_drive_parses_a_drive() -> None:
    # Drive.model_validate (pydantic validation) requires every field that
    # lacks an explicit pydantic-side default, which for a SQLModel table
    # model includes several nullable-in-the-DB columns (last_seen_at,
    # media_status, media_status_at, drive_mode, default_session_id,
    # created_at, updated_at) — unlike Drive(...) construction, which fills
    # those from their Python-side defaults. Pass them explicitly as None.
    body = {
        "id": "drv_1",
        "hostname": "arm-ripper-x",
        "device_path": "/dev/sr3",
        "status": "online",
        "last_seen_at": None,
        "media_status": None,
        "media_status_at": None,
        "drive_mode": None,
        "default_session_id": None,
        "created_at": None,
        "updated_at": None,
    }
    c = _client(lambda req: httpx.Response(200, json=body))
    d = await c.get_drive("drv_1")
    assert d is not None and d.device_path == "/dev/sr3"
