---
name: project_ripper_insert_detection
description: How the ripper detects disc insertion (poll loop) and the drive quirk that shaped it
metadata:
  type: project
---

The v3 ripper has **no udev**; insertion is detected by `poll_loop` in
`services/ripper/arm_ripper/main.py`, which reads `CDROM_DRIVE_STATUS`
(ioctl) every `POLL_INTERVAL_SECONDS` (default 2s) and calls
`JobController.handle_disc_inserted`, which queries the backend live
(`GET /api/ripper/config`, no caching) for `auto_rip_on_insert`.

Drive-behavior gotcha (dev rig, observed via eject/reclose probe): a real
optical drive only reports `TRAY_OPEN` for a ~2s flash on open, then sits
in `NOT_READY` for as long as the tray is open, and again during spin-up —
so a genuine insertion settles as `NOT_READY -> DISC_OK`, and at the 2s
poll the `TRAY_OPEN` flash is routinely missed. The dev drive also **cannot
self-close** (`eject -t` returns rc=1); the tray is pushed shut by hand.

The original edge `last_state not in (DISC_OK, NOT_READY)` therefore
swallowed *every* real insertion (always preceded by NOT_READY). Fixed
with `InsertDetector` in `drive_poll.py`: latch on fire, re-arm on
NO_DISC/TRAY_OPEN **or** a sustained NOT_READY run (default 3 polls).
Tests in `tests/test_drive_poll.py`.
