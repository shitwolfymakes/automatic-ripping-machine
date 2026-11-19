"""abcde output: the status file in its work dir, the WAV bytes written so far, and the bytes a rip will write."""

from __future__ import annotations

from pathlib import Path

from arm_ripper.rip.abcde_output import (
    expected_wav_bytes,
    moved_tracks,
    read_workdir_file,
    track_errors,
    wav_bytes_written,
)

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


def test_read_workdir_file_reads_the_file_in_abcdes_work_dir(tmp_path: Path) -> None:
    workdir = tmp_path / "abcde.fc110d12"
    workdir.mkdir()
    (workdir / "status").write_text(_STATUS)
    assert read_workdir_file(tmp_path, "status") == _STATUS


def test_read_workdir_file_is_empty_before_abcde_creates_its_work_dir(tmp_path: Path) -> None:
    assert read_workdir_file(tmp_path, "status") == ""


def test_wav_bytes_written_counts_moved_tracks_and_the_track_being_read(tmp_path: Path) -> None:
    (tmp_path / "track01.wav").write_bytes(b"a" * 1000)
    (tmp_path / "track02.wav").write_bytes(b"b" * 500)
    workdir = tmp_path / "abcde.fc110d12"
    workdir.mkdir()
    (workdir / "track03.wav").write_bytes(b"c" * 200)
    (workdir / "status").write_text(_STATUS)
    assert wav_bytes_written(tmp_path) == 1700


def test_wav_bytes_written_before_any_wav_is_zero(tmp_path: Path) -> None:
    assert wav_bytes_written(tmp_path) == 0


def test_expected_wav_bytes_is_the_cd_audio_rate_times_the_total_length() -> None:
    assert expected_wav_bytes([245, 273]) == 518 * 176_400


def test_expected_wav_bytes_is_unknown_when_any_length_is() -> None:
    assert expected_wav_bytes([245, None]) is None


def test_expected_wav_bytes_of_no_tracks_is_zero() -> None:
    assert expected_wav_bytes([]) == 0


def test_track_errors_maps_each_failed_track_to_its_reason() -> None:
    errors = "readtrack-02: cdparanoia returned code 1\nreadtrack-07: cdparanoia returned code 2\n"
    assert track_errors(errors) == {2: "cdparanoia returned code 1", 7: "cdparanoia returned code 2"}


def test_track_errors_ignores_lines_about_other_steps() -> None:
    assert track_errors("encodetrack-03: lame returned code 1\n") == {}
