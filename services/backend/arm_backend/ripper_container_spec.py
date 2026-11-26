"""What a ripper container is run with: its name, its `containers.run` kwargs
and the spec hash that marks drift."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import docker.types  # type: ignore[import-untyped]

from arm_backend.config import Settings
from arm_backend.container_logging import log_config
from arm_backend.iso_library import iso_host_path
from arm_common import Drive, DriveKind

DOCKER_LABEL_KEY = "arm.drive_id"
VIRTUAL_LABEL_KEY = "arm.virtual"
# sha256 of the spec the container was created from; reconcile recreates an idle
# ripper whose label no longer matches (a changed ARM_RIPPER_* tunable, PUID, ...).
SPEC_HASH_LABEL_KEY = "arm.spec_hash"
_DEVICE_CGROUP_RULES = ["b 11:* rmw", "c 21:* rmw"]  # sr* block + sg* char majors
_HOST_DISK_MOUNT = "/host-disk"
# Optical-only env: a virtual (ISO) ripper has no device, no /dev/disk and no cdrom group.
_OPTICAL_ONLY_ENV = ("ARM_DRIVE_DEV", "ARM_HOST_DISK_ROOT", "ARM_DRIVE_BY_ID", "CDROM_GID")

# backend Settings name -> env name the ripper/entrypoint reads
_TUNABLE_ENV: dict[str, str] = {
    "ARM_RIPPER_POLL_INTERVAL_SECONDS": "POLL_INTERVAL_SECONDS",
    "ARM_RIPPER_MIN_LENGTH_SECONDS": "ARM_MIN_LENGTH_SECONDS",
    "ARM_RIPPER_MAKEMKV_KEYCHECK_INTERVAL_SECONDS": "MAKEMKV_KEYCHECK_INTERVAL_SECONDS",
    "ARM_RIPPER_NOT_READY_REARM_POLLS": "ARM_NOT_READY_REARM_POLLS",
    "ARM_RIPPER_OPTICAL_SR_MAX": "ARM_OPTICAL_SR_MAX",
    "ARM_RIPPER_OPTICAL_SG_MAX": "ARM_OPTICAL_SG_MAX",
}


def _spec_hash(spec: dict[str, Any]) -> str:
    """Hash of every `containers.run` kwarg except the labels that carry it.
    Image drift is caught by image id in `_image_current`; this catches the
    rest (environment, mounts, network, ...)."""
    material = {k: v for k, v in spec.items() if k != "labels"}
    return hashlib.sha256(json.dumps(material, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def certs_path(settings: Settings) -> str:
    """Local host certs dir for the rippers' CA mount — ARM_RIPPER_CERTS_PATH
    when set (remote-transcode installs), else ARM_HOST_CERTS_PATH."""
    return settings.ARM_RIPPER_CERTS_PATH or settings.ARM_HOST_CERTS_PATH


def container_name(drive: Drive) -> str:
    """`arm-ripper-<serial slug>-<drive-id suffix>` — a stable slot label;
    srN is not in the name because the node moves. The drive-id suffix
    keeps two drives that report the same short serial (common behind USB
    bridges) from colliding on the name. Falls back to the drive-id suffix
    alone when the drive has no serial. Lower-cased `[a-z0-9-]` so it is
    valid both as a docker name and as a hostname. A virtual (ISO) drive
    is `arm-ripper-iso-<drive-id suffix>`."""
    if drive.kind == DriveKind.VIRTUAL:
        return f"arm-ripper-iso-{drive.id[-12:].lower()}"
    id_slug = drive.id[-12:].lower()
    serial_slug = re.sub(r"[^a-z0-9]+", "-", (drive.serial or "").lower()).strip("-")
    if not serial_slug:
        return f"arm-ripper-{id_slug}"
    return f"arm-ripper-{serial_slug}-{drive.id[-6:].lower()}"


def container_spec(settings: Settings, drive: Drive) -> dict[str, Any]:
    """kwargs for `containers.run` — what the ripper needs and nothing more:
    no `devices:` bind (the entrypoint pre-creates nodes), no
    per-ripper cert, `/dev/disk` not `/dev`."""
    s = settings
    name = container_name(drive)
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
    certs_root = Path(certs_path(settings))
    volumes = {
        s.ARM_HOST_RAW_PATH: {"bind": "/raw", "mode": "rw"},
        s.ARM_HOST_LOGS_PATH: {"bind": "/logs", "mode": "rw"},
        str(certs_root / "arm-ca.crt"): {"bind": "/etc/ssl/arm/arm-ca.crt", "mode": "ro"},
        "/dev/disk": {"bind": _HOST_DISK_MOUNT, "mode": "ro"},
    }
    spec: dict[str, Any] = {
        "image": s.ARM_RIPPER_IMAGE,
        "name": name,
        "hostname": name,
        "labels": {DOCKER_LABEL_KEY: drive.id},
        "environment": env,
        "volumes": volumes,
        "network": s.ARM_DOCKER_NETWORK,
        "device_cgroup_rules": list(_DEVICE_CGROUP_RULES),
        "restart_policy": {"Name": "unless-stopped"},
        "log_config": log_config(),
        "detach": True,
    }
    if drive.kind == DriveKind.VIRTUAL:
        spec = _virtual_spec(settings, drive, spec)
    spec["labels"][SPEC_HASH_LABEL_KEY] = _spec_hash(spec)
    return spec


def _virtual_spec(settings: Settings, drive: Drive, spec: dict[str, Any]) -> dict[str, Any]:
    """Turn the optical spec into a one-shot ISO ripper's: only
    the chosen ISO is mounted, read-only, at the drive's device_path
    (`/source/<file name>`); no /dev/disk, no device cgroup rules, no
    cdrom group; restart policy "no" (the watchdog cleans up).

    The ISO goes in `mounts`, not `volumes`: docker-py renders a volume
    as `host:container:mode`, so a file name with a colon in it
    (`Star Wars: Episode IV.iso`) breaks the spec, while a Mount carries
    source and target as separate fields."""
    assert drive.source_path is not None, "a virtual drive always has a source_path"
    source = drive.device_path
    env = {k: v for k, v in spec["environment"].items() if k not in _OPTICAL_ONLY_ENV}
    env["ARM_SOURCE_PATH"] = source
    session_id = (drive.rip_params_json or {}).get("session_id")
    if session_id:
        env["ARM_SOURCE_SESSION_ID"] = str(session_id)
    volumes = dict(spec["volumes"])
    volumes.pop("/dev/disk")
    library_host = settings.ARM_HOST_ISO_LIBRARY_PATH
    iso_mount = docker.types.Mount(
        target=source,
        source=iso_host_path(drive.source_path, library_host=library_host),
        type="bind",
        read_only=True,
    )
    virtual = {
        **spec,
        "environment": env,
        "volumes": volumes,
        "mounts": [iso_mount],
        "labels": {DOCKER_LABEL_KEY: drive.id, VIRTUAL_LABEL_KEY: "1"},
        "restart_policy": {"Name": "no"},
    }
    virtual.pop("device_cgroup_rules")
    return virtual
