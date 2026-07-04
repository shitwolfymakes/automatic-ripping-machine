"""Ripper-side host-resource gathering. CPU/mem come from the shared
arm_common probe; storage is an inline statvfs over the ripper's LOCAL
mounted volumes (no NFS-cache machinery needed — these are local disks)."""

import os

from arm_common.schemas import HostResourcesSnapshot, StorageRoot
from arm_common.utils.resource_probing import probe_cpu_percent, probe_cpu_temp, probe_memory

_GiB = 1073741824


def _storage_for(name: str, path: str) -> StorageRoot | None:
    if not os.path.isdir(path):
        return None
    try:
        st = os.statvfs(path)
    except OSError:
        return None
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    used = total - (st.f_bfree * st.f_frsize)
    percent = round(100.0 * used / total, 1) if total else 0.0
    return StorageRoot(
        name=name,
        path=path,
        total_gb=round(total / _GiB, 1),
        used_gb=round(used / _GiB, 1),
        free_gb=round(free / _GiB, 1),
        percent=percent,
    )


def gather_resources(roots: dict[str, str]) -> HostResourcesSnapshot:
    storage = [s for s in (_storage_for(n, p) for n, p in roots.items()) if s is not None]
    return HostResourcesSnapshot(
        cpu_percent=probe_cpu_percent(),
        cpu_temp=probe_cpu_temp(),
        memory=probe_memory(),
        storage=storage,
    )
