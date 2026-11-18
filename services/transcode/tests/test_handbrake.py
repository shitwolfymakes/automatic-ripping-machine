"""HandBrakeCLI text-mode progress parser."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import Awaitable

import pytest

from arm_transcode.handbrake import (
    build_handbrake_command,
    _PROGRESS_LINE_RE,
    _STDERR_TAIL_LINES,
    _consume_progress,
    _parse_eta,
    _parse_fps,
    _process_progress_line,
    _split_progress_lines,
    transcode_handbrake,
)


def _match(line: str) -> re.Match[str] | None:
    return _PROGRESS_LINE_RE.search(line)


def test_full_line_with_eta() -> None:
    m = _match("Encoding: task 1 of 1, 47.30 % (45.67 fps, avg 23.45 fps, ETA 00h12m34s)")
    assert m is not None
    assert int(round(float(m.group("pct")))) == 47
    assert _parse_eta(m) == 12 * 60 + 34
    assert m.group("pass") == "1"
    assert m.group("pass_total") == "1"


def test_zero_progress_no_eta_yet() -> None:
    m = _match("Encoding: task 1 of 1, 0.00 %")
    assert m is not None
    assert int(round(float(m.group("pct")))) == 0
    assert _parse_eta(m) is None


def test_one_hundred_percent() -> None:
    m = _match("Encoding: task 1 of 1, 100.00 % (45.67 fps, avg 23.45 fps, ETA 00h00m00s)")
    assert m is not None
    assert int(round(float(m.group("pct")))) == 100
    assert _parse_eta(m) == 0


def test_eta_with_hours() -> None:
    m = _match("Encoding: task 2 of 3, 5.20 % (12.00 fps, avg 12.00 fps, ETA 01h45m30s)")
    assert m is not None
    assert _parse_eta(m) == 3600 + 45 * 60 + 30


def test_fps_pair_is_extracted() -> None:
    """The live and average frame rates ride on the heartbeat (D-248)."""
    m = _match("Encoding: task 1 of 1, 47.30 % (45.67 fps, avg 23.45 fps, ETA 00h12m34s)")
    assert m is not None
    assert _parse_fps(m) == (45.67, 23.45)
    assert _parse_eta(m) == 12 * 60 + 34


def test_fps_is_unknown_without_the_tail_and_eta_still_parses_alone() -> None:
    early = _match("Encoding: task 1 of 1, 0.00 %")
    assert early is not None
    assert _parse_fps(early) == (None, None)
    # A tail with an ETA but no fps pair keeps the ETA.
    eta_only = _match("Encoding: task 1 of 2, 50.00 % (... ETA 00h05m00s)")
    assert eta_only is not None
    assert _parse_fps(eta_only) == (None, None)
    assert _parse_eta(eta_only) == 300


def test_does_not_match_title_scan_line() -> None:
    """`Scanning title 1 of 1, 70.00 %` is title-scan progress, not encode
    progress. Anchoring on `task N of M` skips it cleanly."""
    assert _match("Scanning title 1 of 1, 70.00 %") is None


def test_does_not_match_unrelated_line() -> None:
    assert _match("HandBrake 1.6.1 (2023012900) - Linux x86_64") is None
    assert _match("Cannot load libnvidia-encode.so.1") is None
    assert _match("Muxing: this may take a while...") is None


def test_pass_index_is_extracted() -> None:
    """Two-pass encodes report `task 1 of 2` then `task 2 of 2`."""
    m1 = _match("Encoding: task 1 of 2, 50.00 % (... ETA 00h05m00s)")
    m2 = _match("Encoding: task 2 of 2, 10.00 % (... ETA 00h08m00s)")
    assert m1 is not None and m1.group("pass") == "1" and m1.group("pass_total") == "2"
    assert m2 is not None and m2.group("pass") == "2" and m2.group("pass_total") == "2"


@pytest.mark.asyncio
async def test_current_pass_is_emitted_as_n_over_m() -> None:
    """The progress callback's `current` parameter is `N/M` so the UI can
    render HandBrake's internal pass count directly."""
    raw = "Encoding: task 1 of 2, 50.00 % (... ETA 00h05m00s)\rEncoding: task 2 of 2, 10.00 % (... ETA 00h08m00s)\n"
    stream = _FakeStream([raw.encode()])
    seen: list[str | None] = []

    async def cb(
        pct: int, eta: int | None, current: str | None, fps: float | None, avg_fps: float | None
    ) -> Awaitable[None]:  # type: ignore[return]
        seen.append(current)

    await _consume_progress(stream, cb)  # type: ignore[arg-type]
    assert seen == ["1/2", "2/2"]


# --- _consume_progress: the carriage-return splitter ------------------------


class _FakeStream:
    """Minimal `asyncio.StreamReader`-shaped stub. The real reader's
    `read(n)` is what `_consume_progress` calls; we hand it our scripted
    chunks one per call, EOF on exhaustion."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)

    async def read(self, n: int) -> bytes:
        if not self._chunks:
            return b""
        return self._chunks.pop(0)


@pytest.mark.asyncio
async def test_consume_progress_splits_on_carriage_return() -> None:
    """HandBrake glues progress updates with `\\r` (no newline). A
    naive readline-loop reads them all as one giant final line and the
    UI bar gets stuck at whichever pct happens to be first in the
    buffer. Splitting on `[\\r\\n]` recovers each tick as its own
    logical line so dedupe-by-pct fires per update."""
    raw = (
        "Scanning title 1 of 1, 100.00 %\n"
        "Encoding: task 1 of 1, 0.00 %\r"
        "Encoding: task 1 of 1, 12.50 %\r"
        "Encoding: task 1 of 1, 25.00 % (140 fps, avg 140 fps, ETA 00h00m05s)\r"
        "Encoding: task 1 of 1, 50.00 % (140 fps, avg 140 fps, ETA 00h00m02s)\r"
        "Encoding: task 1 of 1, 100.00 %\n"
    )
    stream = _FakeStream([raw.encode()])

    seen: list[tuple[int, int | None, str | None, float | None, float | None]] = []

    async def cb(
        pct: int, eta: int | None, current: str | None, fps: float | None, avg_fps: float | None
    ) -> Awaitable[None]:  # type: ignore[return]
        seen.append((pct, eta, current, fps, avg_fps))

    await _consume_progress(stream, cb)  # type: ignore[arg-type]

    pcts = [s[0] for s in seen]
    assert pcts == [0, 12, 25, 50, 100]  # one event per unique percent
    assert seen[2][1] == 5  # ETA in seconds at 25 %
    assert seen[2][3:] == (140.0, 140.0)  # frame rates at 25 %
    assert seen[1][3:] == (None, None)  # no tail yet at 12 %


@pytest.mark.asyncio
async def test_consume_progress_dedupes_repeated_percent() -> None:
    """HandBrake near 100 % spams the same `99.97 %` line until the encode
    actually finishes. The dedupe should keep the WS publish rate sane."""
    raw = (
        "Encoding: task 1 of 1, 99.97 %\r"
        "Encoding: task 1 of 1, 99.97 %\r"
        "Encoding: task 1 of 1, 99.97 %\r"
        "Encoding: task 1 of 1, 100.00 %\n"
    )
    stream = _FakeStream([raw.encode()])

    seen: list[int] = []

    async def cb(
        pct: int, eta: int | None, current: str | None, fps: float | None, avg_fps: float | None
    ) -> Awaitable[None]:  # type: ignore[return]
        seen.append(pct)

    await _consume_progress(stream, cb)  # type: ignore[arg-type]
    assert seen == [100]  # 99.97 → round to 100, then 100.00 same → one fire


@pytest.mark.asyncio
async def test_consume_progress_handles_chunk_boundary_mid_line() -> None:
    """The chunk read may bisect a progress line. The `pending` carry-
    over should stitch the halves back together on the next chunk."""
    chunks = [
        b"Encoding: task 1 of 1, 33.33",  # mid-token
        b" % (140 fps, avg 140 fps, ETA 00h00m05s)\rEncoding: task 1 of 1, 50",
        b".00 %\n",
    ]
    stream = _FakeStream(chunks)
    seen: list[int] = []

    async def cb(
        pct: int, eta: int | None, current: str | None, fps: float | None, avg_fps: float | None
    ) -> Awaitable[None]:  # type: ignore[return]
        seen.append(pct)

    await _consume_progress(stream, cb)  # type: ignore[arg-type]
    assert seen == [33, 50]


@pytest.mark.asyncio
async def test_consume_progress_processes_unterminated_final_line_at_eof() -> None:
    """A last progress line with no trailing `\\r`/`\\n` is still handled at EOF."""
    stream = _FakeStream([b"Encoding: task 1 of 1, 10.00 %\r", b"Encoding: task 1 of 1, 20.00 %"])
    seen: list[int] = []

    async def cb(pct: int, eta: int | None, current: str | None, fps: float | None, avg_fps: float | None) -> None:
        seen.append(pct)

    await _consume_progress(stream, cb)  # type: ignore[arg-type]
    assert seen == [10, 20]


@pytest.mark.asyncio
async def test_process_progress_line_empty_line_returns_last_emitted_untouched(
    caplog: pytest.LogCaptureFixture,
) -> None:
    calls: list[int] = []

    async def cb(pct: int, eta: int | None, current: str | None, fps: float | None, avg_fps: float | None) -> None:
        calls.append(pct)

    with caplog.at_level(logging.DEBUG, logger="arm_transcode.handbrake"):
        result = await _process_progress_line("", cb, 42)
    assert result == 42
    assert calls == []
    assert caplog.records == []


@pytest.mark.asyncio
async def test_process_progress_line_swallows_callback_error_and_logs_debug(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Pins current behaviour: the swallow is a known defect tracked in #412.
    async def cb(pct: int, eta: int | None, current: str | None, fps: float | None, avg_fps: float | None) -> None:
        raise RuntimeError("boom")

    with caplog.at_level(logging.DEBUG, logger="arm_transcode.handbrake"):
        result = await _process_progress_line("Encoding: task 1 of 1, 30.00 %", cb, -1)
    assert result == 30
    assert any(
        r.name == "arm_transcode.handbrake"
        and r.levelno == logging.DEBUG
        and r.getMessage() == "progress_callback raised: boom"
        for r in caplog.records
    )


# Vitest-style asyncio plumbing — pytest-asyncio is already a dev dep.
def _autouse_asyncio_mode() -> None:
    asyncio.get_event_loop_policy()  # touch to silence unused-import warnings


def test_split_progress_lines_breaks_on_cr_and_lf_and_keeps_the_unterminated_tail() -> None:
    assert _split_progress_lines("a\rb\nc") == (["a", "b"], "c")
    assert _split_progress_lines("no terminator") == ([], "no terminator")


class _FakeProc:
    """Stand-in for the `asyncio.subprocess.Process` HandBrakeCLI launch."""

    def __init__(self, stderr_lines: list[str], rc: int) -> None:
        self.stdout = _FakeStream([])
        self.stderr = asyncio.StreamReader()
        self.stderr.feed_data("".join(f"{line}\n" for line in stderr_lines).encode())
        self.stderr.feed_eof()
        self._rc = rc

    async def wait(self) -> int:
        return self._rc


@pytest.mark.asyncio
async def test_transcode_handbrake_nonzero_exit_raises_with_only_the_stderr_tail(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    total = _STDERR_TAIL_LINES + 5
    lines = [f"stderr line {i}" for i in range(total)]
    proc = _FakeProc(lines, rc=3)

    async def fake_exec(*args: str, **kwargs: object) -> _FakeProc:
        return proc

    async def cb(*_args: object) -> None:  # pragma: no cover - no progress is emitted
        raise AssertionError("no progress expected")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)

    with pytest.raises(RuntimeError) as excinfo:
        await transcode_handbrake(
            input_path=tmp_path / "in.mkv",
            output_path=tmp_path / "out.mkv",
            preset_ref="Fast 1080p30",
            extra_args=None,
            encoder_args=[],
            progress_callback=cb,
        )

    expected_tail = "\n".join(lines[-_STDERR_TAIL_LINES:])
    assert str(excinfo.value) == f"HandBrakeCLI exited rc=3\nstderr tail:\n{expected_tail}"
    assert "rc=3" in str(excinfo.value)
    assert "stderr line 4\n" not in str(excinfo.value)
    assert "stderr line 5\n" in str(excinfo.value)


def _build(extra_args: str | None = None, encoder_args: list[str] | None = None) -> list[str]:
    return build_handbrake_command(
        input_path=Path("/in/a.mkv"),
        output_path=Path("/out/a.mkv"),
        preset_ref="Fast 1080p30",
        extra_args=extra_args,
        encoder_args=encoder_args or [],
    )


_BASE_ARGV = ["HandBrakeCLI", "-i", "/in/a.mkv", "-o", "/out/a.mkv", "--preset", "Fast 1080p30"]


def test_build_handbrake_command_base_argv() -> None:
    assert _build() == _BASE_ARGV


def test_build_handbrake_command_encoder_args_follow_preset() -> None:
    assert _build(encoder_args=["--encoder", "x265"]) == [*_BASE_ARGV, "--encoder", "x265"]


def test_build_handbrake_command_extra_args_split_and_last() -> None:
    assert _build(extra_args="--quality  20\t--rate 30", encoder_args=["--encoder", "x265"]) == [
        *_BASE_ARGV,
        "--encoder",
        "x265",
        "--quality",
        "20",
        "--rate",
        "30",
    ]


@pytest.mark.parametrize("extra_args", [None, ""])
def test_build_handbrake_command_empty_extra_args_add_nothing(extra_args: str | None) -> None:
    assert _build(extra_args=extra_args) == _BASE_ARGV


def test_build_handbrake_command_without_settings_is_todays_argv() -> None:
    """M11: a settings-less preset keeps today's argv byte for byte."""
    assert build_handbrake_command(
        input_path=Path("/raw/title_t00.mkv"),
        output_path=Path("/out/Movie.mkv.arm-inprogress"),
        preset_ref="H.265 MKV 1080p30",
        extra_args="--quality 20 --all-audio",
        encoder_args=["--encoder", "x265"],
    ) == [
        "HandBrakeCLI",
        "-i",
        "/raw/title_t00.mkv",
        "-o",
        "/out/Movie.mkv.arm-inprogress",
        "--preset",
        "H.265 MKV 1080p30",
        "--encoder",
        "x265",
        "--quality",
        "20",
        "--all-audio",
    ]


def test_build_handbrake_command_with_preset_file_imports_arm_preset() -> None:
    assert build_handbrake_command(
        input_path=Path("/in/a.mkv"),
        output_path=Path("/out/a.mkv"),
        preset_ref=None,
        extra_args="--foo 1",
        encoder_args=["--encoder", "x264"],
        preset_file=Path("/tmp/arm-hb-1/arm-preset.json"),
    ) == [
        "HandBrakeCLI",
        "-i",
        "/in/a.mkv",
        "-o",
        "/out/a.mkv",
        "--preset-import-file",
        "/tmp/arm-hb-1/arm-preset.json",
        "--preset",
        "arm",
        "--encoder",
        "x264",
        "--foo",
        "1",
    ]


def test_build_handbrake_command_without_preset_file_or_ref_raises() -> None:
    with pytest.raises(RuntimeError, match="needs a preset_ref"):
        build_handbrake_command(
            input_path=Path("/in/a.mkv"),
            output_path=Path("/out/a.mkv"),
            preset_ref=None,
            extra_args=None,
            encoder_args=[],
        )
