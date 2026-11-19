"""abcde status file: which tracks abcde has moved into place, and where the file lives."""

from __future__ import annotations

from pathlib import Path

from arm_ripper.rip.abcde_status import moved_tracks, read_status

# The head of a real abcde 2.9.3 status file, taken mid-rip on an 18-track CD.
_STATUS = """abcde-version=2.9.3
cdparanoia-audio-tracks=18
readtrack-01
encodetrack-01
movetrack-01
movetrack-output-wav
readtrack-02
encodetracklocation-%local1%=02
movetrack-02
readtrack-03
"""


def test_moved_tracks_lists_each_track_abcde_moved_into_place() -> None:
    assert moved_tracks(_STATUS) == {1, 2}


def test_moved_tracks_ignores_the_per_format_marker_and_other_steps() -> None:
    assert moved_tracks("movetrack-output-wav\nreadtrack-04\nencodetrack-04\n") == set()


def test_moved_tracks_of_an_empty_status_is_empty() -> None:
    assert moved_tracks("") == set()


def test_read_status_reads_the_file_in_abcdes_work_dir(tmp_path: Path) -> None:
    workdir = tmp_path / "abcde.fc110d12"
    workdir.mkdir()
    (workdir / "status").write_text(_STATUS)
    assert read_status(tmp_path) == _STATUS


def test_read_status_is_empty_before_abcde_creates_its_work_dir(tmp_path: Path) -> None:
    assert read_status(tmp_path) == ""
