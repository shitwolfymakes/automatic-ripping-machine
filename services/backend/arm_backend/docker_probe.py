"""Shared "can this docker host run image X right now?" probe, with a TTL cache.

Used by the transcode dispatcher and the ripper manager for
/api/system/diagnostics. Synchronous and never raises — callers run it via
asyncio.to_thread from request handlers.
"""

from __future__ import annotations

import os
import socket
import ssl
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

import docker.errors  # type: ignore[import-untyped]
import httpx

# How long a probe result is reused before re-pinging the docker host. An
# unreachable ssh host stalls each uncached call for docker-py's client
# timeout, and diagnostics polls this on every request.
PROBE_TTL_SECONDS = 30.0

# Where the shared entrypoint finds the ARM CA (it also merges it into the
# system bundle; loaded explicitly so the check holds without that merge).
ARM_CA_FILE = "/etc/ssl/arm/arm-ca.crt"
BACKEND_URL_TIMEOUT_SECONDS = 5.0


def probe_docker(
    client: Any,
    image: str,
    *,
    recover: Callable[[BaseException], Any | None] | None = None,
) -> tuple[bool, str | None]:
    """Ping the daemon, then check `image` exists there. (ok, detail).

    `recover` is handed the ping failure and may return a replacement client
    (a docker-over-SSH transport that died while idle fails the ping and
    nothing else would ever reopen it); the replacement is pinged once and
    answers the rest of the probe. Returning None keeps the failure as is.
    """
    try:
        client.ping()
    except Exception as exc:  # noqa: BLE001 — any transport failure is the same answer
        fresh = recover(exc) if recover is not None else None
        if fresh is None:
            return False, f"docker host unreachable: {exc}"
        client = fresh
        try:
            client.ping()
        except Exception as again:  # noqa: BLE001
            return False, f"docker host unreachable: {again}"
    try:
        client.images.get(image)
    except docker.errors.ImageNotFound:
        return False, f"image {image} not present on docker host"
    except Exception as exc:  # noqa: BLE001
        return False, f"image check failed: {exc}"
    return True, None


class TtlProbe:
    """Memoise a probe callable for `ttl` seconds — failures included, so a
    dead host is not re-pinged on every diagnostics request."""

    def __init__(self, fn: Callable[[], tuple[bool, str | None]], *, ttl: float = PROBE_TTL_SECONDS) -> None:
        self._fn = fn
        self._ttl = ttl
        self._cache: tuple[float, tuple[bool, str | None]] | None = None

    def __call__(self) -> tuple[bool, str | None]:
        now = time.monotonic()
        if self._cache is not None:
            ts, result = self._cache
            if now - ts < self._ttl:
                return result
        result = self._fn()
        self._cache = (now, result)
        return result

    def invalidate(self) -> None:
        """Forget the cached answer; the next call probes again."""
        self._cache = None


def _tls_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    if os.path.isfile(ARM_CA_FILE):
        ctx.load_verify_locations(ARM_CA_FILE)
    return ctx


def probe_backend_url(url: str) -> tuple[bool, str | None]:
    """Can a client that trusts the ARM CA reach `url` over TLS? (ok, detail).

    This is the URL a remote-spawned transcoder dials home on, checked the
    same way it verifies it (system bundle + ARM CA, so the backend leaf's
    SANs must cover the URL host). It runs from the backend host, so it
    cannot see DNS that resolves differently on the remote host; the detail
    names the address it resolved to, for comparison.
    """
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        return False, f"backend URL {url} is not a valid URL: {exc}"
    try:
        address = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)[0][4][0]
    except OSError as exc:
        return False, f"backend URL {url} does not resolve from the backend host: {exc}"
    try:
        ctx = _tls_context()
    except (OSError, ssl.SSLError) as exc:
        return False, f"ARM CA {ARM_CA_FILE} could not be loaded: {exc}"
    try:
        with httpx.Client(verify=ctx, timeout=BACKEND_URL_TIMEOUT_SECONDS) as client:
            client.get(url.rstrip("/") + "/api/health")
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        return False, f"backend URL {url} ({address}) not reachable from the backend host: {exc}"
    return True, None
