import logging
from pathlib import Path

from arm_ripper.drive_resolve import ResolvedDevice, resolve_drive_device

BY_ID = "usb-PIONEER_BD-RW_BDR-S12JX_AAAABBBB000E-0:0"


class Tree:
    """A fake host: /dev, /dev/disk/by-id and /sys/class/block under tmp_path."""

    def __init__(self, tmp_path: Path) -> None:
        self.dev = tmp_path / "dev"
        self.disk = self.dev / "disk"
        self.sysfs = tmp_path / "sys"
        (self.disk / "by-id").mkdir(parents=True)
        (self.sysfs / "class" / "block").mkdir(parents=True)

    def node(self, name: str, major: int, minor: int = 0) -> Path:
        p = self.dev / name
        p.touch()
        d = self.sysfs / "class" / "block" / name
        d.mkdir()
        (d / "dev").write_text(f"{major}:{minor}\n")
        return p

    def link(self, by_id: str, target_name: str) -> None:
        (self.disk / "by-id" / by_id).symlink_to(Path("..") / ".." / target_name)

    def resolve(self, by_id: str | None, hint: str = "/dev/sr0") -> ResolvedDevice | None:
        return resolve_drive_device(by_id, hint, disk_root=self.disk, dev_root=self.dev, sysfs_root=self.sysfs)


def test_by_id_resolves_to_the_linked_optical_node(tmp_path: Path) -> None:
    t = Tree(tmp_path)
    t.node("sr0", 11)
    t.link(BY_ID, "sr0")
    assert t.resolve(BY_ID) == ResolvedDevice(path=str(t.dev / "sr0"), via="by_id")


def test_by_id_follows_a_renumbered_drive(tmp_path: Path) -> None:
    """The point: configured hint says sr0, hardware is now sr2."""
    t = Tree(tmp_path)
    t.node("sr2", 11, 2)
    t.link(BY_ID, "sr2")
    r = t.resolve(BY_ID, hint=str(t.dev / "sr0"))
    assert r is not None and r.path == str(t.dev / "sr2")


def test_by_id_missing_link_is_absent_never_the_hint(tmp_path: Path) -> None:
    t = Tree(tmp_path)
    t.node("sr0", 11)  # hint node exists — must NOT be used
    assert t.resolve(BY_ID, hint=str(t.dev / "sr0")) is None


def test_by_id_dangling_link_is_absent(tmp_path: Path) -> None:
    t = Tree(tmp_path)
    t.link(BY_ID, "sr9")  # no sr9 node
    assert t.resolve(BY_ID) is None


def test_by_id_pointing_above_the_precreated_range_warns(tmp_path: Path, caplog) -> None:
    """udev knows where the drive is; the entrypoint never made that node.
    Silence here reads as "drive unplugged" when it is really a too-low
    ARM_OPTICAL_SR_MAX / ARM_OPTICAL_SG_MAX."""
    caplog.set_level(logging.WARNING, logger="arm_ripper.drive_resolve")
    t = Tree(tmp_path)
    t.link(BY_ID, "sr9")
    assert t.resolve(BY_ID) is None
    warns = [r for r in caplog.records if "is not present under" in r.message]
    assert len(warns) == 1
    assert "sr9" in warns[0].getMessage()
    assert "ARM_OPTICAL_SG_MAX" in warns[0].getMessage()


def test_a_missing_hint_node_does_not_warn(tmp_path: Path, caplog) -> None:
    """The hint path has no udev evidence the drive is anywhere, so a missing
    node there is just "absent" — the poll loop already logs that once."""
    caplog.set_level(logging.WARNING, logger="arm_ripper.drive_resolve")
    t = Tree(tmp_path)
    assert t.resolve(None, hint=str(t.dev / "sr0")) is None
    assert not [r for r in caplog.records if "is not present under" in r.message]


def test_by_id_link_to_a_non_optical_node_is_absent(tmp_path: Path) -> None:
    t = Tree(tmp_path)
    t.node("sda", 8)  # a disk, major 8
    t.link(BY_ID, "sda")
    assert t.resolve(BY_ID) is None


def test_by_id_link_with_no_sysfs_entry_is_absent(tmp_path: Path) -> None:
    t = Tree(tmp_path)
    (t.dev / "sr0").touch()  # node but no /sys/class/block/sr0
    t.link(BY_ID, "sr0")
    assert t.resolve(BY_ID) is None


def test_no_by_id_uses_the_hint_when_it_is_optical(tmp_path: Path) -> None:
    t = Tree(tmp_path)
    t.node("sr0", 11)
    assert t.resolve(None, hint=str(t.dev / "sr0")) == ResolvedDevice(path=str(t.dev / "sr0"), via="hint")


def test_no_by_id_and_missing_hint_is_absent(tmp_path: Path) -> None:
    t = Tree(tmp_path)
    assert t.resolve(None, hint=str(t.dev / "sr0")) is None


def test_no_by_id_and_non_optical_hint_is_absent(tmp_path: Path) -> None:
    t = Tree(tmp_path)
    t.node("sda", 8)
    assert t.resolve(None, hint=str(t.dev / "sda")) is None


def test_missing_by_id_directory_is_absent_not_an_exception(tmp_path: Path) -> None:
    t = Tree(tmp_path)
    (t.disk / "by-id").rmdir()
    assert t.resolve(BY_ID) is None


def test_hint_is_rerooted_under_dev_root(tmp_path: Path) -> None:
    """Only the hint's basename matters; the node is always looked up under dev_root."""
    t = Tree(tmp_path)
    t.node("sr0", 11)
    elsewhere = tmp_path / "elsewhere" / "sr0"  # a hint whose parent is NOT dev_root
    assert t.resolve(None, hint=str(elsewhere)) == ResolvedDevice(path=str(t.dev / "sr0"), via="hint")
