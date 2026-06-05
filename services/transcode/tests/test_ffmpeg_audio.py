"""Tests for `transcode_audio` against a faked ffmpeg subprocess.

ffmpeg streams `key=value` progress lines on stdout (when launched with
`-progress pipe:1`). `transcode_audio` parses `out_time_us=` and fires
the progress callback with a percent computed against the source
`duration_seconds`. The fake replaces `asyncio.create_subprocess_exec`
so the test can stream a canned progress trace and control exit code +
stderr without depending on a real ffmpeg binary or a real WAV file.

Covers:

  - Happy path FLAC: progress percentages tick monotonically and end at
    100; the final return is the size of the output_path file.
  - Happy path MP3: same as above, distinct preset_ref.
  - Unknown preset_ref: rejected before the subprocess is spawned.
  - Non-zero exit: raises RuntimeError including the stderr tail.
  - duration_seconds=None: progress branch is skipped; the callback is
    never fired but transcode_audio still returns the file size.
  - progress_callback raising: the exception is swallowed at DEBUG; the
    transcode itself isn't disturbed.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import arm_transcode.ffmpeg_audio as ffmpeg_audio
from arm_transcode.ffmpeg_audio import transcode_audio


class _FakeStream:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)

    async def readline(self) -> bytes:
        if not self._lines:
            return b""
        return self._lines.pop(0)


class _FakeProc:
    def __init__(
        self,
        stdout_lines: list[bytes],
        stderr_lines: list[bytes] | None = None,
        returncode: int = 0,
    ) -> None:
        self.stdout = _FakeStream(stdout_lines)
        self.stderr = _FakeStream(stderr_lines or [])
        self._final_returncode = returncode
        self.returncode: int | None = None

    async def wait(self) -> int:
        await asyncio.sleep(0)
        self.returncode = self._final_returncode
        return self.returncode

    def kill(self) -> None:
        self.returncode = -9


def _stub_subprocess(
    monkeypatch,
    *,
    stdout_lines: list[str],
    stderr_lines: list[str] | None = None,
    returncode: int = 0,
    captured_args: list[tuple] | None = None,
) -> _FakeProc:
    encoded_out = [(line + "\n").encode() for line in stdout_lines]
    encoded_err = [(line + "\n").encode() for line in (stderr_lines or [])]
    fake = _FakeProc(encoded_out, stderr_lines=encoded_err, returncode=returncode)

    async def fake_create(*a: Any, **_kw: Any) -> _FakeProc:
        if captured_args is not None:
            captured_args.append(a)
        return fake

    monkeypatch.setattr(ffmpeg_audio.asyncio, "create_subprocess_exec", fake_create)
    return fake


def _progress_lines(out_times_us: list[int]) -> list[str]:
    """ffmpeg emits its progress as a multi-line block per snapshot; we
    only key off `out_time_us=`. The rest of the keys are noise that
    transcode_audio skips."""
    out: list[str] = []
    for t in out_times_us:
        out += [
            f"out_time_us={t}",
            "bitrate=128.0kbits/s",
            "progress=continue",
        ]
    out.append("progress=end")
    return out


@pytest.mark.asyncio
async def test_transcode_audio_flac_emits_monotonic_progress_and_returns_size(monkeypatch, tmp_path):
    # 60s source, 3 progress snapshots at 20s / 40s / 60s → 33% / 66% / 100%.
    _stub_subprocess(
        monkeypatch,
        stdout_lines=_progress_lines([20_000_000, 40_000_000, 60_000_000]),
    )
    out_path = tmp_path / "out.flac"
    out_path.write_bytes(b"fLaC" + b"\x00" * 96)  # synthetic 100-byte file

    progress: list[tuple[int, int | None, str | None]] = []

    async def cb(pct: int, tcount: int | None, note: str | None) -> None:
        progress.append((pct, tcount, note))

    size = await transcode_audio(
        input_path=tmp_path / "in.wav",
        output_path=out_path,
        preset_ref="flac",
        duration_seconds=60,
        progress_callback=cb,
    )
    assert size == out_path.stat().st_size
    # Percentages tick up; final emission lands at 100.
    pcts = [p[0] for p in progress]
    assert pcts == sorted(pcts)
    assert pcts[-1] == 100
    # All emissions carry the encoding note.
    assert all(p[2] == "encoding" for p in progress)


@pytest.mark.asyncio
@pytest.mark.parametrize(("preset", "expected_fmt"), [("flac", "flac"), ("mp3", "mp3")])
async def test_transcode_audio_passes_explicit_format_flag(monkeypatch, tmp_path, preset, expected_fmt):
    """Regression: the atomic-rename flow writes to `<final>.arm-inprogress`,
    so ffmpeg can't infer the container from the filename. Without `-f
    <fmt>`, ffmpeg exits with "Unable to find a suitable output format"
    before encoding anything and the whole transcode session fails."""
    captured: list[tuple] = []
    _stub_subprocess(monkeypatch, stdout_lines=_progress_lines([10_000_000]), captured_args=captured)
    out_path = tmp_path / f"out.{preset}.arm-inprogress"
    out_path.write_bytes(b"x" * 20)

    async def cb(_p: int, _t: int | None, _n: str | None) -> None:
        return None

    await transcode_audio(
        input_path=tmp_path / "in.wav",
        output_path=out_path,
        preset_ref=preset,
        duration_seconds=10,
        progress_callback=cb,
    )
    assert captured, "subprocess fake never invoked"
    cmd = list(captured[0])
    assert "-f" in cmd, f"cmd missing `-f` flag: {cmd}"
    assert cmd[cmd.index("-f") + 1] == expected_fmt


@pytest.mark.asyncio
async def test_transcode_audio_mp3_succeeds(monkeypatch, tmp_path):
    _stub_subprocess(monkeypatch, stdout_lines=_progress_lines([10_000_000, 20_000_000]))
    out_path = tmp_path / "out.mp3"
    out_path.write_bytes(b"\xff\xfb" + b"\x00" * 100)

    async def cb(_p: int, _t: int | None, _n: str | None) -> None:
        return None

    size = await transcode_audio(
        input_path=tmp_path / "in.wav",
        output_path=out_path,
        preset_ref="mp3",
        duration_seconds=20,
        progress_callback=cb,
    )
    assert size == out_path.stat().st_size


@pytest.mark.asyncio
async def test_transcode_audio_unknown_preset_rejects_before_spawn(monkeypatch, tmp_path):
    called = {"n": 0}

    async def must_not_call(*_a: Any, **_kw: Any) -> _FakeProc:
        called["n"] += 1
        return _FakeProc([])

    monkeypatch.setattr(ffmpeg_audio.asyncio, "create_subprocess_exec", must_not_call)

    async def cb(_p: int, _t: int | None, _n: str | None) -> None:
        return None

    with pytest.raises(RuntimeError, match="unsupported audio preset_ref"):
        await transcode_audio(
            input_path=tmp_path / "in.wav",
            output_path=tmp_path / "out.opus",
            preset_ref="opus",
            duration_seconds=10,
            progress_callback=cb,
        )
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_transcode_audio_nonzero_exit_raises_with_stderr_tail(monkeypatch, tmp_path):
    _stub_subprocess(
        monkeypatch,
        stdout_lines=_progress_lines([10_000_000]),
        stderr_lines=[
            "[error] something broke at frame 1234",
            "[error] aborting",
        ],
        returncode=1,
    )

    async def cb(_p: int, _t: int | None, _n: str | None) -> None:
        return None

    with pytest.raises(RuntimeError) as exc:
        await transcode_audio(
            input_path=tmp_path / "in.wav",
            output_path=tmp_path / "out.flac",
            preset_ref="flac",
            duration_seconds=10,
            progress_callback=cb,
        )
    assert "rc=1" in str(exc.value)
    assert "something broke" in str(exc.value)


@pytest.mark.asyncio
async def test_transcode_audio_duration_none_skips_progress_callback(monkeypatch, tmp_path):
    _stub_subprocess(monkeypatch, stdout_lines=_progress_lines([10_000_000, 20_000_000]))
    out_path = tmp_path / "out.flac"
    out_path.write_bytes(b"x" * 50)

    called = {"n": 0}

    async def cb(_p: int, _t: int | None, _n: str | None) -> None:
        called["n"] += 1

    size = await transcode_audio(
        input_path=tmp_path / "in.wav",
        output_path=out_path,
        preset_ref="flac",
        duration_seconds=None,
        progress_callback=cb,
    )
    assert size == 50
    # No progress was emitted because we can't compute a percentage.
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_transcode_audio_progress_callback_exception_does_not_propagate(monkeypatch, tmp_path):
    _stub_subprocess(monkeypatch, stdout_lines=_progress_lines([10_000_000, 20_000_000]))
    out_path = tmp_path / "out.flac"
    out_path.write_bytes(b"x" * 20)

    async def cb(_p: int, _t: int | None, _n: str | None) -> None:
        raise ValueError("cb-bug")

    # No raise → cb's exception is swallowed at the call site (logged at debug).
    size = await transcode_audio(
        input_path=tmp_path / "in.wav",
        output_path=out_path,
        preset_ref="flac",
        duration_seconds=10,
        progress_callback=cb,
    )
    assert size == 20
