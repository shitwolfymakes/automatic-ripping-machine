"""`BackendClient.cover_art` against a mocked Backend."""

from __future__ import annotations

import httpx
import pytest

from arm_transcode.api_client import BackendClient


def _client(handler: httpx.MockTransport) -> BackendClient:
    api = BackendClient(base_url="https://backend:8443", service_token="tok", hostname="host1")
    api._client = httpx.AsyncClient(base_url="https://backend:8443", transport=handler)
    return api


@pytest.mark.asyncio
async def test_cover_art_returns_the_image_and_its_type() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, content=b"JPEG", headers={"content-type": "image/jpeg"})

    api = _client(httpx.MockTransport(handler))
    try:
        assert await api.cover_art("t1") == (b"JPEG", "image/jpeg")
    finally:
        await api.close()
    assert seen == ["/api/transcoder/tasks/t1/cover-art"]


@pytest.mark.asyncio
async def test_cover_art_none_when_the_track_has_none() -> None:
    api = _client(httpx.MockTransport(lambda _r: httpx.Response(404, json={"detail": "no cover art"})))
    try:
        assert await api.cover_art("t1") is None
    finally:
        await api.close()


@pytest.mark.asyncio
async def test_cover_art_raises_on_a_backend_error() -> None:
    api = _client(httpx.MockTransport(lambda _r: httpx.Response(500)))
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await api.cover_art("t1")
    finally:
        await api.close()
