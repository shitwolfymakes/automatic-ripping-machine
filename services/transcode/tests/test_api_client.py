"""Unit tests for arm_transcode.api_client.BackendClient: register and cover_art."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from arm_common.schemas import HardwareCaps
from arm_transcode import api_client
from arm_transcode.api_client import BackendClient


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {"ok": True}


class _FakeHttp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def post(self, url: str, json: dict[str, Any]) -> _FakeResponse:
        self.calls.append((url, json))
        return _FakeResponse()


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> tuple[BackendClient, _FakeHttp]:
    c = BackendClient.__new__(BackendClient)  # skip __init__: it builds a real TLS client
    c._hostname = "host-1"
    fake = _FakeHttp()
    c._client = fake  # type: ignore[assignment]
    monkeypatch.setattr(api_client.RegisterTranscoderResponse, "model_validate", staticmethod(lambda d: d))
    return c, fake


async def test_register_posts_task_host_and_caps(client: tuple[BackendClient, _FakeHttp]) -> None:
    c, fake = client
    result = await c.register(task_id="t1", hw_caps=HardwareCaps(cpu_count=2))
    assert result == {"ok": True}
    url, body = fake.calls[0]
    assert url == "/api/transcoder/register"
    assert body["task_id"] == "t1"
    assert body["hostname"] == "host-1"


async def test_register_sends_the_baked_schema_hash(
    client: tuple[BackendClient, _FakeHttp], monkeypatch: pytest.MonkeyPatch
) -> None:
    c, fake = client
    monkeypatch.setattr(api_client, "baked_schema_hash", lambda: "abc123")
    await c.register(task_id="t1", hw_caps=HardwareCaps(cpu_count=2))
    assert fake.calls[0][1]["schema_hash"] == "abc123"


async def test_register_sends_no_hash_without_a_baked_schema(
    client: tuple[BackendClient, _FakeHttp], monkeypatch: pytest.MonkeyPatch
) -> None:
    c, fake = client
    monkeypatch.setattr(api_client, "baked_schema_hash", lambda: None)
    await c.register(task_id="t1", hw_caps=HardwareCaps(cpu_count=2))
    assert fake.calls[0][1]["schema_hash"] is None


def _cover_client(handler: httpx.MockTransport) -> BackendClient:
    c = BackendClient.__new__(BackendClient)  # skip __init__: it builds a real TLS client
    c._hostname = "host-1"
    c._client = httpx.AsyncClient(base_url="https://backend:8443", transport=handler)
    return c


async def test_cover_art_returns_the_image_and_its_type() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, content=b"JPEG", headers={"content-type": "image/jpeg"})

    c = _cover_client(httpx.MockTransport(handler))
    try:
        assert await c.cover_art("t1") == (b"JPEG", "image/jpeg")
    finally:
        await c.close()
    assert seen == ["/api/transcoder/tasks/t1/cover-art"]


async def test_cover_art_none_when_the_track_has_none() -> None:
    c = _cover_client(httpx.MockTransport(lambda _r: httpx.Response(404, json={"detail": "no cover art"})))
    try:
        assert await c.cover_art("t1") is None
    finally:
        await c.close()


async def test_cover_art_raises_on_a_backend_error() -> None:
    c = _cover_client(httpx.MockTransport(lambda _r: httpx.Response(500)))
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await c.cover_art("t1")
    finally:
        await c.close()
