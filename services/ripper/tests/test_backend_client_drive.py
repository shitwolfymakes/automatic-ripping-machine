import json
import logging
import os

os.environ.setdefault("ARM_DRIVE_DEV", "/dev/sr0")
os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
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


async def test_update_device_path_swallows_404_until_the_backend_side_lands(caplog) -> None:
    caplog.set_level(logging.INFO, logger="arm_ripper.backend_client")
    c = _client(lambda req: httpx.Response(404))
    await c.update_device_path(drive_id="drv_1", device_path="/dev/sr2")  # must not raise
    # The drill reads this line: a 404 here is a missing endpoint, not a fault.
    assert any("device-path endpoint absent (404)" in r.message for r in caplog.records)


async def test_update_device_path_raises_on_server_error() -> None:
    c = _client(lambda req: httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await c.update_device_path(drive_id="drv_1", device_path="/dev/sr2")


async def test_get_drive_returns_none_on_404(caplog) -> None:
    # Debug, not info: while the drive is absent this is polled every tick.
    caplog.set_level(logging.DEBUG, logger="arm_ripper.backend_client")
    c = _client(lambda req: httpx.Response(404))
    assert await c.get_drive("drv_1") is None
    rec = [r for r in caplog.records if "not found (404)" in r.message]
    assert len(rec) == 1 and rec[0].levelno == logging.DEBUG


async def test_register_posts_by_drive_id() -> None:
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        seen["body"] = json.loads(req.read())
        return httpx.Response(
            200,
            json={
                "id": "drv_1",
                "hostname": "arm-ripper-abc",
                "device_path": "/dev/sr0",
                "status": "online",
                "lifecycle": "enrolled",
                "present": True,
                "serial": None,
                "by_id_name": "usb-X-0:0",
                "sysfs_port": None,
                "identity_kind": None,
                "vendor": None,
                "model": None,
                "last_error": None,
                "display_name": None,
                "default_session_id": None,
                "drive_mode": "auto",
                "media_status": None,
                "media_status_at": None,
                "last_seen_at": None,
                "created_at": "2026-09-04T00:00:00Z",
                "updated_at": "2026-09-04T00:00:00Z",
            },
        )

    c = _client(handler)
    drive = await c.register(
        drive_id="drv_1", hostname="arm-ripper-abc", device_path="/dev/sr0", ripper_version="3", by_id_name="usb-X-0:0"
    )
    assert drive.id == "drv_1"
    assert seen["path"] == "/api/ripper/register"
    assert seen["body"] == {
        "drive_id": "drv_1",
        "hostname": "arm-ripper-abc",
        "device_path": "/dev/sr0",
        "ripper_version": "3",
        "hw_caps": {},
        "by_id_name": "usb-X-0:0",
    }


@pytest.mark.parametrize("code", [404, 409])
async def test_register_raises_refused_on_fatal_answers(code: int) -> None:
    from arm_ripper.backend_client import RegisterRefused

    c = _client(lambda req: httpx.Response(code, json={"detail": "identity mismatch: x"}))
    with pytest.raises(RegisterRefused, match="identity mismatch"):
        await c.register(drive_id="drv_1", hostname="h", device_path="/dev/sr0", ripper_version="3", by_id_name=None)


async def test_register_5xx_is_a_plain_http_error() -> None:
    c = _client(lambda req: httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        await c.register(drive_id="drv_1", hostname="h", device_path="/dev/sr0", ripper_version="3", by_id_name=None)


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
