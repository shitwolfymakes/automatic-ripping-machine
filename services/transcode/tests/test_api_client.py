"""Unit tests for arm_transcode.api_client.BackendClient.register."""

from __future__ import annotations

from typing import Any

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
