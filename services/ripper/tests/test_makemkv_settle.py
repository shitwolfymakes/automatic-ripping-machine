"""The checks that say a makemkvcon run is closed: open descriptors, stable sizes, the MKV header."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from arm_ripper.rip.makemkv_settle import (
    RunWatch,
    mkv_segment_complete,
    open_files_under,
    run_is_settled,
    sizes_stable,
    suspect_output,
)

_EBML = bytes.fromhex("1a45dfa3") + b"\x84" + b"abcd"  # ID, size 4, a 4-byte body
_SEGMENT = bytes.fromhex("18538067")


def _fake_proc(tmp_path: Path, pid: int, targets: list[str]) -> Path:
    """A /proc tree where `pid` holds a descriptor on each of `targets`."""
    fd_dir = tmp_path / "proc" / str(pid) / "fd"
    fd_dir.mkdir(parents=True)
    for n, target in enumerate(targets):
        os.symlink(target, fd_dir / str(n))
    return tmp_path / "proc"


async def _no_sleep(_seconds: float) -> None:
    return None


def _mkv(path: Path, *, segment_size: bytes, payload: int, trailing: int = 0) -> Path:
    path.write_bytes(_EBML + _SEGMENT + segment_size + b"x" * payload + b"y" * trailing)
    return path


def test_open_files_under_lists_only_descriptors_inside_the_root(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    proc = _fake_proc(tmp_path, 7, [str(out / "a_t00.mkv"), "/dev/sr0", "pipe:[42]", str(tmp_path / "other.mkv")])
    assert open_files_under(7, out, proc) == {out.resolve() / "a_t00.mkv"}


def test_open_files_under_is_empty_when_nothing_is_held(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    assert open_files_under(7, out, _fake_proc(tmp_path, 7, ["/dev/sr0"])) == set()


def test_open_files_under_is_none_when_the_descriptors_cannot_be_read(tmp_path):
    assert open_files_under(7, tmp_path, tmp_path / "proc") is None


def test_open_files_under_skips_a_descriptor_that_closes_while_listed(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    proc = _fake_proc(tmp_path, 7, [str(out / "a.mkv")])
    (proc / "7" / "fd" / "9").write_text("not a link")  # readlink on a plain file raises OSError
    assert open_files_under(7, out, proc) == {out.resolve() / "a.mkv"}


@pytest.mark.asyncio
async def test_sizes_stable_when_nothing_changes(tmp_path):
    f = tmp_path / "a.mkv"
    f.write_bytes(b"x" * 10)
    assert await sizes_stable([f], 2.0, _no_sleep) is True


@pytest.mark.asyncio
async def test_sizes_not_stable_when_a_file_grows_during_the_wait(tmp_path):
    f = tmp_path / "a.mkv"
    f.write_bytes(b"x" * 10)

    async def grow(_seconds: float) -> None:
        f.write_bytes(b"x" * 20)

    assert await sizes_stable([f], 2.0, grow) is False


@pytest.mark.asyncio
async def test_sizes_not_stable_when_a_file_is_missing(tmp_path):
    assert await sizes_stable([tmp_path / "gone.mkv"], 2.0, _no_sleep) is False


@pytest.mark.asyncio
async def test_sizes_not_stable_when_a_file_vanishes_during_the_wait(tmp_path):
    f = tmp_path / "a.mkv"
    f.write_bytes(b"x")

    async def remove(_seconds: float) -> None:
        f.unlink()

    assert await sizes_stable([f], 2.0, remove) is False


def _watch(out: Path, files: list[Path], expected: int) -> RunWatch:
    return RunWatch(output_dir=out, outputs=lambda: files, expected_files=expected, end_on_completion=True)


@pytest.mark.asyncio
async def test_run_is_settled_when_closed_and_the_count_matches(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    f = out / "a_t00.mkv"
    f.write_bytes(b"x" * 8)
    proc = _fake_proc(tmp_path, 7, ["/dev/sr0"])
    assert await run_is_settled(_watch(out, [f], 1), 7, 1, proc_root=proc, sleep=_no_sleep) is True


@pytest.mark.asyncio
async def test_run_is_settled_without_a_reported_count_uses_the_files(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    f = out / "a_t00.mkv"
    f.write_bytes(b"x" * 8)
    proc = _fake_proc(tmp_path, 7, [])
    assert await run_is_settled(_watch(out, [f], 1), 7, None, proc_root=proc, sleep=_no_sleep) is True


@pytest.mark.asyncio
async def test_run_is_not_settled_while_a_file_is_open(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    f = out / "a_t00.mkv"
    f.write_bytes(b"x" * 8)
    proc = _fake_proc(tmp_path, 7, [str(f)])
    assert await run_is_settled(_watch(out, [f], 1), 7, 1, proc_root=proc, sleep=_no_sleep) is False


@pytest.mark.asyncio
async def test_run_is_not_settled_when_the_descriptors_are_unreadable(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    assert await run_is_settled(_watch(out, [], 0), 7, 0, proc_root=tmp_path / "none", sleep=_no_sleep) is False


@pytest.mark.asyncio
async def test_run_is_not_settled_when_the_file_count_differs(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    f = out / "a_t00.mkv"
    f.write_bytes(b"x")
    proc = _fake_proc(tmp_path, 7, [])
    assert await run_is_settled(_watch(out, [f], 2), 7, 2, proc_root=proc, sleep=_no_sleep) is False


@pytest.mark.asyncio
async def test_run_is_not_settled_when_the_run_reported_a_different_count(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    f = out / "a_t00.mkv"
    f.write_bytes(b"x")
    proc = _fake_proc(tmp_path, 7, [])
    assert await run_is_settled(_watch(out, [f], 1), 7, 2, proc_root=proc, sleep=_no_sleep) is False


@pytest.mark.asyncio
async def test_run_is_not_settled_while_the_file_still_grows(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    f = out / "a_t00.mkv"
    f.write_bytes(b"x")
    proc = _fake_proc(tmp_path, 7, [])

    async def grow(_seconds: float) -> None:
        f.write_bytes(b"xx")

    assert await run_is_settled(_watch(out, [f], 1), 7, 1, proc_root=proc, sleep=grow) is False


def test_a_segment_with_a_known_size_ending_at_the_file_is_complete(tmp_path):
    f = _mkv(tmp_path / "a.mkv", segment_size=b"\x88", payload=8)  # size 8, 8 payload bytes
    assert mkv_segment_complete(f) is True


def test_a_segment_with_an_unknown_size_is_not_complete(tmp_path):
    f = _mkv(tmp_path / "a.mkv", segment_size=b"\x01\xff\xff\xff\xff\xff\xff\xff", payload=8)
    assert mkv_segment_complete(f) is False


def test_a_segment_ending_before_the_file_does_is_not_complete(tmp_path):
    f = _mkv(tmp_path / "a.mkv", segment_size=b"\x88", payload=8, trailing=3)
    assert mkv_segment_complete(f) is False


def test_a_segment_declaring_more_than_the_file_holds_is_not_complete(tmp_path):
    f = _mkv(tmp_path / "a.mkv", segment_size=b"\x90", payload=8)  # size 16, 8 present
    assert mkv_segment_complete(f) is False


def test_a_file_that_is_not_matroska_is_not_complete(tmp_path):
    f = tmp_path / "a.mkv"
    f.write_bytes(b"\x00" * 64)
    assert mkv_segment_complete(f) is False


def test_a_file_with_the_wrong_first_element_is_not_complete(tmp_path):
    f = tmp_path / "a.mkv"
    f.write_bytes(bytes.fromhex("18538067") + b"\x88" + b"x" * 8)
    assert mkv_segment_complete(f) is False


def test_a_file_without_a_segment_after_the_header_is_not_complete(tmp_path):
    f = tmp_path / "a.mkv"
    f.write_bytes(_EBML + bytes.fromhex("1549a966") + b"\x88" + b"x" * 8)
    assert mkv_segment_complete(f) is False


def test_an_ebml_header_of_unknown_size_is_not_complete(tmp_path):
    f = tmp_path / "a.mkv"
    f.write_bytes(bytes.fromhex("1a45dfa3") + b"\xff" + _SEGMENT + b"\x88" + b"x" * 8)
    assert mkv_segment_complete(f) is False


def test_a_truncated_head_is_not_complete(tmp_path):
    f = tmp_path / "a.mkv"
    f.write_bytes(bytes.fromhex("1a45"))  # the ID does not fit
    assert mkv_segment_complete(f) is False
    f.write_bytes(bytes.fromhex("1a45dfa3"))  # no size
    assert mkv_segment_complete(f) is False
    f.write_bytes(_EBML + bytes.fromhex("18538067"))  # no Segment size
    assert mkv_segment_complete(f) is False


def test_a_missing_file_is_not_complete(tmp_path):
    assert mkv_segment_complete(tmp_path / "gone.mkv") is False


def test_a_finished_output_of_the_expected_size_looks_fine(tmp_path):
    f = _mkv(tmp_path / "a.mkv", segment_size=b"\x88", payload=8)
    assert suspect_output(f, f.stat().st_size, f.stat().st_size) == []


def test_a_short_output_is_suspect(tmp_path):
    f = _mkv(tmp_path / "a.mkv", segment_size=b"\x88", payload=8)
    problems = suspect_output(f, 80, 100)
    assert problems == ["80 bytes is under 90% of the 100 the scan expected"]


def test_an_unfinalised_header_is_suspect_and_an_unknown_expectation_is_not_checked(tmp_path):
    f = tmp_path / "a.mkv"
    f.write_bytes(b"\x00" * 16)
    assert suspect_output(f, 16, None) == ["its MKV Segment header is not finalised"]
