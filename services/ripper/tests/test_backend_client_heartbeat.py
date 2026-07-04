import json

import httpx
import pytest

from arm_common import DriveMediaStatus
from arm_common.schemas import HostResourcesSnapshot, MemoryInfo
from arm_ripper.backend_client import BackendClient


@pytest.mark.asyncio
async def test_heartbeat_posts_hostname_and_resources(monkeypatch):
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(204)

    transport = httpx.MockTransport(handler)
    client = BackendClient(base_url="https://backend", service_token="t", hostname="ripper-sr0")
    client._client = httpx.AsyncClient(transport=transport, base_url="https://backend")

    snap = HostResourcesSnapshot(
        cpu_percent=2.0,
        cpu_temp=0.0,
        memory=MemoryInfo(total_gb=8.0, used_gb=1.0, free_gb=7.0, percent=12.5),
        storage=[],
    )
    await client.heartbeat(
        drive_id="drv_1", media_status=DriveMediaStatus.LOADED, hostname="ripper-sr0", resources=snap
    )
    assert captured["body"]["hostname"] == "ripper-sr0"
    assert captured["body"]["resources"]["cpu_percent"] == 2.0
