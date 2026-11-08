"""The transcode images the docker host has: a cached presence check and an on-demand pull."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from arm_backend.config import Settings
from arm_backend.docker_client import HealingDockerClient
from arm_backend.docker_probe import TtlProbe, probe_docker
from arm_backend.transcode_images import VARIANT_SUFFIX, split_reference, variant_image, vendor_override
from arm_common import GpuVendor

logger = logging.getLogger(__name__)

# How long a failed pull of a per-vendor variant image is remembered before
# the pull is tried again. A variant tag that exists only on a dev host (or a
# registry that is down) would otherwise cost a registry round trip on every
# spawn and GPU probe.
VARIANT_PULL_RETRY_SECONDS = 600.0


class TranscodeImagePool:
    """Which transcode images the docker host has, and pulling a missing one."""

    def __init__(self, settings: Settings, docker_client: HealingDockerClient | None) -> None:
        self._settings = settings
        self._docker_client = docker_client
        # Per-image TtlProbe cache for `image_exists` (one entry per distinct
        # variant image ever checked, e.g. the derived "-intel"/"-amd" tag).
        self._image_probes: dict[str, TtlProbe] = {}
        # Image -> time.monotonic() of its last failed pull (see
        # `pull_image`); separate from the 30 s presence cache above.
        self._variant_pull_failed: dict[str, float] = {}
        # One lock per variant image being pulled, so concurrent callers (a
        # spawn and a GPU probe in two worker threads) share a single pull:
        # the second waits for the first and reuses its outcome.
        self._pull_locks: dict[str, threading.Lock] = {}
        self._pull_locks_guard = threading.Lock()

    @property
    def _docker(self) -> Any:
        """The docker-py client the shared wrapper currently forwards to."""
        return self._docker_client.current if self._docker_client is not None else None

    def invalidate(self) -> None:
        """Forget every cached image answer: they were made against the client
        a rebuild just replaced. Copied first, since a probe in another thread
        may be adding an image's entry."""
        for probe in list(self._image_probes.values()):
            probe.invalidate()

    def image_exists(self, image: str) -> bool:
        """Cached `probe_docker` check for a specific image reference (the
        base image or a derived per-vendor variant). False when there's no
        docker client at all (ripper-only deployment)."""
        if self._docker is None:
            return False
        cached = self._image_probes.get(image)
        if cached is None:
            # `image` is this call's own local (not a loop variable), so a
            # plain closure captures the right value with no late-binding
            # hazard; each distinct image gets its own TtlProbe + closure.
            cached = TtlProbe(lambda: probe_docker(self._docker_client, image))
            self._image_probes[image] = cached
        ok, _ = cached()
        return ok

    def pull_failed_recently(self, image: str) -> float | None:
        """Seconds until a failed pull of `image` may be retried, or None when
        there is no failure inside the VARIANT_PULL_RETRY_SECONDS window."""
        failed_at = self._variant_pull_failed.get(image)
        if failed_at is None:
            return None
        remaining = VARIANT_PULL_RETRY_SECONDS - (time.monotonic() - failed_at)
        return remaining if remaining > 0 else None

    def _pull_lock(self, image: str) -> threading.Lock:
        with self._pull_locks_guard:
            return self._pull_locks.setdefault(image, threading.Lock())

    def variant_available(self, image: str) -> bool:
        """Can the per-vendor variant `image` be spawned on the docker host?

        True when it is already present (the cached `image_exists` check) or
        a pull of it succeeds now. A failed pull returns False and is not
        retried for VARIANT_PULL_RETRY_SECONDS, so the caller falls back to
        the base image without a registry round trip each time. A digest
        reference has no tag to pull and is never pulled. Concurrent callers
        for the same image share one pull. Only derived variants come
        through here; the base image is never pulled by this path. Used by
        the spawn and GPU-probe paths only, never by diagnostics. Blocking
        (a pull can take minutes): callers run it off the event loop."""
        if self._docker is None:
            return False
        if self.image_exists(image):
            return True
        return self.pull_image(image, kind="variant", fallback="using the base image")

    def pull_image(self, image: str, *, kind: str, fallback: str) -> bool:
        """Pull `image` onto the docker host; True when it is there afterwards.
        A failed pull is not retried for VARIANT_PULL_RETRY_SECONDS, and
        concurrent callers for one image share a pull. A digest reference has
        no tag to pull and is never pulled. Blocking."""
        assert self._docker_client is not None
        parts = split_reference(image)
        if parts is None:
            return False
        with self._pull_lock(image):
            # Re-check under the lock: a concurrent caller may have just
            # finished a pull of this image, successful or not.
            if self.pull_failed_recently(image) is not None:
                return False
            if self.image_exists(image):
                return True
            repo, tag = parts
            logger.info("%s image %s not present on the docker host; pulling it", kind, image)
            try:
                self._docker_client.images.pull(repo, tag=tag)
            except Exception as exc:  # noqa: BLE001 - any pull failure is reported, then retried later
                logger.warning(
                    "could not pull %s image %s (%s); %s, next pull attempt in %.0f s",
                    kind,
                    image,
                    exc,
                    fallback,
                    VARIANT_PULL_RETRY_SECONDS,
                )
                self._variant_pull_failed[image] = time.monotonic()
                return False
            self._variant_pull_failed.pop(image, None)
            # Drop the cached "absent" answer so the next presence check sees it.
            self._image_probes.pop(image, None)
            logger.info("pulled %s image %s", kind, image)
            return True

    def missing_variant_notes(self, enabled_vendors: set[GpuVendor]) -> list[str]:
        """One note per vendor that has an enabled GPU row, has a derivable
        variant, isn't overridden, and whose variant image isn't present on
        this docker host. Presence-only: diagnostics never pulls, so a poll
        costs no registry traffic and never records a pull failure that would
        deny the next spawn its pull. The wording says whether the variant
        will be pulled on first use or recently failed to pull."""
        notes: list[str] = []
        for vendor in sorted(enabled_vendors, key=lambda v: v.value):
            if vendor_override(self._settings, vendor):
                continue
            suffix = VARIANT_SUFFIX.get(vendor)
            if suffix is None:
                continue
            candidate = variant_image(self._settings.ARM_TRANSCODE_IMAGE, suffix)
            if candidate is None or self.image_exists(candidate):
                continue
            retry_in = self.pull_failed_recently(candidate)
            if retry_in is None:
                notes.append(
                    f"{vendor.value} variant image {candidate} not present locally; it will be pulled on first use"
                )
            else:
                notes.append(
                    f"{vendor.value} variant image {candidate} could not be pulled; "
                    f"falling back to the base image (retry after {retry_in:.0f} s)"
                )
        return notes
