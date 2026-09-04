# services/ripper/tests/test_poll_loop_absence.py
"""poll_loop: absence is a first-class, once-logged transition; reattach
re-arms insert detection and re-runs the boot probe; renumbering is followed
and reported to the backend."""

import os

os.environ.setdefault("ARM_DRIVE_DEV", "/dev/sr0")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

import asyncio  # noqa: E402
import errno  # noqa: E402
import logging  # noqa: E402

import pytest  # noqa: E402
from arm_ripper import main as ripper_main  # noqa: E402
from arm_ripper.drive_handle import DriveHandle  # noqa: E402
from arm_ripper.drive_poll import DriveState  # noqa: E402
from arm_ripper.drive_resolve import ResolvedDevice  # noqa: E402


class _Controller:
    def __init__(self) -> None:
        self.inserted: list[str] = []
        self.idle = True

    def is_idle(self) -> bool:
        return self.idle

    async def handle_disc_inserted(self, device: str) -> None:
        self.inserted.append(device)


class _Client:
    def __init__(self, order: list[str] | None = None) -> None:
        self.device_path_updates: list[str] = []
        self.drive_device_path: str | None = None
        self.order = order if order is not None else []

    async def update_device_path(self, *, drive_id: str, device_path: str) -> None:
        self.device_path_updates.append(device_path)
        self.order.append("report_node")

    async def get_drive(self, drive_id: str):
        if self.drive_device_path is None:
            return None

        class _D:
            device_path = self.drive_device_path

        return _D()


class Script:
    """Feed poll_loop a scripted sequence of (resolution, drive status) per tick."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, ticks: list[tuple[ResolvedDevice | None, object]]) -> None:
        self.ticks = ticks
        self.i = 0
        self.boot_probes = 0
        self.order: list[str] = []
        self.client = _Client(self.order)
        self.controller = _Controller()
        # Ruling B: amain pre-resolves the handle before the loop starts, so
        # present-at-start is the realistic initial state.
        self.handle = DriveHandle("/dev/sr0")

        def fake_resolve(by_id, hint, *, disk_root, dev_root, sysfs_root):
            if self.i >= len(self.ticks):
                raise asyncio.CancelledError
            return self.ticks[self.i][0]

        def fake_status(device: str) -> DriveState:
            item = self.ticks[self.i][1]
            if isinstance(item, int) and not isinstance(item, DriveState):
                raise OSError(item, "x", device)
            assert isinstance(item, DriveState)
            return item

        async def fake_boot_probe(client, drive_id, device_path, controller) -> None:
            self.boot_probes += 1
            self.order.append("boot_probe")

        real_sleep = asyncio.sleep

        # Ruling D: yield so create_task()'d pipelines actually run.
        async def tick_sleep(_s: float) -> None:
            self.i += 1
            await real_sleep(0)  # yield so create_task()'d pipelines actually run

        monkeypatch.setattr(ripper_main, "resolve_drive_device", fake_resolve)
        monkeypatch.setattr(ripper_main, "read_drive_status", fake_status)
        monkeypatch.setattr(ripper_main, "boot_probe", fake_boot_probe)
        monkeypatch.setattr(ripper_main.asyncio, "sleep", tick_sleep)

    async def run(self) -> None:
        with pytest.raises(asyncio.CancelledError):
            await ripper_main.poll_loop(self.controller, self.handle, client=self.client, drive_id="drv_1")  # type: ignore[arg-type]


SR0 = ResolvedDevice(path="/dev/sr0", via="by_id")
SR2 = ResolvedDevice(path="/dev/sr2", via="by_id")


async def test_absence_is_logged_once_across_many_polls(monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO, logger="arm_ripper")
    s = Script(monkeypatch, [(SR0, DriveState.NO_DISC)] + [(None, None)] * 20)
    await s.run()
    absent = [r for r in caplog.records if "drive absent" in r.message]
    assert len(absent) == 1
    assert s.handle.absent


async def test_reattach_resets_detector_and_reruns_boot_probe(monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO, logger="arm_ripper")
    s = Script(
        monkeypatch,
        [
            (SR0, DriveState.DISC_OK),  # disc A rips
            (None, None),  # unplugged
            (None, None),
            (SR0, DriveState.DISC_OK),  # back, with (maybe) disc B seated: must rip again
        ],
    )
    await s.run()
    assert s.controller.inserted == ["/dev/sr0", "/dev/sr0"]
    assert s.boot_probes == 1
    assert sum("drive present" in r.message for r in caplog.records) == 1
    # The hint that found the drive is logged as such (spec §4), and the node
    # is reported to the backend BEFORE the probe — _on_reattached can run a
    # whole resumed rip, and the UI must not sit on the stale node meanwhile.
    assert any("drive present at /dev/sr0 via by_id (reattached)" in r.message for r in caplog.records)
    assert s.order == ["report_node", "boot_probe"]


async def test_a_move_logs_the_resolution_hint(monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO, logger="arm_ripper")
    s = Script(monkeypatch, [(SR0, DriveState.NO_DISC), (SR2, DriveState.NO_DISC)])
    await s.run()
    assert any("drive node moved to /dev/sr2 via by_id" in r.message for r in caplog.records)


async def test_reattach_skips_boot_probe_while_a_rip_is_still_running(monkeypatch, caplog) -> None:
    """The drive was yanked mid-rip: makemkvcon is still running against the
    old node when it comes back. boot_probe would resume the same job, wipe
    the raw dir under the live process and start a second rip."""
    caplog.set_level(logging.INFO, logger="arm_ripper")
    s = Script(
        monkeypatch,
        [
            (SR0, DriveState.DISC_OK),  # disc A starts ripping
            (None, None),  # unplugged mid-rip
            (SR0, DriveState.DISC_OK),  # back — but the pipeline never stopped
        ],
    )
    s.controller.idle = False
    await s.run()
    assert s.boot_probes == 0
    assert sum("skipping boot probe" in r.message for r in caplog.records) == 1


async def test_renumbering_is_followed_and_reported(monkeypatch) -> None:
    s = Script(monkeypatch, [(SR0, DriveState.NO_DISC), (None, None), (SR2, DriveState.DISC_OK)])
    await s.run()
    assert s.handle.current == "/dev/sr2"
    assert s.controller.inserted == ["/dev/sr2"]
    assert s.client.device_path_updates == ["/dev/sr2"]


async def test_node_vanishing_between_resolve_and_open_becomes_absent(monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO, logger="arm_ripper")
    s = Script(monkeypatch, [(SR0, DriveState.NO_DISC), (SR0, errno.ENXIO), (SR0, errno.ENXIO)])
    await s.run()
    # resolve said present but open() said ENXIO: that's absence, logged once.
    assert sum("drive absent" in r.message for r in caplog.records) == 1
    assert not any("ioctl failed" in r.message for r in caplog.records)


async def test_permission_errors_log_once_as_misconfigured(monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO, logger="arm_ripper")
    s = Script(monkeypatch, [(SR0, errno.EPERM)] * 6)
    await s.run()
    mis = [r for r in caplog.records if "misconfigured" in r.message]
    assert len(mis) == 1
    assert not any("ioctl failed" in r.message for r in caplog.records)


async def test_other_errors_still_log_every_poll(monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO, logger="arm_ripper")
    s = Script(monkeypatch, [(SR0, errno.EIO)] * 4)
    await s.run()
    assert sum("ioctl failed" in r.message for r in caplog.records) == 4


async def test_port_identity_refreshes_hint_from_backend_while_absent(monkeypatch) -> None:
    """No by-id link: the only way to follow a renumbering is the backend's
    scanner, which keeps device_path current by port. The loop must ask."""
    monkeypatch.setattr(ripper_main.settings, "ARM_DRIVE_BY_ID", None)
    seen_hints: list[str] = []

    s = Script(monkeypatch, [(None, None), (None, None), (SR2, DriveState.NO_DISC)])
    s.client.drive_device_path = "/dev/sr2"
    real = ripper_main.resolve_drive_device

    def spy(by_id, hint, **kw):
        seen_hints.append(hint)
        return real(by_id, hint, **kw)

    monkeypatch.setattr(ripper_main, "resolve_drive_device", spy)
    await s.run()
    assert "/dev/sr2" in seen_hints  # backend-supplied hint was used
