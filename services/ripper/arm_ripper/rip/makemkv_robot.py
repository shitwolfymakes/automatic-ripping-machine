"""Parsers for makemkvcon's --robot output lines (PRGV, PRGT, PRGC and MSG)."""

import re

_PRGV_RE = re.compile(r"^PRGV:(\d+),(\d+),(\d+)$")
PRGT_RE = re.compile(r'^PRGT:(\d+),(\d+),"(.*)"$')
# PRGC:5017,N,"Saving to MKV file" fires once per title save start in
# `mkv all` mode. N is the 0-based *output position* (matches the
# `_tNN.mkv` filename suffix and `eligible_source_indexes[N]`).
_PRGC_SAVE_TITLE_RE = re.compile(r'^PRGC:5017,(\d+),"')
_MSG_HEADER_RE = re.compile(r"^MSG:(\d+),(\d+),(\d+),")
QUOTED_ARG_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
# PRGT text for the "now saving title N" milestone. Older MakeMKV builds
# in per-title invocation mode emit "Saving title #N to MKV file"; in
# `mkv all` mode on 1.18.3+ this never fires (PRGC:5017 is the per-title
# signal there). The PRGT path is kept for defensive compatibility.
_PRGT_SAVING_TITLE_RE = re.compile(r"\btitle\s+#?(\d+)\b", re.IGNORECASE)

# MakeMKV codes worth surfacing in disc-level error text.
#  1002 — LIBMKV_TRACE Exception (e.g. "Error while reading input")
#  3032 — drive/disc region mismatch
#  5003 — Failed to save title N to file ... (per-title)
#  5037 — Copy complete. X titles saved, Y failed (final summary)
# Reference: https://github.com/automatic-ripping-machine/automatic-ripping-machine/wiki/MakeMKV-Codes
_DIAGNOSTIC_MSG_CODES = frozenset({1002, 3032, 5003, 5037})

# MSG codes we recognise for per-title outcomes. 5003 carries the
# failure reason; we don't need a success code because file existence
# in the output dir is the source of truth for "title saved ok".
TITLE_FAIL_CODE = 5003


def parse_progress_line(line: str) -> float | None:
    """Return the per-operation fractional progress [0, 1] from a PRGV
    line (`current/max`), or None.

    Used to drive per-title progress when a "Saving title #N" PRGT
    has previously identified the in-flight title. In `mkv all` mode
    the per-title PRGT never fires; see `parse_progress_totals` for
    the disc-overall fallback.
    """
    m = _PRGV_RE.match(line.strip())
    if not m:
        return None
    _current, _total, max_ = (int(g) for g in m.groups())
    if max_ <= 0:
        return None
    return min(1.0, max(0.0, _current / max_))


def parse_progress_totals(line: str) -> tuple[float, float] | None:
    """Return (current/max, total/max) from a PRGV line, or None.

    `current/max` is per-operation progress (resets between titles in
    `mkv ... all` mode); `total/max` is disc-overall progress that
    advances monotonically across the whole rip. The streamer uses the
    `total` channel as the disc-level signal when no per-title PRGT
    has set `current_title`.
    """
    m = _PRGV_RE.match(line.strip())
    if not m:
        return None
    current, total, max_ = (int(g) for g in m.groups())
    if max_ <= 0:
        return None
    cur_frac = min(1.0, max(0.0, current / max_))
    tot_frac = min(1.0, max(0.0, total / max_))
    return cur_frac, tot_frac


def parse_msg_args(line: str) -> tuple[int, list[str]] | None:
    """Parse a MSG: line into (code, args). args is the list of trailing
    quoted strings *after* the rendered text and format string — i.e.
    the substitution arguments. Returns None if the line isn't a MSG.
    """
    header = _MSG_HEADER_RE.match(line.strip())
    if not header:
        return None
    code = int(header.group(1))
    quoted = [m.group(1) for m in QUOTED_ARG_RE.finditer(line)]
    # args[0] = rendered text, args[1] = format string, args[2:] = substitution values.
    args = [a.replace('\\"', '"') for a in quoted[2:]]
    return code, args


def parse_diagnostic_msg(line: str) -> tuple[int, str] | None:
    """If `line` is a MSG: line whose code is in _DIAGNOSTIC_MSG_CODES,
    return (code, rendered_text). Otherwise None.

    Used by `compose_error` to surface MakeMKV-side reasons when the
    overall rip exits non-zero (or exits 0 but produces no files).
    """
    header = _MSG_HEADER_RE.match(line.strip())
    if not header:
        return None
    code = int(header.group(1))
    if code not in _DIAGNOSTIC_MSG_CODES:
        return None
    quoted = QUOTED_ARG_RE.search(line)
    if quoted is None:
        return None
    text = quoted.group(1).replace('\\"', '"')
    return code, text


def parse_prgt_title(line: str) -> int | None:
    """If `line` is a PRGT whose text announces "Saving title N to
    MKV file", return N. Otherwise None.

    Defensive — empirically silent in `mkv all` mode on MakeMKV 1.18.3
    (PRGC:5017 is the actual per-title signal there; see
    `parse_prgc_save_position`). Kept for older versions / per-title
    invocation modes that may still emit this milestone.
    """
    m = PRGT_RE.match(line.strip())
    if not m:
        return None
    text = m.group(3)
    # Filter on "saving" to avoid matching e.g. "Reading information for title 3".
    if "saving" not in text.lower():
        return None
    title_match = _PRGT_SAVING_TITLE_RE.search(text)
    if not title_match:
        return None
    return int(title_match.group(1))


def parse_prgc_save_position(line: str) -> int | None:
    """If `line` is a PRGC:5017 ("Saving to MKV file") line, return the
    0-based output position from its second field. Otherwise None.

    In `mkv all` mode MakeMKV emits one PRGC:5017 per title save start,
    with the second field stepping 0, 1, 2, … through the eligible
    titles in rip order. That position matches the `_tNN.mkv` filename
    suffix and indexes into the dispatcher's `eligible_source_indexes`.
    """
    m = _PRGC_SAVE_TITLE_RE.match(line.strip())
    if not m:
        return None
    return int(m.group(1))


def extract_title_index_from_msg5003(args: list[str]) -> int | None:
    """MSG:5003 args vary slightly across MakeMKV versions but always
    include the title index as one of the integer-string arguments.
    Heuristic: take the first arg that parses cleanly as an int."""
    for a in args:
        try:
            return int(a)
        except ValueError:
            continue
    return None
