"""What a transcode-family container is run with (its environment, mounts and GPU run options).

Shared by task spawns and GPU probes.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from arm_backend.config import Settings
from arm_common import Gpu, TranscodeTask
from arm_common.encoders import EncoderSpec
from arm_common.enums import GpuVendor

logger = logging.getLogger(__name__)


def container_identity_env(settings: Settings, gpu_vendor: GpuVendor | None) -> dict[str, str]:
    env: dict[str, str] = {}
    # Override the drop uid/gid so the transcoder writes /media as the
    # owner of the (possibly remote) media export, instead of the
    # entrypoint's default uid. Empty settings leave the default in place.
    if settings.ARM_TRANSCODE_PUID:
        env["PUID"] = settings.ARM_TRANSCODE_PUID
    if settings.ARM_TRANSCODE_PGID:
        env["PGID"] = settings.ARM_TRANSCODE_PGID
    # VAAPI/QSV: the entrypoint self-derives the render gid from the
    # mounted node; an explicit ARM_RENDER_GID is a forced OVERRIDE
    # (passed through as RENDER_GID, which wins in the entrypoint).
    if gpu_vendor in (GpuVendor.VAAPI, GpuVendor.QSV) and settings.ARM_RENDER_GID:
        env["RENDER_GID"] = settings.ARM_RENDER_GID
    return env


def gpu_run_kwargs(gpu: Gpu) -> dict[str, Any]:
    """Vendor-specific docker-py kwargs.

    VAAPI/QSV: pass the `/dev/dri/renderD*` node via `devices=`.
    NVENC: ask for the NVIDIA runtime + a single GPU via `device_requests`.
    """
    kwargs: dict[str, Any] = {}
    if gpu.vendor in (GpuVendor.VAAPI, GpuVendor.QSV):
        # Grant cgroup access to the render node. File-level access (the node
        # is root:render 0660) is handled by the container entrypoint adding
        # `arm` to RENDER_GID — see TranscodeDispatcher._spawn_container; a
        # docker group_add here wouldn't survive the entrypoint's gosu group
        # reset.
        kwargs["devices"] = [f"{gpu.device_path}:{gpu.device_path}:rwm"]
        return kwargs
    if gpu.vendor == GpuVendor.NVENC:
        # device_path is "nvidia://N"; pass the index as a string ID so
        # `--gpus device=N` semantics select that single GPU.
        #
        # `count` and `device_ids` are mutually exclusive on the docker
        # daemon side ("cannot set both Count and DeviceIDs on device
        # request"). Pin to a specific GPU when we have an index;
        # otherwise fall back to "count: 1 (any free GPU)".
        idx = gpu.device_path.removeprefix("nvidia://")
        base_kwargs: dict[str, Any] = {
            "driver": "nvidia",
            "capabilities": [["gpu", "video"]],
        }
        if idx:
            base_kwargs["device_ids"] = [idx]
        else:
            base_kwargs["count"] = 1
        try:
            import docker  # type: ignore[import-untyped]

            kwargs["runtime"] = "nvidia"
            kwargs["device_requests"] = [docker.types.DeviceRequest(**base_kwargs)]
        # docker-py is a hard dependency (pyproject) — this fallback is dead.
        except ImportError:  # pragma: no cover
            # Defensive guard: keeps the kwarg shape correct if docker-py
            # is ever missing.
            kwargs["runtime"] = "nvidia"
            fallback = {
                "Driver": base_kwargs["driver"],
                "Capabilities": base_kwargs["capabilities"],
            }
            if "device_ids" in base_kwargs:
                fallback["DeviceIDs"] = base_kwargs["device_ids"]
            else:
                fallback["Count"] = base_kwargs["count"]
            kwargs["device_requests"] = [fallback]
    return kwargs


def backend_url_for_spawn(settings: Settings) -> str:
    remote = bool(settings.ARM_TRANSCODE_DOCKER_HOST)
    if remote and not settings.ARM_TRANSCODE_BACKEND_URL:
        logger.warning(
            "ARM_TRANSCODE_DOCKER_HOST set but ARM_TRANSCODE_BACKEND_URL empty — "
            "remote transcoder will use the unroutable in-network https://arm-backend:8443; "
            "set ARM_TRANSCODE_BACKEND_URL to a host-routable backend URL"
        )
    return (
        settings.ARM_TRANSCODE_BACKEND_URL
        if remote and settings.ARM_TRANSCODE_BACKEND_URL
        else "https://arm-backend:8443"
    )


def task_env(settings: Settings, task: TranscodeTask, backend_url: str) -> dict[str, str]:
    return {
        "ARM_TRANSCODE_TASK_ID": task.id,
        "ARM_BACKEND_URL": backend_url,
        "ARM_SERVICE_TOKEN": settings.ARM_SERVICE_TOKEN,
        "ARM_LOG_LEVEL": settings.ARM_LOG_LEVEL,
        # Per-task log filename so parallel transcoders don't
        # clobber a shared `/logs/arm-transcode.log` rotation.
        "ARM_SERVICE_NAME": f"arm-transcode-{task.id[-12:]}",
    }


def task_volumes(settings: Settings) -> dict[str, dict[str, str]]:
    certs_root = Path(settings.ARM_HOST_CERTS_PATH)
    return {
        settings.ARM_HOST_RAW_PATH: {"bind": "/raw", "mode": "ro"},
        settings.ARM_HOST_MEDIA_PATH: {"bind": "/media", "mode": "rw"},
        settings.ARM_HOST_LOGS_PATH: {"bind": "/logs", "mode": "rw"},
        str(certs_root / "arm-ca.crt"): {"bind": "/etc/ssl/arm/arm-ca.crt", "mode": "ro"},
    }


def gpu_env(gpu: Gpu | None, encoder: EncoderSpec | None) -> dict[str, str]:
    env: dict[str, str] = {}
    if encoder is not None:
        # The worker resolves everything from the catalog id. The
        # ARM_GPU_* vars below are a harmless fallback only: an image that
        # predates --probe-device can never verify a row, so it is never
        # handed a GPU; the upgrade path is rebuilding or pulling it.
        env["ARM_TRANSCODE_ENCODER"] = encoder.id
    if gpu is not None:
        env["ARM_GPU_VENDOR"] = gpu.vendor.value
        env["ARM_GPU_DEVICE"] = gpu.device_path
        if encoder is not None:
            env["ARM_GPU_CODEC"] = str(encoder.codec)
    return env
