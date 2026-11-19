"""What abcde leaves on disk during a rip: its work dir's status file (a line per completed step of each track) and
the WAVs it has written, plus how many WAV bytes a rip will produce."""

import re
from pathlib import Path

# CD audio as WAV: 44.1 kHz, 16-bit, stereo.
CD_WAV_BYTES_PER_SECOND = 44_100 * 2 * 2

# abcde appends `movetrack-NN` once it has moved track NN's file into OUTPUTDIR. The once-per-format
# `movetrack-output-wav` marker does not match.
_MOVED_RE = re.compile(r"^movetrack-(\d+)$", re.MULTILINE)


def moved_tracks(status: str) -> set[int]:
    """The track numbers whose file abcde has moved into the output directory, from the status file's text."""
    return {int(n) for n in _MOVED_RE.findall(status)}


def read_workdir_file(output_dir: Path, name: str) -> str:
    """The text of the file `name` in abcde's work dir for the rip in `output_dir`, or "" when it does not exist yet.

    abcde's work dir is `abcde.<discid>/` under its working directory, which is the output dir.
    """
    for path in output_dir.glob(f"abcde.*/{name}"):
        return path.read_text(errors="replace")
    return ""


def wav_bytes_written(output_dir: Path) -> int:
    """The WAV bytes abcde has written so far: the tracks it moved into `output_dir` plus the one cdparanoia is
    still writing in the work dir."""
    paths = [*output_dir.glob("track*.wav"), *output_dir.glob("abcde.*/track*.wav")]
    return sum(path.stat().st_size for path in paths)


def expected_wav_bytes(durations: list[int | None]) -> int | None:
    """The WAV bytes ripping tracks of these durations (seconds) produces; None when any duration is unknown."""
    if any(seconds is None for seconds in durations):
        return None
    return sum(seconds or 0 for seconds in durations) * CD_WAV_BYTES_PER_SECOND
