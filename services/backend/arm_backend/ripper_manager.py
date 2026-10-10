"""Ripper manager: one durable container per *enrolled* drive (spec §3).

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

import asyncio
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import docker.errors  # type: ignore[import-untyped]
from sqlmodel import col, select

from arm_backend.config import Settings
from arm_backend.docker_probe import TtlProbe, probe_docker
from arm_common import Drive, DriveLifecycle, DriveStatus, Job, JobStatus

logger = logging.getLogger("arm_backend.ripper_manager")

DOCKER_LABEL_KEY = "arm.drive_id"
# Seconds docker waits for the ripper to exit on SIGTERM before SIGKILL.
# A rip in flight is refused at the router (unenroll while RIPPING), so
# this only ever interrupts idle polling.
_STOP_TIMEOUT_SECONDS = 30
_DEVICE_CGROUP_RULES = ["b 11:* rmw", "c 21:* rmw"]  # sr* block + sg* char majors (spec §3)
_HOST_DISK_MOUNT = "/host-disk"

# backend Settings name -> env name the ripper/entrypoint reads
_TUNABLE_ENV: dict[str, str] = {
    "ARM_RIPPER_POLL_INTERVAL_SECONDS": "POLL_INTERVAL_SECONDS",
    "ARM_RIPPER_MIN_LENGTH_SECONDS": "ARM_MIN_LENGTH_SECONDS",
    "ARM_RIPPER_MAKEMKV_KEYCHECK_INTERVAL_SECONDS": "MAKEMKV_KEYCHECK_INTERVAL_SECONDS",
    "ARM_RIPPER_NOT_READY_REARM_POLLS": "ARM_NOT_READY_REARM_POLLS",
    "ARM_RIPPER_OPTICAL_SR_MAX": "ARM_OPTICAL_SR_MAX",
    "ARM_RIPPER_OPTICAL_SG_MAX": "ARM_OPTICAL_SG_MAX",
}


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


class RipperManager:
    def __init__(self, settings: Settings, docker_client: Any) -> None:
        self._settings = settings
        self._docker = docker_client
        self._probe = TtlProbe(lambda: probe_docker(self._docker, self._settings.ARM_RIPPER_IMAGE))

    # --- diagnostics ---------------------------------------------------------

    def host_paths_set(self) -> bool:
        s = self._settings
        return bool(s.ARM_HOST_RAW_PATH and s.ARM_HOST_LOGS_PATH and self._certs_path())

    def _certs_path(self) -> str:
        """Local host certs dir for the rippers' CA mount — ARM_RIPPER_CERTS_PATH
        when set (remote-transcode installs), else ARM_HOST_CERTS_PATH."""
        return self._settings.ARM_RIPPER_CERTS_PATH or self._settings.ARM_HOST_CERTS_PATH

    def probe(self) -> tuple[bool, str | None]:
        """Daemon reachable and ARM_RIPPER_IMAGE present? Never raises; TTL-cached."""
        return self._probe()

    # --- spec ------------------------------------------------------------------

    def container_name(self, drive: Drive) -> str:
        """`arm-ripper-<serial slug>` — a stable slot label; srN is not in the
        name because the node moves. Falls back to the drive-id suffix when
        the drive has no serial. Lower-cased `[a-z0-9-]` so it is valid both
        as a docker name and as a hostname."""
        raw = drive.serial or drive.id[-12:]
        slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-") or drive.id[-12:].lower()
        return f"arm-ripper-{slug}"

    def container_spec(self, drive: Drive) -> dict[str, Any]:
        """kwargs for `containers.run` — what the ripper needs and nothing more
        (spec §3): no `devices:` bind (the entrypoint pre-creates nodes), no
        per-ripper cert, `/dev/disk` not `/dev`."""
        s = self._settings
        name = self.container_name(drive)
        env: dict[str, str] = {
            "ARM_DRIVE_ID": drive.id,
            "ARM_DRIVE_DEV": drive.device_path,
            "ARM_HOST_DISK_ROOT": _HOST_DISK_MOUNT,
            "ARM_BACKEND_URL": "https://arm-backend:8443",
            "ARM_SERVICE_TOKEN": s.ARM_SERVICE_TOKEN,
            "ARM_LOG_LEVEL": s.ARM_LOG_LEVEL,
        }
        if drive.by_id_name:
            env["ARM_DRIVE_BY_ID"] = drive.by_id_name
        for key in ("PUID", "PGID", "CDROM_GID"):
            value = getattr(s, key)
            if value:
                env[key] = value
        for setting, env_name in _TUNABLE_ENV.items():
            value = getattr(s, setting)
            if value:
                env[env_name] = value
        certs_root = Path(self._certs_path())
        volumes = {
            s.ARM_HOST_RAW_PATH: {"bind": "/raw", "mode": "rw"},
            s.ARM_HOST_LOGS_PATH: {"bind": "/logs", "mode": "rw"},
            str(certs_root / "arm-ca.crt"): {"bind": "/etc/ssl/arm/arm-ca.crt", "mode": "ro"},
            "/dev/disk": {"bind": _HOST_DISK_MOUNT, "mode": "ro"},
        }
        return {
            "image": s.ARM_RIPPER_IMAGE,
            "name": name,
            "hostname": name,
            "labels": {DOCKER_LABEL_KEY: drive.id},
            "environment": env,
            "volumes": volumes,
            "network": s.ARM_DOCKER_NETWORK,
            "device_cgroup_rules": list(_DEVICE_CGROUP_RULES),
            "restart_policy": {"Name": "unless-stopped"},
            "detach": True,
        }

    # --- operations ------------------------------------------------------------

    def _labelled(self, drive_id: str | None = None) -> list[Any]:
        label = DOCKER_LABEL_KEY if drive_id is None else f"{DOCKER_LABEL_KEY}={drive_id}"
        return list(self._docker.containers.list(all=True, filters={"label": label}))

    def _start_or_create(self, drive: Drive, existing: Any | None) -> str:
        """Returns "created" | "adopted" | "restarted"."""
        if existing is None:
            try:
                self._docker.containers.run(**self.container_spec(drive))
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
        name = existing.name if existing is not None else self.container_name(drive)
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

    def reconcile(self, enrolled: Sequence[Drive], *, busy: frozenset[str] = frozenset()) -> ReconcileSummary:
        """Boot-time: the Drive table is the source of truth (spec §3).
        Per-drive failures are recorded, not raised; only an un-listable
        daemon raises. A running ripper whose container image no longer
        matches ARM_RIPPER_IMAGE is recreated so `docker compose build`
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
        by_drive: dict[str, Any] = {}
        for c in containers:
            by_drive.setdefault(c.labels.get(DOCKER_LABEL_KEY), c)
        wanted = {d.id for d in enrolled}
        summary = ReconcileSummary()
        for drive_id, c in by_drive.items():
            if drive_id in wanted:
                continue
            try:
                self._stop_and_remove(c)
                summary.orphans_removed.append(drive_id)
            except Exception as exc:  # noqa: BLE001
                summary.failed[drive_id] = _err(exc)
        for drive in enrolled:
            existing = by_drive.get(drive.id)
            if existing is not None and not self._image_current(existing):
                if drive.id in busy:
                    logger.info(
                        "ripper drive_id=%s runs a stale image but is ripping — adopting; recreated at the "
                        "next backend restart once the drive is idle",
                        drive.id,
                    )
                else:
                    try:
                        self._stop_and_remove(existing)
                        self._docker.containers.run(**self.container_spec(drive))
                    except Exception as exc:  # noqa: BLE001
                        summary.failed[drive.id] = _err(exc)
                        continue
                    summary.recreated.append(drive.id)
                    continue
            try:
                outcome = self._start_or_create(drive, existing)
            except Exception as exc:  # noqa: BLE001
                summary.failed[drive.id] = _err(exc)
                continue
            getattr(summary, outcome).append(drive.id)
        logger.info(
            "ripper reconcile: created=%d adopted=%d restarted=%d recreated=%d orphans_removed=%d failed=%d",
            len(summary.created),
            len(summary.adopted),
            len(summary.restarted),
            len(summary.recreated),
            len(summary.orphans_removed),
            len(summary.failed),
        )
        return summary


async def reconcile_enrolled_rippers(manager: RipperManager, session_factory: Any) -> ReconcileSummary | None:
    """Lifespan hook: reconcile containers against the `enrolled` rows and
    persist per-drive outcomes in `last_error` (cleared on success). Returns
    None — after logging — when the daemon itself cannot be listed; boot
    must not fail because docker is down."""
    async with session_factory() as db:
        enrolled = list(
            (await db.execute(select(Drive).where(col(Drive.lifecycle) == DriveLifecycle.ENROLLED))).scalars().all()
        )
        ripping = (await db.execute(select(Job).where(col(Job.status) == JobStatus.RIPPING))).scalars().all()
        busy = frozenset(j.drive_id for j in ripping if j.drive_id)
        try:
            summary = await asyncio.to_thread(manager.reconcile, enrolled, busy=busy)
        except RipperManagerError as exc:
            logger.error("ripper reconcile skipped: %s", exc)
            return None
        for drive in enrolled:
            if drive.id in summary.failed:
                drive.last_error = summary.failed[drive.id]
            elif drive.status is not DriveStatus.ERROR:
                drive.last_error = None  # a stale reason from a previous boot; ERROR rows keep theirs
            db.add(drive)
        await db.commit()
    return summary
