"""Shared host-resource probes (CPU%, CPU temp, memory) used by the backend
and the ripper. Storage probing stays service-local: the backend uses an
NFS-safe subprocess disk cache, the ripper an inline statvfs over local volumes.

Note the `except (AttributeError, OSError)` tuple — psutil.sensors_temperatures
is absent on some platforms (AttributeError) and can raise OSError reading
/sys; both mean "no temp available", so fall back to 0.0.
"""

import psutil  # type: ignore[import-untyped]

from arm_common.schemas.system import MemoryInfo

_GiB = 1073741824
_CPU_TEMP_KEYS = ("coretemp", "cpu_thermal", "k10temp")


def probe_cpu_percent() -> float:
    return float(psutil.cpu_percent(interval=None))


def probe_cpu_temp() -> float:
    try:
        temps = psutil.sensors_temperatures()
    except (AttributeError, OSError):
        return 0.0
    for key in _CPU_TEMP_KEYS:
        readings = temps.get(key)
        if readings:
            return float(readings[0].current)
    return 0.0


def probe_memory() -> MemoryInfo:
    mem = psutil.virtual_memory()
    return MemoryInfo(
        total_gb=round(mem.total / _GiB, 1),
        used_gb=round(mem.used / _GiB, 1),
        free_gb=round(mem.available / _GiB, 1),
        percent=mem.percent,
    )
