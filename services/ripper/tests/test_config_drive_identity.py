import os

os.environ.setdefault("ARM_DRIVE_DEV", "/dev/sr0")
os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

import pytest
from pydantic import ValidationError

from arm_ripper.config import Settings  # noqa: E402


def test_drive_identity_defaults() -> None:
    s = Settings()
    assert s.ARM_DRIVE_ID == "drv_test"
    assert s.ARM_DRIVE_BY_ID is None
    assert s.ARM_HOST_DISK_ROOT == "/host-disk"


def test_drive_id_is_required(monkeypatch) -> None:
    monkeypatch.delenv("ARM_DRIVE_ID")
    with pytest.raises(ValidationError):
        Settings()


def test_drive_serial_setting_is_gone() -> None:
    assert "ARM_DRIVE_SERIAL" not in Settings.model_fields


def test_drive_identity_from_env(monkeypatch) -> None:
    monkeypatch.setenv("ARM_DRIVE_ID", "drv_01ABC")
    monkeypatch.setenv("ARM_DRIVE_BY_ID", "usb-PIONEER_BD-RW_BDR-S12JX_AAAABBBB000E-0:0")
    monkeypatch.setenv("ARM_HOST_DISK_ROOT", "/mnt/hd")
    s = Settings()
    assert s.ARM_DRIVE_ID == "drv_01ABC"
    assert s.ARM_DRIVE_BY_ID == "usb-PIONEER_BD-RW_BDR-S12JX_AAAABBBB000E-0:0"
    assert s.ARM_HOST_DISK_ROOT == "/mnt/hd"
