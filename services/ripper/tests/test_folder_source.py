"""Disc-folder sources ("Rip from folder"): the backend mounts a BDMV /
VIDEO_TS folder at /source/<name>; MakeMKV reads it as `file:<folder>`, and
every drive-only step (drive-status ioctl, eject, scan settle retry, the
optical fingerprint probe) is skipped exactly as for an ISO file."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend.invalid")
os.environ.setdefault("ARM_SERVICE_TOKEN", "test-token")

import arm_ripper.scan.data as data_module  # noqa: E402
import arm_ripper.scan.disc_probe as disc_probe  # noqa: E402
from arm_common import DiscType  # noqa: E402
from arm_ripper.source import is_file_source, is_folder_source, is_iso_source, makemkv_source_url  # noqa: E402


def _disc(tmp_path: Path, name: str, video_dir: str = "BDMV") -> Path:
    d = tmp_path / name
    (d / video_dir).mkdir(parents=True)
    return d


def test_a_disc_folder_is_read_by_makemkv_as_a_folder(tmp_path: Path) -> None:
    bd = _disc(tmp_path, "MirrorMask (2005)")
    dvd = _disc(tmp_path, "Half Baked", "VIDEO_TS")
    assert makemkv_source_url(str(bd)) == f"file:{bd}"
    assert makemkv_source_url(str(dvd)) == f"file:{dvd}"


def test_source_kinds(tmp_path: Path) -> None:
    bd = _disc(tmp_path, "bd")
    iso = tmp_path / "x.iso"
    iso.write_bytes(b"\0")
    plain = tmp_path / "plain"
    plain.mkdir()

    assert is_folder_source(str(bd)) and is_file_source(str(bd)) and not is_iso_source(str(bd))
    assert is_iso_source(str(iso)) and is_file_source(str(iso)) and not is_folder_source(str(iso))
    assert not is_file_source(str(plain))
    assert not is_file_source("/dev/sr0")


async def test_a_folder_needs_no_device_settle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bd = _disc(tmp_path, "bd")

    def _boom(_p: str) -> None:
        raise AssertionError("the drive-status ioctl must not run for a folder")

    monkeypatch.setattr(disc_probe, "read_drive_status", _boom)
    assert await disc_probe.await_device_ready(str(bd)) is True


async def test_the_fingerprint_probe_skips_a_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """pydvdid and PyCdlib read a device or image, not a folder."""
    bd = _disc(tmp_path, "bd")

    def _boom(*_a: object, **_k: object) -> None:
        raise AssertionError("no optical probe for a folder")

    monkeypatch.setattr(disc_probe, "_compute_crc", _boom)
    probe = await disc_probe.probe_disc(str(bd), bluray=True)
    assert (probe.crc64, probe.thediscdb) == (None, None)


async def test_the_data_scan_classifies_a_folder_by_its_tree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """MakeMKV listed nothing: the folder is still a Blu-ray / DVD (so the job
    can be identified and fails with a clear reason), named after the folder."""

    async def _no_blkid(*_a: object, **_k: object) -> None:
        raise AssertionError("blkid has nothing to read in a folder")

    monkeypatch.setattr(data_module.asyncio, "create_subprocess_exec", _no_blkid)
    bd = await data_module.scan_data(str(_disc(tmp_path, "MirrorMask (2005)")))
    dvd = await data_module.scan_data(str(_disc(tmp_path, "Half Baked", "VIDEO_TS")))
    assert (bd.disc_type, bd.volume_label) == (DiscType.BLURAY, "MirrorMask (2005)")
    assert (dvd.disc_type, dvd.volume_label) == (DiscType.DVD, "Half Baked")
