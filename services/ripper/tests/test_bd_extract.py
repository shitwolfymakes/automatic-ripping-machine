"""bd_extract: the 7-Zip extraction and the metadata listing, through a fake 7-Zip on PATH."""

from __future__ import annotations

from pathlib import Path

import pytest
from bd_builders import fake_7zz

from arm_ripper.scan import bd_extract


async def test_extract_files_passes_every_pattern(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    argv = tmp_path / "argv"
    fake_7zz(tmp_path, monkeypatch, f'printf "%s\\n" "$@" > {argv}')
    assert await bd_extract.extract_files("/dev/sr0", tmp_path / "out", 5, ["a/*.x", "b/*.y"]) == bd_extract.OK
    lines = argv.read_text().splitlines()
    assert lines[0] == "x"
    assert lines[-4:] == ["--", "/dev/sr0", "a/*.x", "b/*.y"]


async def test_list_file_sizes_parses_the_listing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    listing = tmp_path / "listing.txt"
    listing.write_text(
        "Path = BDMV/STREAM/00001.M2TS\nFolder = -\nSize = 11\n\n"
        "Path = BDMV/STREAM/SSIF\nFolder = +\nSize = 0\n\n"
        "Path = BDMV/STREAM/00002.m2ts\nFolder = -\nSize = 22\n\n"
    )
    fake_7zz(tmp_path, monkeypatch, f"/bin/cat {listing}")
    assert await bd_extract.list_file_sizes("/dev/sr0", 5, "BDMV/STREAM/*.m2ts") == (
        {"00001.m2ts": 11, "00002.m2ts": 22},
        bd_extract.OK,
    )


async def test_list_file_sizes_without_7z(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    assert await bd_extract.list_file_sizes("/dev/sr0", 5, "x") == ({}, bd_extract.UNAVAILABLE)


async def test_list_file_sizes_timeout_is_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_7zz(tmp_path, monkeypatch, "exec /bin/sleep 5")
    assert await bd_extract.list_file_sizes("/dev/sr0", 0.2, "x") == ({}, bd_extract.TIMEOUT)
