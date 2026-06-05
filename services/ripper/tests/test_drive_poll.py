"""InsertDetector edge-detection tests.

The detector turns a stream of CDROM_DRIVE_STATUS readings into "start a
rip now" edges. The cases below mirror what real optical drives emit,
captured by probing the dev rig across an eject / manual-reclose cycle:

    DISC_OK -> (eject) -> TRAY_OPEN (~2s flash) -> NOT_READY (tray open)
            -> (manual close) -> NOT_READY (spin-up) -> DISC_OK

A genuine insertion therefore settles as NOT_READY -> DISC_OK, and at the
2s poll interval the TRAY_OPEN flash is frequently missed entirely.
"""

from __future__ import annotations

from arm_ripper.drive_poll import DriveState, InsertDetector


def _feed(detector: InsertDetector, states: list[DriveState]) -> list[bool]:
    return [detector.update(s) for s in states]


def test_boot_with_disc_present_fires_once_then_latches():
    det = InsertDetector()
    # Disc already seated at startup; subsequent steady DISC_OK polls must
    # not re-fire.
    assert _feed(det, [DriveState.DISC_OK] * 4) == [True, False, False, False]


def test_seated_disc_spin_flap_does_not_refire():
    det = InsertDetector()
    # A brief NOT_READY blip (≤ rearm threshold) is the drive re-reading a
    # seated disc, not a swap — must not start a second rip.
    out = _feed(
        det,
        [DriveState.DISC_OK, DriveState.NOT_READY, DriveState.NOT_READY, DriveState.DISC_OK],
    )
    assert out == [True, False, False, False]


def test_tray_open_flash_then_reinsert_refires():
    det = InsertDetector()
    # Flash caught: TRAY_OPEN re-arms immediately, close settles via
    # NOT_READY -> DISC_OK.
    out = _feed(
        det,
        [
            DriveState.DISC_OK,
            DriveState.TRAY_OPEN,
            DriveState.NOT_READY,
            DriveState.NOT_READY,
            DriveState.DISC_OK,
        ],
    )
    assert out[0] is True
    assert out[-1] is True
    assert out[1:-1] == [False, False, False]


def test_missed_tray_flash_sustained_not_ready_refires():
    # The exact real-world failure: at a 2s poll the TRAY_OPEN flash is
    # never sampled, so the swap looks like DISC_OK -> NOT_READY... -> DISC_OK.
    # A NOT_READY run past the rearm threshold must still re-arm.
    det = InsertDetector(not_ready_rearm_polls=3)
    out = _feed(
        det,
        [DriveState.DISC_OK]
        + [DriveState.NOT_READY] * 6  # tray sits open ~12s at a 2s interval
        + [DriveState.DISC_OK],
    )
    assert out[0] is True
    assert out[-1] is True


def test_no_disc_then_disc_refires():
    det = InsertDetector()
    out = _feed(det, [DriveState.DISC_OK, DriveState.NO_DISC, DriveState.DISC_OK])
    assert out == [True, False, True]


def test_no_info_is_neutral():
    # NO_INFO (ioctl busy/unknown, e.g. device held mid-rip) must neither
    # re-arm nor fire on its own.
    det = InsertDetector()
    out = _feed(det, [DriveState.DISC_OK, DriveState.NO_INFO, DriveState.DISC_OK])
    assert out == [True, False, False]


def test_no_info_does_not_reset_partial_not_ready_streak_into_refire():
    # A NO_INFO in the middle of a NOT_READY run resets the streak (it is
    # not a NOT_READY reading); the run must then re-accumulate before
    # re-arming, so a short NOT_READY / NO_INFO flap does not refire.
    det = InsertDetector(not_ready_rearm_polls=3)
    out = _feed(
        det,
        [
            DriveState.DISC_OK,
            DriveState.NOT_READY,
            DriveState.NOT_READY,
            DriveState.NO_INFO,
            DriveState.NOT_READY,
            DriveState.DISC_OK,
        ],
    )
    assert out == [True, False, False, False, False, False]
