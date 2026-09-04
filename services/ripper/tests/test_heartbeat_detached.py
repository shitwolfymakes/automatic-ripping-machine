import os

os.environ.setdefault("ARM_DRIVE_DEV", "/dev/sr0")
os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

import asyncio  # noqa: E402

import pytest  # noqa: E402
from arm_common import DriveMediaStatus  # noqa: E402
from arm_ripper import main as ripper_main  # noqa: E402
from arm_ripper.drive_handle import DriveHandle  # noqa: E402


class _Client:
    def __init__(self) -> None:
        self.beats: list[DriveMediaStatus] = []

    async def heartbeat(self, *, drive_id: str, media_status: DriveMediaStatus) -> None:
        self.beats.append(media_status)

    async def get_current_job(self, drive_id: str):
        return None


class _Controller:
    def is_idle(self) -> bool:
        return True


async def _run(monkeypatch, handle: DriveHandle, beats: int) -> list[DriveMediaStatus]:
    client = _Client()
    n = {"i": 0}

    async def stop_after(_s: float) -> None:
        n["i"] += 1
        if n["i"] >= beats:
            raise asyncio.CancelledError

    monkeypatch.setattr(ripper_main.asyncio, "sleep", stop_after)
    monkeypatch.setattr(ripper_main, "probe_drive_media", lambda p: (DriveMediaStatus.NO_DISC, "fake"))
    with pytest.raises(asyncio.CancelledError):
        await ripper_main.heartbeat_loop(client, "drv_1", handle, _Controller())  # type: ignore[arg-type]
    return client.beats


async def test_absent_handle_reports_detached_and_keeps_beating(monkeypatch) -> None:
    beats = await _run(monkeypatch, DriveHandle(), beats=3)
    assert beats == [DriveMediaStatus.DETACHED] * 3


async def test_present_handle_probes_the_current_node(monkeypatch) -> None:
    beats = await _run(monkeypatch, DriveHandle("/dev/sr0"), beats=1)
    assert beats == [DriveMediaStatus.NO_DISC]


async def test_heartbeat_sees_the_move_without_restart(monkeypatch) -> None:
    probed: list[str] = []
    h = DriveHandle("/dev/sr0")
    client = _Client()
    n = {"i": 0}

    async def flip_then_stop(_s: float) -> None:
        n["i"] += 1
        if n["i"] == 1:
            h.set("/dev/sr2")
        else:
            raise asyncio.CancelledError

    def probe(p: str):
        probed.append(p)
        return DriveMediaStatus.NO_DISC, "fake"

    monkeypatch.setattr(ripper_main.asyncio, "sleep", flip_then_stop)
    monkeypatch.setattr(ripper_main, "probe_drive_media", probe)
    with pytest.raises(asyncio.CancelledError):
        await ripper_main.heartbeat_loop(client, "drv_1", h, _Controller())  # type: ignore[arg-type]
    assert probed == ["/dev/sr0", "/dev/sr2"]
