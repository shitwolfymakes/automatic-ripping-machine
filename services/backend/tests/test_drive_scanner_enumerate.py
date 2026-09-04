"""enumerate_optical over a fixture /sys + /dev/disk tree — no real hardware, no privilege."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from arm_backend.drive_scanner import ScannedDrive, enumerate_optical, parse_short_serial  # noqa: E402

BY_ID = "usb-PIONEER_BD-RW_BDR-S12JX_AAAABBBB000E-0:0"


class Tree:
    """Mimics the real layout: /sys/class/block/srN -> ../../devices/.../hostH/.../block/srN,
    with srN/device -> the SCSI device dir holding vendor/model/scsi_generic/."""

    def __init__(self, tmp_path: Path) -> None:
        self.sysfs = tmp_path / "sys"
        self.disk = tmp_path / "dev" / "disk"
        (self.sysfs / "class" / "block").mkdir(parents=True)
        (self.disk / "by-id").mkdir(parents=True)

    def drive(
        self,
        node: str = "sr0",
        *,
        minor: int = 0,
        major: int = 11,
        port: str = "pci0000:00/0000:00:14.0/usb4/4-1/4-1:1.0",
        host: int = 0,
        vendor: str = "PIONEER ",
        model: str = "BD-RW  BDR-S12JX",
        sg: str | None = "sg0",
        by_id: str | None = BY_ID,
    ) -> None:
        dev_dir = self.sysfs / "devices" / port / f"host{host}" / f"target{host}:0:0" / f"{host}:0:0:0"
        dev_dir.mkdir(parents=True, exist_ok=True)
        if not (dev_dir / "vendor").exists():
            (dev_dir / "vendor").write_text(vendor + "\n")
        if not (dev_dir / "model").exists():
            (dev_dir / "model").write_text(model + "\n")
        if sg:
            (dev_dir / "scsi_generic" / sg).mkdir(parents=True, exist_ok=True)
        blk = dev_dir / "block" / node
        blk.mkdir(parents=True)
        (blk / "dev").write_text(f"{major}:{minor}\n")
        (blk / "device").symlink_to(Path("..") / "..")
        (self.sysfs / "class" / "block" / node).symlink_to(blk)
        if by_id:
            # Create the actual device file that the by-id link will point to
            (self.disk.parent / node).touch()
            (self.disk / "by-id" / by_id).symlink_to(Path("..") / ".." / node)

    def scan(self) -> list[ScannedDrive]:
        return enumerate_optical(sysfs_root=self.sysfs, disk_root=self.disk)


def test_one_usb_drive_is_fully_described(tmp_path: Path) -> None:
    t = Tree(tmp_path)
    t.drive()
    [d] = t.scan()
    assert d.node == "sr0" and d.device_path == "/dev/sr0"
    assert (d.major, d.minor) == (11, 0)
    assert d.vendor == "PIONEER" and d.model == "BD-RW  BDR-S12JX"  # stripped, inner spaces kept
    assert d.sg == "sg0"
    assert d.by_id_name == BY_ID and d.serial == "AAAABBBB000E"
    assert d.sysfs_port == str(t.sysfs / "devices" / "pci0000:00/0000:00:14.0/usb4/4-1/4-1:1.0")


def test_two_drives_sorted_by_node(tmp_path: Path) -> None:
    t = Tree(tmp_path)
    t.drive(
        "sr1",
        minor=1,
        host=1,
        port="pci0000:00/0000:00:17.0/ata3",
        by_id="ata-HL-DT-ST_BD-RE_WH16NS40_K1234567-0:0",
        sg="sg2",
    )
    t.drive("sr0")
    assert [d.node for d in t.scan()] == ["sr0", "sr1"]


def test_port_identity_when_no_by_id_link(tmp_path: Path) -> None:
    t = Tree(tmp_path)
    t.drive(by_id=None)
    [d] = t.scan()
    assert d.by_id_name is None and d.serial is None
    assert d.sysfs_port.endswith("usb4/4-1/4-1:1.0")


def test_sysfs_port_is_stable_across_host_renumbering(tmp_path: Path) -> None:
    """Replug: the kernel hands out host1 instead of host0; the port must not change."""
    a = Tree(tmp_path / "a")
    a.drive(host=0)
    b = Tree(tmp_path / "b")
    b.drive(host=1)
    assert a.scan()[0].sysfs_port.replace(str(a.sysfs), "") == b.scan()[0].sysfs_port.replace(str(b.sysfs), "")


def test_non_optical_block_devices_are_ignored(tmp_path: Path) -> None:
    t = Tree(tmp_path)
    t.drive("sda", major=8, by_id="ata-SAMSUNG_SSD_S1234-0:0", sg="sg1")  # a disk
    t.drive("sr0")
    assert [d.node for d in t.scan()] == ["sr0"]


def test_dangling_by_id_link_is_not_attributed(tmp_path: Path) -> None:
    t = Tree(tmp_path)
    t.drive(by_id=None)
    (t.disk / "by-id" / "usb-GHOST_0000-0:0").symlink_to(Path("..") / ".." / "sr9")
    [d] = t.scan()
    assert d.by_id_name is None


def test_missing_sysfs_or_disk_root_yields_empty_not_error(tmp_path: Path) -> None:
    assert enumerate_optical(sysfs_root=tmp_path / "nope", disk_root=tmp_path / "nope2") == []


def test_parse_short_serial() -> None:
    assert parse_short_serial("usb-PIONEER_BD-RW_BDR-S12JX_AAAABBBB000E-0:0") == "AAAABBBB000E"
    assert parse_short_serial("ata-HL-DT-ST_BD-RE_WH16NS40_K1234567") == "K1234567"  # no lun suffix
    assert parse_short_serial("usb-NOUNDERSCORE-0:0") is None


def test_dev_file_missing(tmp_path: Path) -> None:
    """dev file missing or malformed is skipped."""
    t = Tree(tmp_path)
    t.drive()
    # Remove the dev file to trigger the "dev is None" path
    (t.sysfs / "class" / "block" / "sr0" / "dev").unlink()
    assert t.scan() == []


def test_dev_file_malformed(tmp_path: Path) -> None:
    """dev file without ':' is skipped."""
    t = Tree(tmp_path)
    t.drive()
    (t.sysfs / "class" / "block" / "sr0" / "dev").write_text("notadevnum\n")
    assert t.scan() == []


def test_wrong_major_device_ignored(tmp_path: Path) -> None:
    """Block device with wrong major number is ignored."""
    t = Tree(tmp_path)
    t.drive(major=66)  # Not SCSI_CDROM_MAJOR (11)
    assert t.scan() == []


def test_no_sg_pairing(tmp_path: Path) -> None:
    """Drive with no scsi_generic pairing sets sg=None."""
    t = Tree(tmp_path)
    t.drive(sg=None)
    [d] = t.scan()
    assert d.sg is None


def test_vendor_model_missing(tmp_path: Path) -> None:
    """vendor/model files missing result in None fields."""
    t = Tree(tmp_path)
    t.drive()
    # The device symlink points to ../.. from block/sr0
    # which is the {host}:0:0:0 directory where vendor/model live
    vendor_path = (
        t.sysfs
        / "devices"
        / "pci0000:00/0000:00:14.0/usb4/4-1/4-1:1.0"
        / "host0"
        / "target0:0:0"
        / "0:0:0:0"
        / "vendor"
    )
    model_path = (
        t.sysfs / "devices" / "pci0000:00/0000:00:14.0/usb4/4-1/4-1:1.0" / "host0" / "target0:0:0" / "0:0:0:0" / "model"
    )
    vendor_path.unlink()
    model_path.unlink()
    [d] = t.scan()
    assert d.vendor is None and d.model is None


def test_sysfs_port_no_host_component(tmp_path: Path) -> None:
    """sysfs_port without 'hostN' component still cuts at block dir."""
    t = Tree(tmp_path)
    # Create a simple path without hostN
    dev_dir = t.sysfs / "devices" / "virtual" / "block" / "sr0"
    dev_dir.mkdir(parents=True)
    (dev_dir / "dev").write_text("11:0\n")
    (dev_dir / "device").symlink_to(Path("..") / "..")
    (dev_dir / "vendor").write_text("VIRTUAL\n")
    (dev_dir / "model").write_text("DRIVE\n")
    (t.sysfs / "class" / "block" / "sr0").symlink_to(dev_dir)
    [d] = t.scan()
    # Should cut before /block/
    assert d.sysfs_port.endswith("/virtual")


def test_by_id_links_with_broken_readlink(tmp_path: Path) -> None:
    """by_id links with broken readlink are skipped gracefully."""
    t = Tree(tmp_path)
    # Create a broken symlink in by-id
    (t.disk / "by-id" / "broken-link").symlink_to("../../nonexistent")
    # Regular drive should still work
    t.drive()
    [d] = t.scan()
    assert d.node == "sr0"
