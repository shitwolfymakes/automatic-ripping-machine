"""What abcde leaves on disk during a rip: its work dir's status file (a line per completed step of each track) and
errors file (a line per failed step), and the WAVs it has written; plus how many WAV bytes a rip will produce."""

import re
from pathlib import Path

# CD audio as WAV: 44.1 kHz, 16-bit, stereo.
CD_WAV_BYTES_PER_SECOND = 44_100 * 2 * 2

# abcde appends `movetrack-NN` once it has moved track NN's file into OUTPUTDIR. The once-per-format
# `movetrack-output-wav` marker does not match.
_MOVED_RE = re.compile(r"^movetrack-(\d+)$", re.MULTILINE)

# abcde appends `readtrack-NN: <reader> returned code N` to its errors file when it cannot read track NN.
_READ_ERROR_RE = re.compile(r"^readtrack-(\d+): (.+)$", re.MULTILINE)


def moved_tracks(status: str) -> set[int]:
    """The track numbers whose file abcde has moved into the output directory, from the status file's text."""
    return {int(n) for n in _MOVED_RE.findall(status)}


def track_errors(errors: str) -> dict[int, str]:
    """The reason abcde gave for each track it could not read, from the errors file's text."""
    return {int(n): reason.strip() for n, reason in _READ_ERROR_RE.findall(errors)}


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


def wav_duration_seconds(size_bytes: int) -> int:
    """The length of a ripped CD track, from its WAV size at the CD audio rate (the header rounds away)."""
    return round(size_bytes / CD_WAV_BYTES_PER_SECOND)
