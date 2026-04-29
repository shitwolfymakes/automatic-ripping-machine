"""Parse robot-mode `makemkvcon mkv --robot --progress=-stdout` output."""

from arm_ripper.rip.makemkv_rip import parse_progress_line


def test_progress_line_parses_to_fraction():
    assert parse_progress_line("PRGV:5000,7500,10000") == 0.5


def test_progress_line_clamps_to_one():
    # current > max can happen when MakeMKV emits the final frame with current==max+epsilon.
    assert parse_progress_line("PRGV:10001,10000,10000") == 1.0


def test_progress_line_handles_zero_max():
    assert parse_progress_line("PRGV:0,0,0") is None


def test_non_progress_lines_return_none():
    assert parse_progress_line("MSG:5021,260,1,...") is None
    assert parse_progress_line('PRGT:5018,1,"Saving to file"') is None
    assert parse_progress_line("") is None
    assert parse_progress_line("garbage") is None


def test_whitespace_tolerated():
    assert parse_progress_line("  PRGV:1,2,4  ") == 0.25
