from arm_common.enums import DriveMediaStatus
from arm_common.schemas import HostResourcesSnapshot, MemoryInfo, RipperHeartbeatRequest


def test_heartbeat_carries_hostname_and_optional_resources():
    snap = HostResourcesSnapshot(
        cpu_percent=1.0,
        cpu_temp=0.0,
        memory=MemoryInfo(total_gb=8.0, used_gb=1.0, free_gb=7.0, percent=12.5),
        storage=[],
    )
    req = RipperHeartbeatRequest(
        drive_id="drv_1",
        media_status=DriveMediaStatus.LOADED,
        hostname="ripper-sr0",
        resources=snap,
    )
    assert req.hostname == "ripper-sr0"
    assert req.resources is not None
    assert req.resources.cpu_percent == 1.0


def test_heartbeat_resources_defaults_none():
    req = RipperHeartbeatRequest(
        drive_id="drv_1",
        media_status=DriveMediaStatus.NO_DISC,
        hostname="ripper-sr0",
    )
    assert req.resources is None
