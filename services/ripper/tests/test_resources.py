from unittest.mock import patch

from arm_common.schemas import HostResourcesSnapshot
from arm_ripper import resources as rr


def test_gather_resources_shape(tmp_path) -> None:
    roots = {"RAW_ROOT": str(tmp_path)}
    with (
        patch.object(rr, "probe_cpu_percent", return_value=7.0),
        patch.object(rr, "probe_cpu_temp", return_value=0.0),
    ):
        snap = rr.gather_resources(roots)
    assert isinstance(snap, HostResourcesSnapshot)
    assert snap.cpu_percent == 7.0
    assert len(snap.storage) == 1
    assert snap.storage[0].name == "RAW_ROOT"
    assert snap.storage[0].total_gb >= 0.0


def test_gather_resources_skips_missing_root() -> None:
    roots = {"NOPE": "/no/such/path/xyz"}
    with (
        patch.object(rr, "probe_cpu_percent", return_value=1.0),
        patch.object(rr, "probe_cpu_temp", return_value=0.0),
    ):
        snap = rr.gather_resources(roots)
    assert snap.storage == []
