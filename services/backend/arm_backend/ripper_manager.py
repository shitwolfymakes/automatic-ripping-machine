"""Ripper manager: one durable container per *enrolled* drive.

Mirrors transcode_dispatcher's docker-py usage (label-based tracking,
boot-time reconcile) with two differences in kind: rippers are durable
(`restart_policy: unless-stopped`, never `auto_remove`) so docker keeps them
up and the backend only decides whether they should exist; and they always
run on the *local* daemon — the drive is plugged into this host, so
ARM_TRANSCODE_DOCKER_HOST never applies.

Every method is synchronous (callers use asyncio.to_thread) and raises only
RipperManagerError for docker/transport failures.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

import docker.errors  # type: ignore[import-untyped]

from arm_backend.config import Settings
from arm_backend.docker_probe import TtlProbe, probe_docker
from arm_backend.ripper_container_spec import (
    DOCKER_LABEL_KEY,
    SPEC_HASH_LABEL_KEY,
    certs_path,
    container_name,
    container_spec,
)
from arm_common import Drive

logger = logging.getLogger("arm_backend.ripper_manager")

# Seconds docker waits for the ripper to exit on SIGTERM before SIGKILL.
# A rip in flight is refused at the router (unenroll while RIPPING), so
# this only ever interrupts idle polling.
_STOP_TIMEOUT_SECONDS = 30


class RipperManagerError(RuntimeError):
    """A docker/transport failure, already reduced to an operator-readable line."""


@dataclass
class ReconcileSummary:
    created: list[str] = field(default_factory=list)
    adopted: list[str] = field(default_factory=list)
    restarted: list[str] = field(default_factory=list)
    recreated: list[str] = field(default_factory=list)
    orphans_removed: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)


def _err(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}"[:300]


def _by_drive(containers: Iterable[Any]) -> dict[str, Any]:
    """Index the labelled containers by drive id; the first one listed for
    an id wins."""
    by_drive: dict[str, Any] = {}
    for c in containers:
        by_drive.setdefault(c.labels.get(DOCKER_LABEL_KEY), c)
    return by_drive


def _log_summary(summary: ReconcileSummary) -> None:
    """Log one line counting each reconcile outcome."""
    logger.info(
        "ripper reconcile: created=%d adopted=%d restarted=%d recreated=%d orphans_removed=%d failed=%d",
        len(summary.created),
        len(summary.adopted),
        len(summary.restarted),
        len(summary.recreated),
        len(summary.orphans_removed),
        len(summary.failed),
    )


class RipperManager:
    def __init__(self, settings: Settings, docker_client: Any) -> None:
        self._settings = settings
        self._docker = docker_client
        self._probe = TtlProbe(lambda: probe_docker(self._docker, self._settings.ARM_RIPPER_IMAGE))

    # --- diagnostics ---------------------------------------------------------

    def host_paths_set(self) -> bool:
        s = self._settings
        return bool(s.ARM_HOST_RAW_PATH and s.ARM_HOST_LOGS_PATH and certs_path(s))

    def probe(self) -> tuple[bool, str | None]:
        """Daemon reachable and ARM_RIPPER_IMAGE present? Never raises; TTL-cached."""
        return self._probe()

    # --- operations ------------------------------------------------------------

    def _labelled(self, drive_id: str | None = None) -> list[Any]:
        label = DOCKER_LABEL_KEY if drive_id is None else f"{DOCKER_LABEL_KEY}={drive_id}"
        return list(self._docker.containers.list(all=True, filters={"label": label}))

    def _start_or_create(self, drive: Drive, existing: Any | None) -> str:
        """Returns "created" | "adopted" | "restarted"."""
        if existing is None:
            try:
                self._docker.containers.run(**container_spec(self._settings, drive))
            except docker.errors.APIError as exc:
                # A concurrent creator can win the name race between our
                # `_labelled` lookup and `containers.run` (two callers
                # reconciling/enrolling the same drive at once) — docker
                # answers 409 "Conflict" for the name collision. Re-list and
                # adopt whatever is there now instead of failing outright;
                # if nothing shows up it wasn't a name conflict after all and
                # the original error stands.
                if exc.status_code == 409:
                    winner = next(iter(self._labelled(drive.id)), None)
                    if winner is not None:
                        return self._start_or_create(drive, winner)
                raise
            return "created"
        if existing.status != "running":
            # "running" / "exited" / "paused" / … are docker's own
            # `ContainerState.Status` values from the daemon, not ours. A
            # `paused` container's `.start()` answers 409 (only `unpause`
            # resumes a paused container) — that is not swallowed here: it
            # propagates as a docker-py APIError and is recorded as a
            # per-drive failure by the caller (`ensure_running` wraps it as
            # RipperManagerError; `reconcile` puts it in `summary.failed`).
            existing.start()
            return "restarted"
        return "adopted"

    def ensure_running(self, drive: Drive) -> str:
        """Enroll effect. Idempotent: a container carrying the label is
        adopted (started if exited), never duplicated. Returns the name."""
        try:
            existing = next(iter(self._labelled(drive.id)), None)
            outcome = self._start_or_create(drive, existing)
        except Exception as exc:  # noqa: BLE001 — docker-py + transport errors, all one answer
            raise RipperManagerError(_err(exc)) from exc
        name = existing.name if existing is not None else container_name(drive)
        logger.info(
            "ripper %s drive_id=%s container=%s image=%s", outcome, drive.id, name, self._settings.ARM_RIPPER_IMAGE
        )
        return name

    def _stop_and_remove(self, container: Any) -> None:
        container.stop(timeout=_STOP_TIMEOUT_SECONDS)
        container.remove()

    def remove(self, drive_id: str) -> int:
        """Unenroll effect: stop + remove every container labelled with the drive."""
        try:
            containers = self._labelled(drive_id)
            for c in containers:
                self._stop_and_remove(c)
        except Exception as exc:  # noqa: BLE001
            raise RipperManagerError(_err(exc)) from exc
        if containers:
            logger.info("ripper removed drive_id=%s containers=%d", drive_id, len(containers))
        return len(containers)

    def _image_current(self, container: Any) -> bool:
        """Does the container run the image ARM_RIPPER_IMAGE resolves to now?
        Unknowable (missing image, transport error) counts as current — a
        reconcile must never tear a working ripper down on a guess."""
        try:
            return bool(container.image.id == self._docker.images.get(self._settings.ARM_RIPPER_IMAGE).id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cannot compare image for container %s: %s", getattr(container, "name", "?"), _err(exc))
            return True

    def _drift(self, drive: Drive, container: Any) -> str | None:
        """Why the container no longer matches what `container_spec` would
        create now, or None. A container from before the spec-hash label
        existed has no label and counts as drifted: reconcile recreates it
        once, when idle."""
        if not self._image_current(container):
            return "a stale image"
        wanted = container_spec(self._settings, drive)["labels"][SPEC_HASH_LABEL_KEY]
        if (container.labels or {}).get(SPEC_HASH_LABEL_KEY) != wanted:
            return "a spec that differs from the current settings"
        return None

    def container_statuses(self, drive_ids: Iterable[str]) -> dict[str, tuple[str, bool | None]]:
        """(docker state, image current?) per drive id for /api/drives/diagnostic, from ONE
        container listing. Every id maps to ("unknown", None) when docker is unreachable
        (probe() says so, or the listing fails), ("missing", None) when no container carries
        its label. Never raises."""
        ids = list(drive_ids)
        ok, _detail = self.probe()
        if not ok:
            return dict.fromkeys(ids, ("unknown", None))
        try:
            containers = self._labelled()
        except Exception as exc:  # noqa: BLE001
            logger.warning("cannot list containers: %s", _err(exc))
            return dict.fromkeys(ids, ("unknown", None))
        by_drive = _by_drive(containers)
        result: dict[str, tuple[str, bool | None]] = {}
        for drive_id in ids:
            existing = by_drive.get(drive_id)
            if existing is None:
                result[drive_id] = ("missing", None)
            else:
                result[drive_id] = (str(existing.status), self._image_current(existing))
        return result

    def reconcile(self, enrolled: Sequence[Drive], *, busy: frozenset[str] = frozenset()) -> ReconcileSummary:
        """Boot-time: the Drive table is the source of truth.
        Per-drive failures are recorded, not raised; only an un-listable
        daemon raises. A ripper whose container image no longer matches
        ARM_RIPPER_IMAGE, or whose spec no longer matches the current
        settings (a changed ARM_RIPPER_* tunable, PUID, ARM_LOG_LEVEL, ...),
        is recreated so `docker compose build` or an edited `.env`
        actually takes effect — unless the drive is mid-rip (`busy`), in
        which case it's adopted as-is and picked up on the next reconcile
        after the job finishes. `busy` is RIPPING-only on purpose: a scan
        has no job row yet (unknowable) and IDENTIFIED/AWAITING_REVIEW
        would block upgrades indefinitely behind a review gate; a container
        replaced mid-scan re-detects the seated disc on its first poll."""
        try:
            containers = self._labelled()
        except Exception as exc:  # noqa: BLE001
            raise RipperManagerError(_err(exc)) from exc
        by_drive = _by_drive(containers)
        wanted = {d.id for d in enrolled}
        summary = ReconcileSummary()
        self._remove_orphans(by_drive, wanted, summary)
        for drive in enrolled:
            self._reconcile_drive(drive, by_drive.get(drive.id), busy, summary)
        _log_summary(summary)
        return summary

    def _remove_orphans(self, by_drive: dict[str, Any], wanted: set[str], summary: ReconcileSummary) -> None:
        """Stop and remove every labelled container whose drive is no longer
        enrolled, recording each outcome."""
        for drive_id, c in by_drive.items():
            if drive_id in wanted:
                continue
            try:
                self._stop_and_remove(c)
                summary.orphans_removed.append(drive_id)
            except Exception as exc:  # noqa: BLE001
                summary.failed[drive_id] = _err(exc)

    def _reconcile_drive(
        self, drive: Drive, existing: Any | None, busy: frozenset[str], summary: ReconcileSummary
    ) -> None:
        """Bring one enrolled drive's container in line with its spec,
        recording the outcome; never raises."""
        try:
            drift = self._drift(drive, existing) if existing is not None else None
        except Exception as exc:  # noqa: BLE001
            # container_spec can raise for one bad drive; that must not
            # abort the reconcile for every other drive.
            summary.failed[drive.id] = _err(exc)
            return
        if drift is not None:
            if drive.id in busy:
                logger.info(
                    "ripper drive_id=%s runs %s but is ripping — adopting; recreated at the "
                    "next backend restart once the drive is idle",
                    drive.id,
                    drift,
                )
            else:
                self._recreate(drive, existing, drift, summary)
                return
        try:
            outcome = self._start_or_create(drive, existing)
        except Exception as exc:  # noqa: BLE001
            summary.failed[drive.id] = _err(exc)
            return
        getattr(summary, outcome).append(drive.id)

    def _recreate(self, drive: Drive, existing: Any, drift: str, summary: ReconcileSummary) -> None:
        """Replace a drifted, idle container with one built from the current
        spec."""
        try:
            self._stop_and_remove(existing)
            self._docker.containers.run(**container_spec(self._settings, drive))
        except Exception as exc:  # noqa: BLE001
            summary.failed[drive.id] = _err(exc)
            return
        logger.info("ripper recreated drive_id=%s: it ran %s", drive.id, drift)
        summary.recreated.append(drive.id)
