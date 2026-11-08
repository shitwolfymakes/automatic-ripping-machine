import pytest

from arm_backend.metadata.years import year_from, year_from_any


@pytest.mark.parametrize(
    ("text", "expected"),
    [("1973-03-01", 1973), ("2010–2015", 2010), ("1973", 1973), ("N/A", None), ("197", 197), ("", None)],
)
def test_year_from(text: str, expected: int | None) -> None:
    assert year_from(text) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(1999, 1999), ("1999-01-01", 1999), ("abc", None), (None, None), (19.5, None)],
)
def test_year_from_any(value: object, expected: int | None) -> None:
    assert year_from_any(value) == expected
