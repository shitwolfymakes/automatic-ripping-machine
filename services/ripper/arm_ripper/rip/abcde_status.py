"""abcde's status file: the log abcde appends a line to as it completes each step of each track."""

import re
from pathlib import Path

# abcde appends `movetrack-NN` once it has moved track NN's file into OUTPUTDIR. The once-per-format
# `movetrack-output-wav` marker does not match.
_MOVED_RE = re.compile(r"^movetrack-(\d+)$", re.MULTILINE)


def moved_tracks(status: str) -> set[int]:
    """The track numbers whose file abcde has moved into the output directory, from the status file's text."""
    return {int(n) for n in _MOVED_RE.findall(status)}


def read_status(output_dir: Path) -> str:
    """The text of abcde's status file for the rip in `output_dir`, or "" before abcde has created it.

    abcde keeps the file in its work dir, `abcde.<discid>/status`, under its working directory, which is
    the output dir.
    """
    for path in output_dir.glob("abcde.*/status"):
        return path.read_text(errors="replace")
    return ""
