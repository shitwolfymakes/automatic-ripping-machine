from arm_ripper.drive_handle import DriveHandle


def test_starts_absent_by_default() -> None:
    h = DriveHandle()
    assert h.current is None
    assert h.absent is True


def test_fixed_is_present_and_stable() -> None:
    h = DriveHandle.fixed("/tmp/x.iso")
    assert h.current == "/tmp/x.iso"
    assert h.absent is False


def test_set_reports_change_and_no_change() -> None:
    h = DriveHandle("/dev/sr0")
    assert h.set("/dev/sr0") is False
    assert h.set("/dev/sr2") is True
    assert h.current == "/dev/sr2"
    assert h.set(None) is True
    assert h.absent is True
    assert h.set(None) is False


def test_consumers_share_one_view() -> None:
    """The reason this class exists: two readers, one truth."""
    h = DriveHandle("/dev/sr0")
    reader_a = h
    reader_b = h
    h.set("/dev/sr1")
    assert reader_a.current == reader_b.current == "/dev/sr1"
