from unittest.mock import patch

from arm_common.schemas import MemoryInfo
from arm_common.utils import resource_probing as rp


def test_probe_memory_shape():
    class _VM:
        total = 8 * rp._GiB
        used = 2 * rp._GiB
        available = 6 * rp._GiB
        percent = 25.0

    with patch.object(rp.psutil, "virtual_memory", return_value=_VM()):
        mem = rp.probe_memory()
    assert isinstance(mem, MemoryInfo)
    assert mem.total_gb == 8.0
    assert mem.used_gb == 2.0
    assert mem.free_gb == 6.0
    assert mem.percent == 25.0


def test_probe_cpu_temp_reads_first_known_key():
    class _R:
        current = 47.5

    with patch.object(rp.psutil, "sensors_temperatures", return_value={"k10temp": [_R()]}):
        assert rp.probe_cpu_temp() == 47.5


def test_probe_cpu_temp_returns_zero_when_unavailable():
    with patch.object(rp.psutil, "sensors_temperatures", side_effect=OSError):
        assert rp.probe_cpu_temp() == 0.0
    with patch.object(rp.psutil, "sensors_temperatures", return_value={}):
        assert rp.probe_cpu_temp() == 0.0


def test_probe_cpu_percent_passthrough():
    with patch.object(rp.psutil, "cpu_percent", return_value=13.0):
        assert rp.probe_cpu_percent() == 13.0
