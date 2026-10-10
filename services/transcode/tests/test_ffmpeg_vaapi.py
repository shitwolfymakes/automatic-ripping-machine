"""Tests for the ffmpeg VAAPI (AMD/Mesa) engine.

`build_command` is pure and covers the fixed CQP defaults, container →
muxer mapping, and extra_args placement. `transcode_ffmpeg_vaapi` is
exercised against a faked ffmpeg subprocess, mirroring the fake-process
pattern in `test_ffmpeg_audio.py` (fake `asyncio.create_subprocess_exec`
streaming a canned `-progress pipe:1` trace, no real ffmpeg binary or
media file needed).

Covers:

  - build_command: default CQP flags, encoder from the catalog spec,
    explicit stream mapping (first video stream only, all audio, subs
    only for MKV), container → muxer, extra_args appended before the
    output path, unsupported container rejected. MP4 drops subtitles
    entirely (`-sn`) instead of mapping them, because MP4 cannot mux
    bitmap subtitle codecs (Blu-ray PGS / DVD) and would abort mid-encode.
  - transcode_ffmpeg_vaapi: success returns the output file size and
    emits progress; non-zero exit raises RuntimeError with the stderr
    tail; duration_seconds=None completes successfully with no progress
    callbacks (the percent can't be computed without a duration).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

from arm_common import ContainerFormat
from arm_common.encoders import get_encoder
from arm_transcode.engines.ffmpeg_vaapi import build_command, transcode_ffmpeg_vaapi


def test_build_command_defaults():
    cmd = build_command(
        input_path=Path("/raw/t.mkv"),
        output_path=Path("/media/o.mkv.arm-inprogress"),
        spec=get_encoder("vaapi_h265"),
        device="/dev/dri/renderD128",
        container=ContainerFormat.MKV,
        extra_args=None,
    )
    assert cmd[:2] == ["ffmpeg", "-hide_banner"]
    assert cmd[cmd.index("-vaapi_device") + 1] == "/dev/dri/renderD128"
    assert cmd[cmd.index("-vf") + 1] == "format=nv12,hwupload"
    assert cmd[cmd.index("-c:v") + 1] == "hevc_vaapi"
    assert cmd[cmd.index("-rc_mode") + 1] == "CQP"
    assert cmd[cmd.index("-qp") + 1] == "22"
    map_values = [cmd[i + 1] for i, tok in enumerate(cmd) if tok == "-map"]
    assert map_values == ["0:v:0", "0:a?", "0:s?"]
    assert "0" not in map_values  # bare `-map 0` would pull in extra angles / attached pics
    assert cmd[cmd.index("-c:a") + 1] == "copy"
    assert cmd[cmd.index("-c:s") + 1] == "copy"
    assert cmd[cmd.index("-f") + 1] == "matroska"
    assert cmd[-1] == "/media/o.mkv.arm-inprogress"
    assert "scale" not in " ".join(cmd)


def test_build_command_mp4_drops_subtitles_and_passes_sn():
    cmd = build_command(
        input_path=Path("i"),
        output_path=Path("o"),
        spec=get_encoder("vaapi_h264"),
        device="/dev/dri/renderD128",
        container=ContainerFormat.MP4,
        extra_args=None,
    )
    map_values = [cmd[i + 1] for i, tok in enumerate(cmd) if tok == "-map"]
    assert map_values == ["0:v:0", "0:a?"]
    assert "0:s?" not in map_values
    assert "-c:s" not in cmd
    assert "-sn" in cmd
    assert cmd[cmd.index("-f") + 1] == "mp4"


def test_extra_args_appended_before_output():
    cmd = build_command(
        input_path=Path("i"),
        output_path=Path("o"),
        spec=get_encoder("vaapi_h264"),
        device="/dev/dri/renderD128",
        container=ContainerFormat.MP4,
        extra_args="-qp 18",
    )
    assert cmd[-3:] == ["-qp", "18", "o"]
    assert cmd[cmd.index("-f") + 1] == "mp4"


def test_unsupported_container_rejected():
    with pytest.raises(ValueError, match="container"):
        build_command(
            input_path=Path("i"),
            output_path=Path("o"),
            spec=get_encoder("vaapi_h264"),
            device="d",
            container=ContainerFormat.FLAC,
            extra_args=None,
        )


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


def _stub_subprocess(
    monkeypatch,
    *,
    stdout_lines: list[str],
    stderr_lines: list[str] | None = None,
    returncode: int = 0,
) -> _FakeProc:
    import arm_transcode.engines.ffmpeg_vaapi as ffmpeg_vaapi

    encoded_out = [(line + "\n").encode() for line in stdout_lines]
    encoded_err = [(line + "\n").encode() for line in (stderr_lines or [])]
    fake = _FakeProc(encoded_out, stderr_lines=encoded_err, returncode=returncode)

    async def fake_create(*_a: Any, **_kw: Any) -> _FakeProc:
        return fake

    monkeypatch.setattr(ffmpeg_vaapi.asyncio, "create_subprocess_exec", fake_create)
    return fake


def _progress_lines(out_times_us: list[int]) -> list[str]:
    out: list[str] = []
    for t in out_times_us:
        out += [f"out_time_us={t}", "bitrate=0kbits/s", "progress=continue"]
    out.append("progress=end")
    return out


@pytest.mark.asyncio
async def test_transcode_ffmpeg_vaapi_success_returns_size_and_emits_progress(monkeypatch, tmp_path):
    _stub_subprocess(monkeypatch, stdout_lines=_progress_lines([30_000_000, 60_000_000]))
    out_path = tmp_path / "out.mkv"
    out_path.write_bytes(b"x" * 42)

    progress: list[tuple[int, int | None, str | None]] = []

    async def cb(pct: int, eta: int | None, note: str | None) -> None:
        progress.append((pct, eta, note))

    size = await transcode_ffmpeg_vaapi(
        input_path=tmp_path / "in.mkv",
        output_path=out_path,
        spec=get_encoder("vaapi_h265"),
        device="/dev/dri/renderD128",
        container=ContainerFormat.MKV,
        extra_args=None,
        duration_seconds=60,
        progress_callback=cb,
    )
    assert size == 42
    assert progress
    assert progress[-1][0] == 100


@pytest.mark.asyncio
async def test_transcode_ffmpeg_vaapi_nonzero_exit_raises_with_stderr_tail(monkeypatch, tmp_path):
    _stub_subprocess(
        monkeypatch,
        stdout_lines=_progress_lines([10_000_000]),
        stderr_lines=["[error] vaapi init failed", "[error] aborting"],
        returncode=1,
    )

    async def cb(_p: int, _e: int | None, _n: str | None) -> None:
        return None

    with pytest.raises(RuntimeError) as exc:
        await transcode_ffmpeg_vaapi(
            input_path=tmp_path / "in.mkv",
            output_path=tmp_path / "out.mkv",
            spec=get_encoder("vaapi_h265"),
            device="/dev/dri/renderD128",
            container=ContainerFormat.MKV,
            extra_args=None,
            duration_seconds=10,
            progress_callback=cb,
        )
    assert "ffmpeg_vaapi exited 1" in str(exc.value)
    assert "vaapi init failed" in str(exc.value)


@pytest.mark.asyncio
async def test_transcode_ffmpeg_vaapi_duration_none_completes_with_no_progress(monkeypatch, tmp_path):
    _stub_subprocess(monkeypatch, stdout_lines=_progress_lines([10_000_000, 20_000_000]))
    out_path = tmp_path / "out.mkv"
    out_path.write_bytes(b"y" * 7)

    called = {"n": 0}

    async def cb(_p: int, _e: int | None, _n: str | None) -> None:
        called["n"] += 1

    size = await transcode_ffmpeg_vaapi(
        input_path=tmp_path / "in.mkv",
        output_path=out_path,
        spec=get_encoder("vaapi_h265"),
        device="/dev/dri/renderD128",
        container=ContainerFormat.MKV,
        extra_args=None,
        duration_seconds=None,
        progress_callback=cb,
    )
    assert size == 7
    assert called["n"] == 0
