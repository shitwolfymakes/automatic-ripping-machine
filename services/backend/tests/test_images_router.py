"""GET /api/images/proxy — allowlist, scheme guard, cache, negative-cache, no-auth."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import httpx  # noqa: E402
import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend import image_cache  # noqa: E402
from arm_backend.routers import images as images_router  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(image_cache.settings, "ARM_IMAGE_CACHE_PATH", str(tmp_path))
    image_cache.reset()
    images_router._NEGATIVE_CACHE.clear()
    app = FastAPI()
    app.include_router(images_router.router)
    with TestClient(app) as c:
        yield c
    image_cache.reset()


class _FakeStreamResp:
    def __init__(self, content: bytes, content_type: str):
        self._content = content
        self.headers = {"content-type": content_type}

    def raise_for_status(self) -> None:
        return None

    async def aiter_bytes(self):
        # chunk it to exercise the streaming accumulator
        for i in range(0, len(self._content), 4096):
            yield self._content[i : i + 4096]


def _patch_fetch(monkeypatch, *, content=b"IMG", content_type="image/png", raise_error=False):
    class _FakeStreamCtx:
        def __init__(self, resp, raise_error):
            self._resp = resp
            self._raise = raise_error

        async def __aenter__(self):
            if self._raise:
                raise httpx.HTTPError("boom")
            return self._resp

        async def __aexit__(self, *a):
            return False

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, method, url):
            return _FakeStreamCtx(_FakeStreamResp(content, content_type), raise_error)

    monkeypatch.setattr(images_router.httpx, "AsyncClient", _FakeClient)


def test_rejects_non_allowlisted_host(client):
    r = client.get("/api/images/proxy", params={"url": "https://evil.example/x.jpg"})
    assert r.status_code == 404
    assert "not allowed" in r.json()["detail"]


def test_extra_image_host_not_rejected(client, monkeypatch):
    # ARM_EXTRA_IMAGE_HOSTS adds an operator host; a proxy request to it must NOT
    # hit the "not allowed" SSRF-guard path. It proceeds to the fetch (which we
    # stub to succeed), proving the host is accepted, not rejected.
    monkeypatch.setattr(images_router.settings, "ARM_EXTRA_IMAGE_HOSTS", ["posters.lan"])
    _patch_fetch(monkeypatch, content=b"IMG", content_type="image/png")
    r = client.get("/api/images/proxy", params={"url": "https://posters.lan/x.jpg"})
    assert r.status_code == 200
    assert r.content == b"IMG"


def test_rejects_non_http_scheme(client):
    r = client.get("/api/images/proxy", params={"url": "ftp://image.tmdb.org/x.jpg"})
    assert r.status_code == 404
    assert "HTTP" in r.json()["detail"]


def test_fetches_caches_and_serves_allowlisted(client, monkeypatch):
    _patch_fetch(monkeypatch, content=b"IMG", content_type="image/png")
    url = "https://image.tmdb.org/t/p/w500/x.jpg"
    r = client.get("/api/images/proxy", params={"url": url})
    assert r.status_code == 200
    assert r.content == b"IMG"
    assert r.headers["content-type"] == "image/png"
    assert "max-age=604800" in r.headers["cache-control"]
    _patch_fetch(monkeypatch, raise_error=True)
    r2 = client.get("/api/images/proxy", params={"url": url})
    assert r2.status_code == 200
    assert r2.content == b"IMG"


def test_unsafe_content_type_coerced(client, monkeypatch):
    _patch_fetch(monkeypatch, content=b"IMG", content_type="text/html")
    r = client.get("/api/images/proxy", params={"url": "https://coverartarchive.org/x"})
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"


def test_fetch_failure_negative_caches(client, monkeypatch):
    _patch_fetch(monkeypatch, raise_error=True)
    url = "https://ia.media-imdb.com/x.jpg"
    r = client.get("/api/images/proxy", params={"url": url})
    assert r.status_code == 404
    assert "Failed to fetch" in r.json()["detail"]
    assert url in images_router._NEGATIVE_CACHE
    r2 = client.get("/api/images/proxy", params={"url": url})
    assert r2.status_code == 404
    assert "unavailable" in r2.json()["detail"]


def test_oversized_image_rejected(client, monkeypatch):
    big = b"x" * (2 * 1024 * 1024 + 1)
    _patch_fetch(monkeypatch, content=big, content_type="image/jpeg")
    url = "https://m.media-amazon.com/big.jpg"
    r = client.get("/api/images/proxy", params={"url": url})
    assert r.status_code == 404
    assert "too large" in r.json()["detail"]


def test_oversized_negative_cached(client, monkeypatch):
    big = b"x" * (2 * 1024 * 1024 + 1)
    _patch_fetch(monkeypatch, content=big, content_type="image/jpeg")
    url = "https://m.media-amazon.com/big2.jpg"
    r = client.get("/api/images/proxy", params={"url": url})
    assert r.status_code == 404
    assert url in images_router._NEGATIVE_CACHE


def test_endpoint_requires_no_auth(client, monkeypatch):
    _patch_fetch(monkeypatch, content=b"OK", content_type="image/webp")
    r = client.get("/api/images/proxy", params={"url": "https://image.tmdb.org/a.webp"})
    assert r.status_code == 200
