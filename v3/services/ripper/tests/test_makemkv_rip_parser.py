"""Parse robot-mode `makemkvcon mkv --robot --progress=-stdout` output."""

from arm_ripper.rip.makemkv_rip import (
    _compose_error,
    _extract_title_index_from_msg5003,
    parse_diagnostic_msg,
    parse_msg_args,
    parse_prgt_title,
    parse_progress_line,
)


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


def test_diagnostic_msg_extracts_known_codes():
    # MSG:1002 — the libmkv "Error while reading input" we saw in prod.
    line = (
        'MSG:1002,32,1,"LIBMKV_TRACE: Exception: Error while reading input",'
        '"LIBMKV_TRACE: %1","Exception: Error while reading input"'
    )
    assert parse_diagnostic_msg(line) == (1002, "LIBMKV_TRACE: Exception: Error while reading input")


def test_diagnostic_msg_extracts_save_failure():
    line = (
        'MSG:5003,0,2,"Failed to save title 2 to file /raw/x.mkv","Failed to save title %1 to file %2","2","/raw/x.mkv"'
    )
    assert parse_diagnostic_msg(line) == (5003, "Failed to save title 2 to file /raw/x.mkv")


def test_diagnostic_msg_skips_unrelated_codes():
    # MSG:3034 (audio stream skipped) is informational; not in the surface set.
    line = 'MSG:3034,0,2,"Audio stream #4 in title #7 looks empty and was skipped",...'
    assert parse_diagnostic_msg(line) is None


def test_diagnostic_msg_skips_non_msg_lines():
    assert parse_diagnostic_msg("PRGV:1,2,4") is None
    assert parse_diagnostic_msg("") is None
    assert parse_diagnostic_msg("nonsense") is None


def test_compose_error_no_diagnostics_passthrough():
    assert _compose_error("makemkvcon failed: exit=1", []) == "makemkvcon failed: exit=1"


def test_compose_error_joins_diagnostics():
    diagnostics = [
        "Region setting of drive does not match disc",
        "LIBMKV_TRACE: Exception: Error while reading input",
        "Failed to save title 2 to file /raw/x.mkv",
    ]
    composed = _compose_error("makemkvcon exited 0 but produced no .mkv", diagnostics)
    assert composed.startswith("makemkvcon exited 0 but produced no .mkv: ")
    assert "Error while reading input" in composed
    assert "Failed to save title 2" in composed


def test_compose_error_dedups_adjacent_repeats():
    # MSG:3032 (region mismatch) is emitted twice during makemkvcon's
    # workaround attempts; the error string shouldn't repeat it.
    diagnostics = ["region mismatch", "region mismatch", "save failed"]
    composed = _compose_error("makemkvcon failed", diagnostics)
    assert composed.count("region mismatch") == 1
    assert "save failed" in composed


# --- per-title attribution from the single-invocation stream -----------------


def test_prgt_title_extracts_index_from_saving_title():
    line = 'PRGT:5018,0,"Saving title #2 to MKV file"'
    assert parse_prgt_title(line) == 2


def test_prgt_title_handles_no_hash_variant():
    # Older MakeMKV builds emit "Saving title 2" without the # prefix.
    line = 'PRGT:5018,0,"Saving title 0 to MKV file"'
    assert parse_prgt_title(line) == 0


def test_prgt_title_returns_none_for_other_milestones():
    # "Reading information" should not be misread as a title-start.
    assert parse_prgt_title('PRGT:5017,0,"Reading information from disc"') is None
    # Generic milestones that mention "title" without "saving" must not match.
    assert parse_prgt_title('PRGT:0,0,"Analyzing title #3"') is None


def test_prgt_title_returns_none_for_non_prgt_lines():
    assert parse_prgt_title("PRGV:1,2,4") is None
    assert parse_prgt_title('MSG:5003,0,2,"Failed to save title 2"') is None
    assert parse_prgt_title("") is None


def test_msg_args_extracts_substitution_values():
    # MSG:5014 — "Saving N titles into directory X". Args after rendered+format:
    # "6", "titles", "file:///raw/job_x"
    line = (
        'MSG:5014,0,3,"Saving 6 titles into directory file:///raw/job_x",'
        '"Saving %1 %2 into directory %3","6","titles","file:///raw/job_x"'
    )
    parsed = parse_msg_args(line)
    assert parsed is not None
    code, args = parsed
    assert code == 5014
    assert args == ["6", "titles", "file:///raw/job_x"]


def test_msg_args_extracts_5003_title_index():
    line = (
        'MSG:5003,0,2,"Failed to save title 2 to file title_t02.mkv",'
        '"Failed to save title %1 to file %2","2","title_t02.mkv"'
    )
    parsed = parse_msg_args(line)
    assert parsed is not None
    code, args = parsed
    assert code == 5003
    assert _extract_title_index_from_msg5003(args) == 2


def test_msg_args_returns_none_for_non_msg_lines():
    assert parse_msg_args("PRGV:1,2,4") is None
    assert parse_msg_args('PRGT:5018,0,"Saving title 0"') is None
    assert parse_msg_args("") is None


def test_msg_args_handles_escaped_quotes_in_args():
    # Filenames with embedded double-quotes are escaped as \"; the
    # parser unescapes them so downstream consumers see clean strings.
    line = (
        r'MSG:5003,0,2,"Failed to save title 1 to file \"weird name\".mkv",'
        r'"Failed to save title %1 to file %2","1","\"weird name\".mkv"'
    )
    parsed = parse_msg_args(line)
    assert parsed is not None
    code, args = parsed
    assert code == 5003
    assert args[0] == "1"
    assert '"weird name".mkv' in args[1]


def test_extract_title_index_returns_none_for_no_int_args():
    # Defensive — if MakeMKV ever changes 5003's arg order so no int
    # appears, the parser must not crash; the dispatcher logs a warn.
    assert _extract_title_index_from_msg5003(["foo", "bar.mkv"]) is None
