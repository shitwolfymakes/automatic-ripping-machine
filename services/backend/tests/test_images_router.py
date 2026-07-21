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
    def __init__(self, content: bytes, content_type: str, status_code: int = 200):
        self._content = content
        self.headers = {"content-type": content_type}
        self.is_redirect = False
        self.status_code = status_code

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


# --- redirect following (Cover Art Archive 307s to archive.org dynamic nodes) ---


class _RedirectResp:
    """A 3xx redirect response (no body), exposing httpx's redirect surface."""

    def __init__(self, status_code: int, location: str):
        self.status_code = status_code
        self.headers = {"location": location}
        self.is_redirect = True

    def raise_for_status(self) -> None:
        return None

    async def aiter_bytes(self):
        if False:
            yield b""  # pragma: no cover - redirect responses have no body


class _ImageResp:
    """A terminal 200 image response."""

    def __init__(self, content: bytes, content_type: str):
        self.status_code = 200
        self._content = content
        self.headers = {"content-type": content_type}
        self.is_redirect = False

    def raise_for_status(self) -> None:
        return None

    async def aiter_bytes(self):
        yield self._content


class _NotFoundResp:
    """A terminal 404 (CAA returns this for an entity with no uploaded art)."""

    def __init__(self) -> None:
        self.status_code = 404
        self.headers: dict[str, str] = {}
        self.is_redirect = False

    def raise_for_status(self) -> None:  # pragma: no cover - 404 handled before this
        raise httpx.HTTPStatusError("404", request=None, response=None)

    async def aiter_bytes(self):
        if False:
            yield b""  # pragma: no cover - 404 has no body we read


def _patch_fetch_recording(monkeypatch, route):
    """Stub httpx, dispatching each stream() by the requested URL.

    `route` maps a substring → response item, where an item is a ('image',
    bytes, type) tuple or the sentinel '404'. Records every requested URL on the
    returned list so tests can assert which entities were (and weren't) fetched.
    """
    requested: list[str] = []

    class _Ctx:
        def __init__(self, resp):
            self._resp = resp

        async def __aenter__(self):
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
            requested.append(url)
            for needle, item in route.items():
                if needle in url:
                    if item == "404":
                        return _Ctx(_NotFoundResp())
                    return _Ctx(_ImageResp(item[1], item[2]))
            return _Ctx(_NotFoundResp())

    monkeypatch.setattr(images_router.httpx, "AsyncClient", _FakeClient)
    return requested


def _patch_fetch_chain(monkeypatch, hops):
    """Stub httpx so successive .stream() calls return the queued responses in order.

    `hops` is a list of redirect tuples ending in an image, e.g.
    [(307, 'https://archive.org/dl/x.jpg'), (302, 'https://dn1.ca.archive.org/x.jpg'),
     ('image', b'BYTES', 'image/jpeg')].
    """
    queue = list(hops)

    class _Ctx:
        def __init__(self, resp):
            self._resp = resp

        async def __aenter__(self):
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
            item = queue.pop(0)
            if isinstance(item, tuple) and item[0] == "image":
                return _Ctx(_ImageResp(item[1], item[2]))
            status, location = item
            return _Ctx(_RedirectResp(status, location))

    monkeypatch.setattr(images_router.httpx, "AsyncClient", _FakeClient)


def test_follows_caa_redirect_chain_to_image(client, monkeypatch):
    # coverartarchive.org 307 -> archive.org 302 -> dn*.ca.archive.org (the JPG).
    _patch_fetch_chain(
        monkeypatch,
        [
            (307, "https://archive.org/download/mbid-x/cover.jpg"),
            (302, "https://dn710304.ca.archive.org/0/items/mbid-x/cover.jpg"),
            ("image", b"COVER", "image/jpeg"),
        ],
    )
    r = client.get(
        "/api/images/proxy",
        params={"url": "https://coverartarchive.org/release/mbid-x/front"},
    )
    assert r.status_code == 200
    assert r.content == b"COVER"
    assert r.headers["content-type"] == "image/jpeg"


def test_redirect_to_disallowed_host_blocked(client, monkeypatch):
    # A redirect that tries to escape to a non-allowlisted host must be refused
    # (SSRF guard preserved across hops), not followed — the disallowed image is
    # never returned. The chain is abandoned (404), not chased to the SSRF host.
    _patch_fetch_chain(
        monkeypatch,
        [
            (307, "http://169.254.169.254/latest/meta-data/"),
            ("image", b"SECRET", "image/jpeg"),
        ],
    )
    r = client.get(
        "/api/images/proxy",
        params={"url": "https://coverartarchive.org/release/mbid-x/front"},
    )
    assert r.status_code == 404
    assert r.content != b"SECRET"


def test_redirect_loop_capped(client, monkeypatch):
    # An endless redirect chain must terminate with a 404, not hang/recurse.
    _patch_fetch_chain(
        monkeypatch,
        [(302, "https://archive.org/a.jpg")] * 12,
    )
    r = client.get(
        "/api/images/proxy",
        params={"url": "https://coverartarchive.org/release/mbid-x/front"},
    )
    assert r.status_code == 404


def test_archive_org_subdomain_allowed_directly(client, monkeypatch):
    # The dynamic archive.org data-node host is suffix-allowlisted.
    _patch_fetch(monkeypatch, content=b"IMG", content_type="image/jpeg")
    r = client.get(
        "/api/images/proxy",
        params={"url": "https://dn710304.ca.archive.org/0/items/mbid-x/cover.jpg"},
    )
    assert r.status_code == 200
    assert r.content == b"IMG"


# --- cache failure must not break serving (cache is an optimization) ---


def test_serves_image_when_cache_store_fails(client, monkeypatch):
    # A broken/unwritable cache dir (image_cache.store raises) must NOT 500 the
    # request — the freshly fetched image is still served.
    _patch_fetch(monkeypatch, content=b"IMG", content_type="image/png")

    def _boom(*a, **k):
        raise OSError("cache dir unwritable")

    monkeypatch.setattr(images_router.image_cache, "store", _boom)
    r = client.get("/api/images/proxy", params={"url": "https://image.tmdb.org/x.png"})
    assert r.status_code == 200
    assert r.content == b"IMG"


def test_serves_image_when_cache_retrieve_fails(client, monkeypatch):
    # A read failure on the cache lookup must also fall through to a live fetch,
    # not 500.
    _patch_fetch(monkeypatch, content=b"IMG", content_type="image/png")

    def _boom(*a, **k):
        raise OSError("cache dir unreadable")

    monkeypatch.setattr(images_router.image_cache, "retrieve", _boom)
    r = client.get("/api/images/proxy", params={"url": "https://image.tmdb.org/y.png"})
    assert r.status_code == 200
    assert r.content == b"IMG"


# --- release -> release-group cover fallback (Picard model) ---

_RELEASE_URL = "https://coverartarchive.org/release/rel-1/front-250"


def test_release_404_falls_back_to_group(client, monkeypatch):
    # release/{mbid}/front-250 -> 404 ; release-group/{rg}/front-250 -> image.
    # The proxy must serve the group cover (the art-less-pressing rescue).
    requested = _patch_fetch_recording(
        monkeypatch,
        {"/release/rel-1/": "404", "/release-group/grp-1/": ("image", b"GROUPCOVER", "image/jpeg")},
    )
    r = client.get("/api/images/proxy", params={"url": f"{_RELEASE_URL}?fallback_group=grp-1"})
    assert r.status_code == 200
    assert r.content == b"GROUPCOVER"
    assert any("/release-group/grp-1/" in u for u in requested)


def test_release_200_does_not_use_fallback(client, monkeypatch):
    # Release art exists -> serve it, never fetch the group (distinct covers).
    requested = _patch_fetch_recording(
        monkeypatch,
        {"/release/rel-1/": ("image", b"RELEASECOVER", "image/jpeg"), "/release-group/grp-1/": "404"},
    )
    r = client.get("/api/images/proxy", params={"url": f"{_RELEASE_URL}?fallback_group=grp-1"})
    assert r.status_code == 200
    assert r.content == b"RELEASECOVER"
    assert not any("/release-group/" in u for u in requested)


def test_release_404_and_group_404_returns_404(client, monkeypatch):
    # Neither the release nor its group has art -> 404, negative-cached.
    _patch_fetch_recording(monkeypatch, {"/release/rel-1/": "404", "/release-group/grp-1/": "404"})
    r = client.get("/api/images/proxy", params={"url": f"{_RELEASE_URL}?fallback_group=grp-1"})
    assert r.status_code == 404
    # negative-cache key is the stripped primary URL (no fallback_group param)
    assert _RELEASE_URL in images_router._NEGATIVE_CACHE


def test_fallback_group_param_stripped_from_upstream_fetch(client, monkeypatch):
    # The upstream request URL must NOT carry fallback_group (clean request/cache key).
    requested = _patch_fetch_recording(monkeypatch, {"/release/rel-1/": ("image", b"IMG", "image/jpeg")})
    r = client.get("/api/images/proxy", params={"url": f"{_RELEASE_URL}?fallback_group=grp-1"})
    assert r.status_code == 200
    assert requested  # something was fetched
    assert all("fallback_group" not in u for u in requested)


def test_no_fallback_param_404_unchanged(client, monkeypatch):
    # A plain release URL with no fallback_group that 404s -> 404 (prior behavior),
    # and the group endpoint is never consulted.
    requested = _patch_fetch_recording(monkeypatch, {"/release/rel-1/": "404"})
    r = client.get("/api/images/proxy", params={"url": _RELEASE_URL})
    assert r.status_code == 404
    assert not any("/release-group/" in u for u in requested)
