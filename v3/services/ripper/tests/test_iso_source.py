"""ARM_MANUAL_TRIGGER_ISO mode tests.

Covers the five code paths the iso-source helper flips:

  - source.is_iso_source / source.makemkv_source_url helpers
  - scan_disc: makemkvcon info source URL becomes `iso:<file>`
  - rip_disc: makemkvcon mkv source URL becomes `iso:<file>`
  - _temp_mount: mount options gain `,loop` for ISO sources
  - _eject_with_retry: skipped for ISO sources
  - heartbeat_loop: probe_drive_media is bypassed for ISO sources
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# arm_ripper.config builds a pydantic Settings at import time and refuses
# to load without these vars. Set placeholders before any arm_ripper.*
# import so importing main.py (for the heartbeat test) doesn't blow up.
os.environ.setdefault("ARM_DRIVE_DEV", "/dev/sr0")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend.invalid")
os.environ.setdefault("ARM_SERVICE_TOKEN", "test-token")

import arm_ripper.main as ripper_main  # noqa: E402
import arm_ripper.rip.makemkv_rip as makemkv_rip  # noqa: E402
import arm_ripper.scan.disc_probe as disc_probe  # noqa: E402
import arm_ripper.scan.makemkv as scan_makemkv  # noqa: E402
from arm_common import DriveMediaStatus  # noqa: E402
from arm_ripper.source import is_iso_source, makemkv_source_url  # noqa: E402


# --- helpers ---------------------------------------------------------------


class _FakeStream:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)

    async def readline(self) -> bytes:
        if not self._lines:
            return b""
        return self._lines.pop(0)

    async def read(self) -> bytes:
        return b""


class _FakeProc:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self._final_returncode = returncode
        self.returncode: int | None = None
        # For rip_disc which streams line-by-line.
        self.stdout = _FakeStream([])
        self.stderr = _FakeStream([])

    async def communicate(self) -> tuple[bytes, bytes]:
        self.returncode = self._final_returncode
        return self._stdout, self._stderr

    async def wait(self) -> int:
        await asyncio.sleep(0)
        self.returncode = self._final_returncode
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9


def _capture_subprocess(monkeypatch, module: Any, *, returncode: int = 0, stdout: bytes = b"") -> list[tuple[Any, ...]]:
    """Replace `module.asyncio.create_subprocess_exec` with a recorder.

    Returns a list that accumulates the positional args of every call —
    asserts can inspect `calls[0][...]` to find the source URL.
    """
    calls: list[tuple[Any, ...]] = []

    async def fake_create(*args: Any, **_kwargs: Any) -> _FakeProc:
        calls.append(args)
        return _FakeProc(stdout=stdout, returncode=returncode)

    monkeypatch.setattr(module.asyncio, "create_subprocess_exec", fake_create)
    return calls


# --- source helpers --------------------------------------------------------


def test_is_iso_source_true_for_real_iso_file(tmp_path: Path) -> None:
    iso = tmp_path / "sintel.iso"
    iso.write_bytes(b"")
    assert is_iso_source(str(iso)) is True


def test_is_iso_source_false_for_dev_node() -> None:
    # `/dev/sr0` always exists on a host with an optical drive, but it's
    # a block device, not a regular file — Path.is_file() returns False.
    assert is_iso_source("/dev/sr0") is False


def test_is_iso_source_false_for_iso_suffix_with_missing_file(tmp_path: Path) -> None:
    # Suffix matches but file is absent — must not classify as ISO.
    assert is_iso_source(str(tmp_path / "ghost.iso")) is False


def test_is_iso_source_false_for_uppercase_suffix(tmp_path: Path) -> None:
    # Helper is intentionally lower-case-only to avoid widening detection
    # by accident. Document it in the test.
    iso = tmp_path / "SINTEL.ISO"
    iso.write_bytes(b"")
    assert is_iso_source(str(iso)) is False


def test_is_iso_source_false_for_directory(tmp_path: Path) -> None:
    d = tmp_path / "sintel.iso"
    d.mkdir()
    assert is_iso_source(str(d)) is False


def test_makemkv_source_url_iso_for_file(tmp_path: Path) -> None:
    iso = tmp_path / "sintel.iso"
    iso.write_bytes(b"")
    assert makemkv_source_url(str(iso)) == f"iso:{iso}"


def test_makemkv_source_url_dev_for_device() -> None:
    assert makemkv_source_url("/dev/sr0") == "dev:/dev/sr0"


# --- scan_disc command-line ------------------------------------------------


@pytest.mark.asyncio
async def test_scan_disc_uses_iso_source_url_for_iso_path(monkeypatch, tmp_path: Path) -> None:
    iso = tmp_path / "sintel.iso"
    iso.write_bytes(b"")
    # Empty stdout → parse_makemkvcon_info returns empty titles. probe_disc
    # is best-effort and never raises. We only care about the cmd shape.
    calls = _capture_subprocess(monkeypatch, scan_makemkv, returncode=0, stdout=b"")
    # Skip the real probe_disc — it would try to mount.
    monkeypatch.setattr(
        scan_makemkv,
        "probe_disc",
        AsyncMock(return_value=disc_probe.DiscProbe(disc_type=None, crc64=None)),
    )

    await scan_makemkv.scan_disc(str(iso))

    assert calls, "create_subprocess_exec was never called"
    argv = calls[0]
    assert argv[0] == "makemkvcon"
    assert f"iso:{iso}" in argv
    assert not any(str(a).startswith("dev:") for a in argv), argv


@pytest.mark.asyncio
async def test_scan_disc_keeps_dev_source_url_for_block_device(monkeypatch) -> None:
    calls = _capture_subprocess(monkeypatch, scan_makemkv, returncode=0, stdout=b"")
    monkeypatch.setattr(
        scan_makemkv,
        "probe_disc",
        AsyncMock(return_value=disc_probe.DiscProbe(disc_type=None, crc64=None)),
    )

    await scan_makemkv.scan_disc("/dev/sr0")

    argv = calls[0]
    assert "dev:/dev/sr0" in argv
    assert not any(str(a).startswith("iso:") for a in argv), argv


# --- rip_disc command-line -------------------------------------------------


@pytest.mark.asyncio
async def test_rip_disc_uses_iso_source_url_for_iso_path(monkeypatch, tmp_path: Path) -> None:
    iso = tmp_path / "sintel.iso"
    iso.write_bytes(b"")
    output_dir = tmp_path / "out"
    calls: list[tuple[Any, ...]] = []

    async def fake_create(*args: Any, **_kwargs: Any) -> _FakeProc:
        calls.append(args)
        return _FakeProc(returncode=0)

    monkeypatch.setattr(makemkv_rip.asyncio, "create_subprocess_exec", fake_create)

    await makemkv_rip.rip_disc(
        device_path=str(iso),
        output_dir=output_dir,
        minlength_seconds=600,
        eligible_source_indexes=[],
    )

    assert calls, "create_subprocess_exec was never called"
    argv = calls[0]
    assert argv[0] == "makemkvcon"
    assert f"iso:{iso}" in argv
    assert not any(str(a).startswith("dev:") for a in argv), argv


@pytest.mark.asyncio
async def test_rip_disc_keeps_dev_source_url_for_block_device(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[Any, ...]] = []

    async def fake_create(*args: Any, **_kwargs: Any) -> _FakeProc:
        calls.append(args)
        return _FakeProc(returncode=0)

    monkeypatch.setattr(makemkv_rip.asyncio, "create_subprocess_exec", fake_create)

    await makemkv_rip.rip_disc(
        device_path="/dev/sr0",
        output_dir=tmp_path / "out",
        minlength_seconds=600,
        eligible_source_indexes=[],
    )

    argv = calls[0]
    assert "dev:/dev/sr0" in argv
    assert not any(str(a).startswith("iso:") for a in argv), argv


# --- _temp_mount loop option -----------------------------------------------


@pytest.mark.asyncio
async def test_temp_mount_uses_loop_option_for_iso(monkeypatch, tmp_path: Path) -> None:
    iso = tmp_path / "sintel.iso"
    iso.write_bytes(b"")
    captured: list[tuple[str, ...]] = []

    async def fake_run(*argv: str, log_failure: bool = True) -> tuple[int | None, str]:
        captured.append(argv)
        # mount succeeds; umount is recorded but irrelevant
        return 0, ""

    monkeypatch.setattr(disc_probe, "_run", fake_run)

    async with disc_probe._temp_mount(str(iso)) as mount_dir:
        assert mount_dir is not None

    assert captured, "_run was never called"
    mount_argv = captured[0]
    assert mount_argv[0] == "mount"
    assert "-o" in mount_argv
    opts_idx = mount_argv.index("-o") + 1
    assert mount_argv[opts_idx] == "ro,loop"
    assert str(iso) in mount_argv


@pytest.mark.asyncio
async def test_temp_mount_keeps_ro_only_for_block_device(monkeypatch) -> None:
    captured: list[tuple[str, ...]] = []

    async def fake_run(*argv: str, log_failure: bool = True) -> tuple[int | None, str]:
        captured.append(argv)
        return 0, ""

    monkeypatch.setattr(disc_probe, "_run", fake_run)

    async with disc_probe._temp_mount("/dev/sr0") as mount_dir:
        assert mount_dir is not None

    mount_argv = captured[0]
    opts_idx = mount_argv.index("-o") + 1
    assert mount_argv[opts_idx] == "ro"
    assert "/dev/sr0" in mount_argv


# --- eject skip ------------------------------------------------------------


@pytest.mark.asyncio
async def test_eject_with_retry_skips_for_iso_source(tmp_path: Path) -> None:
    from arm_ripper.job_controller import JobController

    iso = tmp_path / "sintel.iso"
    iso.write_bytes(b"")

    controller = JobController(
        client=MagicMock(),
        drive_id="drv_iso",
        ws=MagicMock(),
        device_path=str(iso),
        default_min_length_seconds=120,
    )
    # If _run_command got called, it'd shell `umount` / `eject`. The test
    # would not crash (the AsyncMock would absorb it), but we want to
    # *assert* no shell-out happened at all.
    controller._run_command = AsyncMock()  # type: ignore[method-assign]

    await controller._eject_with_retry(str(iso))

    controller._run_command.assert_not_called()


@pytest.mark.asyncio
async def test_eject_with_retry_runs_for_block_device(monkeypatch) -> None:
    from arm_ripper.job_controller import JobController

    controller = JobController(
        client=MagicMock(),
        drive_id="drv_sr0",
        ws=MagicMock(),
        device_path="/dev/sr0",
        default_min_length_seconds=120,
    )
    # Short-circuit the retry delays so the test runs fast.
    monkeypatch.setattr("arm_ripper.job_controller.EJECT_RETRY_DELAYS", [0])
    controller._run_command = AsyncMock(return_value=(0, ""))  # type: ignore[method-assign]

    await controller._eject_with_retry("/dev/sr0")

    # umount first, then eject — both fired.
    called_argvs = [call.args for call in controller._run_command.call_args_list]
    assert any("umount" in argv for argv in called_argvs)
    assert any("eject" in argv for argv in called_argvs)


# --- heartbeat ISO short-circuit ------------------------------------------


@pytest.mark.asyncio
async def test_heartbeat_short_circuits_probe_for_iso_source(monkeypatch, tmp_path: Path) -> None:
    iso = tmp_path / "sintel.iso"
    iso.write_bytes(b"")
    probe_calls: list[str] = []

    def fake_probe(path: str) -> tuple[DriveMediaStatus, str]:
        probe_calls.append(path)
        return DriveMediaStatus.UNKNOWN, "should-not-be-called"

    monkeypatch.setattr(ripper_main, "probe_drive_media", fake_probe)

    client = MagicMock()
    client.heartbeat = AsyncMock()

    # Cancel after one tick so the test doesn't hang on the loop.
    async def cancel_after_one_tick() -> None:
        await asyncio.sleep(0)
        task.cancel()

    task = asyncio.create_task(ripper_main.heartbeat_loop(client, "drv_iso", str(iso)))
    asyncio.create_task(cancel_after_one_tick())
    with pytest.raises(asyncio.CancelledError):
        await task

    assert probe_calls == [], "probe_drive_media must not be called for ISO sources"
    client.heartbeat.assert_called_once()
    assert client.heartbeat.call_args.kwargs["media_status"] == DriveMediaStatus.LOADED
