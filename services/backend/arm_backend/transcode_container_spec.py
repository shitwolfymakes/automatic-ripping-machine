"""What a transcode-family container is run with (its environment, mounts and GPU run options).

Shared by task spawns and GPU probes.
"""

from __future__ import annotations

from typing import Any

from arm_common import Gpu
from arm_common.enums import GpuVendor


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
            # Legacy guard from when docker-py was test-optional. Kept
            # so the kwarg shape stays correct if that ever regresses.
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
