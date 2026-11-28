"""The minimum title length shared by the scan and the rip (#647)."""

from __future__ import annotations

import logging

import pytest
from arm_common.enums import DiscType
from arm_common.schemas import RipStartResponse

import arm_ripper.disc_rip as disc_rip_module
from arm_ripper.makemkv_minlength import DEFAULT_MIN_TITLE_LENGTH_SECONDS, rip_min_length_seconds

_RAISED = "minlength raised from 60s to the configured minimum title length of 120s: the rip may not write a title the scan did not list"


def test_the_fallback_minimum_is_makemkvs_own() -> None:
    assert DEFAULT_MIN_TITLE_LENGTH_SECONDS == 120


@pytest.mark.parametrize(
    ("session", "floor", "expected"),
    [(None, 60, 60), (None, 120, 120), (300, 60, 300), (60, 120, 120), (120, 120, 120)],
)
def test_the_rip_minimum_is_the_session_minimum_never_below_the_floor(
    session: int | None, floor: int, expected: int
) -> None:
    assert rip_min_length_seconds(session, floor) == expected


def test_raising_the_session_minimum_is_logged_once(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="arm_ripper.makemkv_minlength"):
        rip_min_length_seconds(60, 120)
    assert [r.getMessage() for r in caplog.records] == [_RAISED]


@pytest.mark.parametrize(("session", "floor"), [(None, 120), (300, 120), (120, 120)])
def test_a_session_minimum_that_is_kept_is_not_logged(
    caplog: pytest.LogCaptureFixture, session: int | None, floor: int
) -> None:
    with caplog.at_level(logging.INFO, logger="arm_ripper.makemkv_minlength"):
        rip_min_length_seconds(session, floor)
    assert caplog.records == []


def _disc_rip(session: int | None, floor: int | None, default: int = 120) -> disc_rip_module.DiscRip:
    return disc_rip_module.DiscRip(
        backend=None,  # type: ignore[arg-type]
        ws=None,
        ejector=None,  # type: ignore[arg-type]
        device=None,  # type: ignore[arg-type]
        default_min_length_seconds=default,
        output_dir=None,  # type: ignore[arg-type]
        job_id="job_x",
        disc_type=DiscType.BLURAY,
        device_path="/dev/sr0",
        rip_start=RipStartResponse(
            end_on_completion_message=False,
            job_id="job_x",
            rip_preset_id="rpr",
            tracks=[],
            min_length_seconds=session,
            min_title_length_seconds=floor,
        ),
    )


def _disc_rip_minimum(session: int | None, floor: int | None, default: int = 120) -> int:
    return _disc_rip(session, floor, default)._min_length_seconds


@pytest.mark.parametrize(
    ("session", "floor", "expected"),
    [(60, 120, 120), (300, 60, 300), (None, 60, 60), (None, 200, 200)],
)
def test_disc_rip_uses_the_session_minimum_never_below_the_scans(
    session: int | None, floor: int, expected: int
) -> None:
    assert _disc_rip_minimum(session, floor) == expected


def test_disc_rip_falls_back_to_the_host_minimum_from_an_older_backend() -> None:
    assert _disc_rip_minimum(None, None, default=90) == 90
    assert _disc_rip_minimum(60, None, default=90) == 90


def test_disc_rip_hands_the_scans_minimum_to_a_per_title_run() -> None:
    """D36: the per-title command passes the scan's minimum, not the session's, so the title numbers match the scan."""
    assert _disc_rip(300, 60)._options.scan_min_length_seconds == 60
    assert _disc_rip(None, None, default=90)._options.scan_min_length_seconds == 90
