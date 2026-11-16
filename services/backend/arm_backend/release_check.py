"""Latest stable ARM release, polled from GitHub in the background.

The version endpoint reads the in-memory cache and never waits on GitHub: a
loop started in the app lifespan refreshes it at start-up and every six
hours. A failed check leaves the last good answer in place and logs one
warning per failure streak.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

DEFAULT_REPO = "automatic-ripping-machine/automatic-ripping-machine"
REFRESH_INTERVAL_SECONDS = 6 * 3600
_USER_AGENT = "arm-release-check"
_CORE_RE = re.compile(r"^\d+(\.\d+)*$")
_CHUNK_RE = re.compile(r"\d+|\D+")

type VersionKey = tuple[tuple[int, int, str], ...]


class ReleaseCheckError(Exception):
    """GitHub could not be reached or did not answer with a usable release."""


@dataclass(frozen=True)
class Release:
    tag: str
    url: str


class ReleaseCache:
    """The last successfully fetched stable release (None until one is known)."""

    def __init__(self) -> None:
        self.release: Release | None = None


cache = ReleaseCache()


def release_repo() -> str:
    """The GitHub repo to check: ARMCTL_RELEASE_REPO when set, else upstream."""
    return os.environ.get("ARMCTL_RELEASE_REPO", "").strip() or DEFAULT_REPO


def parse_version(version: str) -> tuple[tuple[int, ...], str] | None:
    """Split a release tag into (numeric core, pre-release). A leading v is
    ignored. Returns None when the core is not dotted numbers (for example
    0.0.0+unknown)."""
    text = version.removeprefix("v")
    core, _, pre = text.partition("-")
    if not _CORE_RE.match(core):
        return None
    return tuple(int(part) for part in core.split(".")), pre


def _natural_key(text: str) -> VersionKey:
    """Order digit runs numerically and other runs as text, like sort -V."""
    return tuple((0, int(chunk), "") if chunk.isdigit() else (1, 0, chunk) for chunk in _CHUNK_RE.findall(text))


def version_older(a: str, b: str) -> bool:
    """True when release tag a is older than b. Mirrors deploy/armctl.sh
    version_older: a leading v is ignored, cores compare numerically, and a
    pre-release of a core is older than the core itself."""
    a_text, b_text = a.removeprefix("v"), b.removeprefix("v")
    a_core, _, a_pre = a_text.partition("-")
    b_core, _, b_pre = b_text.partition("-")
    if a_core != b_core:
        return _natural_key(a_core) < _natural_key(b_core)
    if not a_pre:
        return False
    if not b_pre:
        return True
    return _natural_key(a_pre) < _natural_key(b_pre)


def update_available(running: str, release: Release) -> bool:
    """True only when the running version parses and the stable release is
    strictly newer."""
    if parse_version(running) is None or parse_version(release.tag) is None:
        return False
    return version_older(running, release.tag)


def _release_from_payload(payload: object) -> Release | None:
    if not isinstance(payload, dict):
        raise ReleaseCheckError("release payload is not an object")
    if payload.get("prerelease") or payload.get("draft"):
        return None
    tag, url = payload.get("tag_name"), payload.get("html_url")
    if not isinstance(tag, str) or not isinstance(url, str) or not tag or not url:
        raise ReleaseCheckError("release payload lacks tag_name or html_url")
    return Release(tag=tag, url=url)


async def latest_stable_release(client: httpx.AsyncClient, repo: str) -> Release | None:
    """The repo's latest stable release; None when GitHub reports a prerelease
    or draft. Raises ReleaseCheckError when no usable answer comes back."""
    try:
        response = await client.get(
            f"https://api.github.com/repos/{repo}/releases/latest",
            headers={"Accept": "application/vnd.github+json", "User-Agent": _USER_AGENT},
        )
    except httpx.HTTPError as e:
        raise ReleaseCheckError(f"{type(e).__name__}: {e}") from e
    if response.status_code == 404:
        raise ReleaseCheckError("HTTP 404, the repository has no published releases")
    if response.status_code != 200:
        raise ReleaseCheckError(f"HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as e:
        raise ReleaseCheckError("response is not JSON") from e
    return _release_from_payload(payload)


async def _check_once(client: httpx.AsyncClient, repo: str, failing: bool) -> bool:
    """Refresh the cache once; return whether this check failed. Warns only
    when a failure streak starts."""
    try:
        cache.release = await latest_stable_release(client, repo)
    except Exception as e:  # noqa: BLE001 — a failed check must never end the loop (cancellation is a BaseException)
        if not failing:
            logger.warning("release check against %s failed: %s", repo, e)
        return True
    return False


async def release_check_loop(
    client: httpx.AsyncClient,
    repo: str,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> None:
    """Check at start-up, then every REFRESH_INTERVAL_SECONDS, until cancelled."""
    failing = False
    while True:
        failing = await _check_once(client, repo, failing)
        await sleep(REFRESH_INTERVAL_SECONDS)
