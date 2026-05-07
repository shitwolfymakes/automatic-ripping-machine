"""HandBrakeCLI text-mode progress parser."""

from __future__ import annotations

import re

from arm_transcode.handbrake import _PROGRESS_LINE_RE, _parse_eta


def _match(line: str) -> re.Match[str] | None:
    return _PROGRESS_LINE_RE.search(line)


def test_full_line_with_eta() -> None:
    m = _match("Encoding: task 1 of 1, 47.30 % (45.67 fps, avg 23.45 fps, ETA 00h12m34s)")
    assert m is not None
    assert int(round(float(m.group("pct")))) == 47
    assert _parse_eta(m) == 12 * 60 + 34
    assert m.group("pass") == "1"


def test_zero_progress_no_eta_yet() -> None:
    m = _match("Encoding: task 1 of 1, 0.00 %")
    assert m is not None
    assert int(round(float(m.group("pct")))) == 0
    assert _parse_eta(m) is None


def test_one_hundred_percent() -> None:
    m = _match("Encoding: task 1 of 1, 100.00 % (45.67 fps, avg 23.45 fps, ETA 00h00m00s)")
    assert m is not None
    assert int(round(float(m.group("pct")))) == 100
    assert _parse_eta(m) == 0


def test_eta_with_hours() -> None:
    m = _match("Encoding: task 2 of 3, 5.20 % (12.00 fps, avg 12.00 fps, ETA 01h45m30s)")
    assert m is not None
    assert _parse_eta(m) == 3600 + 45 * 60 + 30


def test_does_not_match_title_scan_line() -> None:
    """`Scanning title 1 of 1, 70.00 %` is title-scan progress, not encode
    progress. Anchoring on `task N of M` skips it cleanly."""
    assert _match("Scanning title 1 of 1, 70.00 %") is None


def test_does_not_match_unrelated_line() -> None:
    assert _match("HandBrake 1.6.1 (2023012900) - Linux x86_64") is None
    assert _match("Cannot load libnvidia-encode.so.1") is None
    assert _match("Muxing: this may take a while...") is None


def test_pass_index_is_extracted() -> None:
    """Two-pass encodes report `task 1 of 2` then `task 2 of 2`."""
    m1 = _match("Encoding: task 1 of 2, 50.00 % (... ETA 00h05m00s)")
    m2 = _match("Encoding: task 2 of 2, 10.00 % (... ETA 00h08m00s)")
    assert m1 is not None and m1.group("pass") == "1"
    assert m2 is not None and m2.group("pass") == "2"
