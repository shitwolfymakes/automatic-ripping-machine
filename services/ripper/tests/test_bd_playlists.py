"""BD playlist reader: MPLS parsing from in-memory bytes, disc reads through a fake 7-Zip on PATH."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import struct
from pathlib import Path

import pytest
from arm_common.schemas import BdPlaylist

from arm_ripper.scan import bd_playlists, playlist_extract
from arm_ripper.scan.bd_playlists import parse_mpls, parse_playlists, read_mpls_files, scan_playlists

TICKS = 45000


def _item(clip: str, seconds: float, *, angles: int = 1, start: int = 0) -> bytes:
    body = clip.encode().ljust(5, b"0") + b"M2TS"
    body += struct.pack(">H", 0x10 if angles > 1 else 0x01)  # multi-angle bit / connection_condition
    body += b"\x00"  # ref_to_STC_id
    body += struct.pack(">II", start, start + int(seconds * TICKS))
    body += b"\x00" * 8 + b"\x00" + b"\x00" + b"\x00\x00"  # UO mask, flags, still mode, still time
    if angles > 1:
        body += bytes([angles, 0])
        for n in range(angles - 1):
            body += f"{n + 90:05d}".encode() + b"M2TS" + b"\x00"
    return struct.pack(">H", len(body)) + body


def mpls(items: list[bytes], marks: list[int] | None = None) -> bytes:
    """A minimal MPLS: header, PlayList of `items`, PlayListMark with mark types `marks`."""
    play_list = struct.pack(">HHH", 0, len(items), 0) + b"".join(items)
    play_list = struct.pack(">I", len(play_list)) + play_list
    mark_types = marks or []
    mark_block = struct.pack(">H", len(mark_types))
    for t in mark_types:
        mark_block += bytes([0, t]) + struct.pack(">HIHI", 0, 0, 0xFFFF, 0)
    mark_block = struct.pack(">I", len(mark_block)) + mark_block
    play_list_start = 40
    mark_start = play_list_start + len(play_list)
    header = b"MPLS0200" + struct.pack(">III", play_list_start, mark_start, 0)
    return header.ljust(play_list_start, b"\x00") + play_list + mark_block


# --- parse_mpls -----------------------------------------------------------------


def test_parse_durations_clip_order_and_chapters() -> None:
    data = mpls([_item("00005", 600.0), _item("00002", 90.5, start=1000)], marks=[1, 2, 1, 1])
    playlist = parse_mpls(data, "00202.mpls")
    assert playlist == BdPlaylist(
        name="00202.mpls",
        clips=[5, 2],
        clip_seconds=[600.0, 90.5],
        duration_seconds=round(690.5),
        chapter_count=3,
        multi_angle=False,
    )


def test_parse_multi_angle_records_primary_clip_only() -> None:
    data = mpls([_item("00010", 100.0, angles=3), _item("00011", 50.0)])
    playlist = parse_mpls(data, "00001.mpls")
    assert playlist is not None
    assert playlist.clips == [10, 11]
    assert playlist.multi_angle is True


def test_parse_reversed_times_count_as_zero() -> None:
    item = bytearray(_item("00001", 10.0))
    item[14:22] = struct.pack(">II", 900, 100)
    playlist = parse_mpls(mpls([bytes(item)]), "00001.mpls")
    assert playlist is not None
    assert playlist.clip_seconds == [0.0]


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"NOPE" + b"\x00" * 60,
        mpls([_item("00001", 1.0)])[:30],  # cut inside the header offsets' target
        mpls([_item("00001", 1.0)])[:60],  # cut inside the PlayItem
        mpls([_item("00001", 1.0)], marks=[1])[:-13],  # cut inside the marks
        mpls([]),  # no PlayItems
        mpls([_item("ABCDE", 1.0)]),  # non-numeric clip name
    ],
)
def test_parse_garbage_or_truncated_is_none(data: bytes) -> None:
    assert parse_mpls(data, "00001.mpls") is None


def test_parse_non_ascii_clip_name_is_none() -> None:
    item = bytearray(_item("00001", 1.0))
    item[2] = 0xFF
    assert parse_mpls(mpls([bytes(item)]), "00001.mpls") is None


# --- fake 7-Zip on PATH ---------------------------------------------------------------


def _fake_7zz(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str) -> Path:
    """A `7zz` shell script as the only executable on PATH; `body` runs with $OUT = the -o directory."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "7zz"
    script.write_text(
        '#!/bin/sh\nfor a in "$@"; do case "$a" in -o*) OUT="${a#-o}";; esac; done\n' + body + "\n",
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    return bin_dir


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


async def test_hung_read_is_killed_and_reaped_before_returning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    pid_file = tmp_path / "pid"
    _fake_7zz(tmp_path, monkeypatch, f"echo $$ > {pid_file}\nexec /bin/sleep 5")
    monkeypatch.setattr(bd_playlists, "PLAYLIST_TIMEOUT_SECONDS", 0.3)
    image = tmp_path / "disc.iso"
    image.write_bytes(b"x")
    with caplog.at_level(logging.INFO, logger="arm_ripper.scan.bd_playlists"):
        assert await scan_playlists(str(image)) == []
    pid = int(pid_file.read_text())
    try:
        assert not _alive(pid), "the read process is still running (or unreaped) after scan_playlists returned"
    finally:
        if _alive(pid):
            os.kill(pid, signal.SIGKILL)
    assert any("count=0" in r.getMessage() and "reason=timeout" in r.getMessage() for r in caplog.records)


async def test_event_loop_keeps_running_and_no_executor_thread_reads_the_drive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "src"
    (src / "BDMV" / "PLAYLIST").mkdir(parents=True)
    (src / "BDMV" / "PLAYLIST" / "00001.mpls").write_bytes(mpls([_item("00002", 30.0)]))
    _fake_7zz(tmp_path, monkeypatch, f'/bin/sleep 0.4\n/bin/cp -r {src}/. "$OUT"/')
    image = tmp_path / "disc.iso"
    image.write_bytes(b"x")
    loop = asyncio.get_running_loop()
    offloaded: list[object] = []
    real = loop.run_in_executor
    monkeypatch.setattr(loop, "run_in_executor", lambda *a, **k: (offloaded.append(a), real(*a, **k))[1])
    ticks = 0

    async def _ticker() -> None:
        nonlocal ticks
        while True:
            await asyncio.sleep(0.02)
            ticks += 1

    task = asyncio.create_task(_ticker())
    try:
        playlists = await scan_playlists(str(image))
    finally:
        task.cancel()
    assert [p.name for p in playlists] == ["00001.mpls"]
    assert ticks >= 10  # the loop ran during the ~0.4 s read
    assert offloaded == []  # the drive is read by a killable subprocess, not an uninterruptible thread


def _copy_into_out(tmp_path: Path, files: dict[str, bytes]) -> str:
    """Shell body that lays `files` out under $OUT/BDMV/PLAYLIST like `7zz x ... BDMV/PLAYLIST/*.mpls` does."""
    src = tmp_path / "src" / "BDMV" / "PLAYLIST"
    src.mkdir(parents=True)
    for name, data in files.items():
        (src / name).write_bytes(data)
    return f'/bin/cp -r {tmp_path / "src"}/. "$OUT"/'


async def test_scan_extracts_through_7z_and_parses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    body = _copy_into_out(
        tmp_path,
        {
            "00800.MPLS": mpls([_item("00001", 120.0)], marks=[1]),
            "00001.mpls": mpls([_item("00002", 30.0)]),
            "notes.txt": b"not a playlist",
            "00003.mpls": b"garbage",
        },
    )
    _fake_7zz(tmp_path, monkeypatch, body)
    playlists = await scan_playlists("/dev/sr0")
    assert [p.name for p in playlists] == ["00001.mpls", "00800.mpls"]
    assert playlists[1].chapter_count == 1
    assert playlists[1].duration_seconds == 120


async def test_scan_passes_device_and_pattern_to_7z(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    argv = tmp_path / "argv"
    _fake_7zz(tmp_path, monkeypatch, f'printf "%s\\n" "$@" > {argv}')
    await scan_playlists("/dev/sr0")
    lines = argv.read_text().splitlines()
    assert lines[0] == "x"
    assert lines[-3:] == ["--", "/dev/sr0", "BDMV/PLAYLIST/*.mpls"]


async def test_scan_disc_without_bdmv_is_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_7zz(tmp_path, monkeypatch, "exit 1")  # 7z warns "no files to process"
    assert await scan_playlists("/dev/sr0") == []


async def test_scan_reads_a_disc_folder_without_7z(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "")
    folder = tmp_path / "disc"
    (folder / "BDMV" / "PLAYLIST").mkdir(parents=True)
    (folder / "BDMV" / "PLAYLIST" / "00001.MPLS").write_bytes(mpls([_item("00004", 10.0)]))
    (folder / "BDMV" / "PLAYLIST" / "readme.txt").write_bytes(b"x")
    playlists = await scan_playlists(str(folder))
    assert [(p.name, p.clips) for p in playlists] == [("00001.mpls", [4])]


async def test_scan_folder_without_playlist_dir_is_empty(tmp_path: Path) -> None:
    (tmp_path / "BDMV").mkdir()
    assert await scan_playlists(str(tmp_path)) == []


async def test_scan_without_7z_is_empty_and_logged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    with caplog.at_level(logging.INFO, logger="arm_ripper.scan.bd_playlists"):
        assert await scan_playlists("/dev/sr0") == []
    assert any("count=0" in r.getMessage() and "reason=no-7z" in r.getMessage() for r in caplog.records)


async def test_scan_spawn_failure_is_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    bin_dir = _fake_7zz(tmp_path, monkeypatch, "")
    (bin_dir / "7zz").write_text("not a script, no shebang \x00")  # exec format error
    with caplog.at_level(logging.INFO, logger="arm_ripper.scan.bd_playlists"):
        assert await scan_playlists("/dev/sr0") == []
    assert any("reason=spawn-failed" in r.getMessage() for r in caplog.records)


async def test_scan_never_raises(monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    async def _boom(_p: str) -> tuple[dict[str, bytes], str]:
        raise OSError("disc gone")

    monkeypatch.setattr(bd_playlists, "_read_files", _boom)
    with caplog.at_level(logging.INFO, logger="arm_ripper.scan.bd_playlists"):
        assert await scan_playlists("/dev/sr0") == []
    assert any("reason=error" in r.getMessage() for r in caplog.records)


async def test_scan_logs_count_and_elapsed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    _fake_7zz(tmp_path, monkeypatch, _copy_into_out(tmp_path, {"00001.mpls": mpls([_item("00002", 1.0)])}))
    with caplog.at_level(logging.INFO, logger="arm_ripper.scan.bd_playlists"):
        await scan_playlists("/dev/sr0")
    assert any(
        r.getMessage().startswith("bd_playlists device=/dev/sr0 count=1 elapsed_ms=")
        and r.getMessage().endswith("reason=ok")
        for r in caplog.records
    )


async def test_cancelled_scan_kills_and_reaps_the_read(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pid_file = tmp_path / "pid"
    _fake_7zz(tmp_path, monkeypatch, f"echo $$ > {pid_file}\nexec /bin/sleep 5")
    task = asyncio.create_task(scan_playlists("/dev/sr0"))
    while not pid_file.exists() or not pid_file.read_text().strip():
        await asyncio.sleep(0.01)
    pid = int(pid_file.read_text())
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    try:
        assert not _alive(pid)
    finally:
        if _alive(pid):
            os.kill(pid, signal.SIGKILL)


def test_read_mpls_files_missing_directory(tmp_path: Path) -> None:
    assert read_mpls_files(tmp_path / "nope") == {}


def test_parse_playlists_orders_by_name_and_drops_garbage() -> None:
    files = {"00002.mpls": mpls([_item("00001", 1.0)]), "00001.mpls": mpls([_item("00001", 1.0)]), "00003.mpls": b""}
    assert [p.name for p in parse_playlists(files)] == ["00001.mpls", "00002.mpls"]


class _WedgedProc:
    """A child that ignores SIGKILL (drive I/O wedge): wait() never completes."""

    pid = 4242
    returncode: int | None = None

    def __init__(self) -> None:
        self.killed = False

    def kill(self) -> None:
        self.killed = True

    async def wait(self) -> int:
        await asyncio.sleep(60)
        return -9


async def test_reap_gives_up_on_a_wedged_child_instead_of_hanging(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(playlist_extract, "REAP_TIMEOUT_SECONDS", 0.05)
    proc = _WedgedProc()
    with caplog.at_level(logging.ERROR, logger="arm_ripper.scan.playlist_extract"):
        await playlist_extract._reap(proc)  # type: ignore[arg-type]
    assert proc.killed
    assert any("did not exit" in r.getMessage() for r in caplog.records)


async def test_reap_leaves_a_finished_child_alone() -> None:
    proc = _WedgedProc()
    proc.returncode = 0
    await playlist_extract._reap(proc)  # type: ignore[arg-type]
    assert not proc.killed
