"""Pure formatters shared by the services' log messages."""

from __future__ import annotations

import pytest

from arm_common.log_format import elapsed, human_duration, human_size, quarter_crossed


@pytest.mark.parametrize(
    ("value", "expected"),
    [(43107500, "41.1 MB"), (9730283713, "9.1 GB"), (512, "512 B"), (2048, "2.0 KB"), (None, "unknown size")],
)
def test_human_size(value: int | None, expected: str) -> None:
    assert human_size(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(244, "4:04"), (3093, "51:33"), (3723, "1:02:03"), (None, "unknown length")],
)
def test_human_duration(value: float | None, expected: str) -> None:
    assert human_duration(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(402, "6m42s"), (59, "59s"), (3725, "1h02m05s")],
)
def test_elapsed(value: float, expected: str) -> None:
    assert elapsed(value) == expected


@pytest.mark.parametrize(
    ("previous", "current", "expected"),
    [(None, 10, None), (10, 30, 25), (10, 80, 75), (30, 30, None), (99, 100, 100)],
)
def test_quarter_crossed(previous: float | None, current: float, expected: int | None) -> None:
    assert quarter_crossed(previous, current) == expected
