"""The rip settings resolvers: a drive's own value over the global, NULL on the drive follows the global."""

from __future__ import annotations

import pytest

from arm_backend.rip_settings import resolve_end_on_completion
from arm_common import Config, Drive


def _drive(value: bool | None) -> Drive:
    return Drive(id="drv_x", hostname="h", device_path="/dev/sr0", rip_end_on_completion_message=value)


@pytest.mark.parametrize(
    ("global_value", "drive_value", "expected"),
    [
        (False, None, False),
        (True, None, True),
        (False, True, True),
        (True, False, False),
        (True, True, True),
        (False, False, False),
    ],
)
def test_a_drive_override_wins_and_null_follows_the_global(
    global_value: bool, drive_value: bool | None, expected: bool
) -> None:
    cfg = Config(id=1, rip_end_on_completion_message=global_value)
    assert resolve_end_on_completion(cfg, _drive(drive_value)) is expected


def test_a_job_without_a_drive_follows_the_global() -> None:
    assert resolve_end_on_completion(Config(id=1, rip_end_on_completion_message=True), None) is True
    assert resolve_end_on_completion(Config(id=1, rip_end_on_completion_message=False), None) is False


def test_no_config_row_reads_as_the_shipped_default_off() -> None:
    assert resolve_end_on_completion(None, None) is False
    assert resolve_end_on_completion(None, _drive(True)) is True
