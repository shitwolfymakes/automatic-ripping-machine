"""Shared "can this docker host run image X right now?" probe, with a TTL cache.

Used by the transcode dispatcher and the ripper manager for
/api/system/diagnostics. Synchronous and never raises — callers run it via
asyncio.to_thread from request handlers.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
import socket
import ssl
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

import docker.errors  # type: ignore[import-untyped]
import httpx

from arm_backend.url_masking import strip_userinfo

if TYPE_CHECKING:
    from arm_backend.config import Settings

# How long a probe result is reused before re-pinging the docker host. An
# unreachable ssh host stalls each uncached call for docker-py's client
# timeout, and diagnostics polls this on every request.
PROBE_TTL_SECONDS = 30.0

# Where the shared entrypoint finds the ARM CA (it also merges it into the
# system bundle; loaded explicitly so the check holds without that merge).
ARM_CA_FILE = "/etc/ssl/arm/arm-ca.crt"
BACKEND_URL_TIMEOUT_SECONDS = 5.0


def probe_docker(client: Any, image: str) -> tuple[bool, str | None]:
    """Ping the daemon, then check `image` exists there. (ok, detail).

    A transcode-host `client` is a `HealingDockerClient`, so a docker-over-SSH
    transport that died while idle is reopened by whichever of the two calls
    meets it, and that call is retried once before it counts as a failure.
    """
    try:
        client.ping()
    except Exception as exc:  # noqa: BLE001 — any transport failure is the same answer
        return False, f"docker host unreachable: {exc}"
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
    shown = strip_userinfo(url)
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        # Not `{exc}`: urlsplit's port error quotes the text after the
        # first `:` of the host part, which can be part of a password.
        return False, f"backend URL {shown} is not a valid URL"
    try:
        address = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)[0][4][0]
    except OSError as exc:
        return False, f"backend URL {shown} does not resolve from the backend host: {exc}"
    try:
        ctx = _tls_context()
    except (OSError, ssl.SSLError) as exc:
        return False, f"ARM CA {ARM_CA_FILE} could not be loaded: {exc}"
    try:
        with httpx.Client(verify=ctx, timeout=BACKEND_URL_TIMEOUT_SECONDS) as client:
            client.get(url.rstrip("/") + "/api/health")
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        return False, f"backend URL {shown} ({address}) not reachable from the backend host: {exc}"
    return True, None


_PEM_BLOCK = re.compile(r"-----BEGIN CERTIFICATE-----(.+?)-----END CERTIFICATE-----", re.DOTALL)


def _ca_fingerprints(pem: str) -> set[str]:
    """SHA-256 of every certificate in a PEM bundle, as hex."""
    return {hashlib.sha256(base64.b64decode("".join(block.split()))).hexdigest() for block in _PEM_BLOCK.findall(pem)}


def _short(fingerprints: set[str]) -> str:
    return ",".join(sorted(f[:12] for f in fingerprints)) or "no certificate"


def certs_dir_difference(settings: Settings) -> str | None:
    """With local transcoding, rippers and transcoders mount the same local
    certs dir, so `ARM_RIPPER_CERTS_PATH` (when set) must equal
    `ARM_HOST_CERTS_PATH`. Returns the problem, or None."""
    ripper, host = settings.ARM_RIPPER_CERTS_PATH, settings.ARM_HOST_CERTS_PATH
    if settings.ARM_TRANSCODE_DOCKER_HOST or not ripper or not host:
        return None
    if os.path.normpath(ripper) == os.path.normpath(host):
        return None
    return (
        f"ARM_RIPPER_CERTS_PATH ({ripper}) differs from ARM_HOST_CERTS_PATH ({host}) on a local-transcode "
        "install; both must name this install's certs dir"
    )


def probe_transcode_ca(client: Any, settings: Settings, *, ca_file: str = ARM_CA_FILE) -> tuple[bool, str | None]:
    """With local transcoding, is the CA that transcoders will mount
    (`ARM_HOST_CERTS_PATH/arm-ca.crt`) the CA this backend itself trusts and
    serves under? (ok, detail).

    The backend sees only its own `/etc/ssl/arm`, not host paths, so a
    throwaway container of the transcode image mounts exactly what the
    transcode spec mounts and prints it; the certificate fingerprints are
    compared with the backend's own CA file. Not checkable (remote
    transcoding, no CA file here, missing image) answers ok; the image and
    host probes report those. Never raises.
    """
    host_ca = str(Path(settings.ARM_HOST_CERTS_PATH) / "arm-ca.crt")
    if settings.ARM_TRANSCODE_DOCKER_HOST or not settings.ARM_HOST_CERTS_PATH or not os.path.isfile(ca_file):
        return True, None
    try:
        mine = _ca_fingerprints(Path(ca_file).read_text())
        mount = docker.types.Mount("/ca/arm-ca.crt", host_ca, type="bind", read_only=True)
        out = client.containers.run(
            settings.ARM_TRANSCODE_IMAGE,
            command=["/ca/arm-ca.crt"],
            entrypoint=["cat"],
            mounts=[mount],
            remove=True,
            network_mode="none",
        )
    except docker.errors.ImageNotFound:
        return True, None
    except (docker.errors.DockerException, OSError, ValueError) as exc:
        return False, f"transcoders would mount {host_ca} (ARM_HOST_CERTS_PATH) but it could not be read: {exc}"
    theirs = _ca_fingerprints(out.decode("utf-8", "replace") if isinstance(out, bytes) else str(out))
    if mine and theirs & mine:
        return True, None
    return False, (
        f"transcoders would mount {host_ca} (ARM_HOST_CERTS_PATH), a CA ({_short(theirs)}) other than the one "
        f"this backend runs with ({_short(mine)}); they would fail TLS verification. "
        "Point ARM_HOST_CERTS_PATH at this install's certs dir"
    )
