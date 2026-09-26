"""`transcode_handbrake` command assembly: the caller-supplied `encoder_args`
(from the engine seam, see `test_engines.py`) land after `--preset` and
before `extra_args`, same order as the old `_hw_encoder_args()` inline call.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest

import arm_transcode.handbrake as handbrake
from arm_transcode.handbrake import transcode_handbrake


class _FakeStream:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)

    async def readline(self) -> bytes:
        if not self._lines:
            return b""
        return self._lines.pop(0)

    async def read(self, _n: int) -> bytes:
        if not self._lines:
            return b""
        return self._lines.pop(0)


class _FakeProc:
    def __init__(self, returncode: int = 0) -> None:
        self.stdout = _FakeStream([])
        self.stderr = _FakeStream([])
        self._final_returncode = returncode
        self.returncode: int | None = None

    async def wait(self) -> int:
        await asyncio.sleep(0)
        self.returncode = self._final_returncode
        return self.returncode


async def _noop_progress(_pct: int, _eta: int | None, _current: str | None) -> None:
    return None


def _stub_subprocess(monkeypatch: pytest.MonkeyPatch, captured_args: list[tuple[Any, ...]]) -> None:
    fake = _FakeProc(returncode=0)

    async def fake_create(*a: Any, **_kw: Any) -> _FakeProc:
        captured_args.append(a)
        return fake

    monkeypatch.setattr(handbrake.asyncio, "create_subprocess_exec", fake_create)


@pytest.mark.asyncio
async def test_cmd_order_with_encoder_args(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: list[tuple[Any, ...]] = []
    _stub_subprocess(monkeypatch, captured)
    output_path = tmp_path / "out.mkv"
    output_path.write_bytes(b"x")

    await transcode_handbrake(
        input_path=tmp_path / "in.mkv",
        output_path=output_path,
        preset_ref="Fast 1080p30",
        extra_args="--verbose 1",
        encoder_args=["--encoder", "x265"],
        progress_callback=_noop_progress,
    )

    assert len(captured) == 1
    cmd = list(captured[0])
    assert cmd == [
        "HandBrakeCLI",
        "-i",
        str(tmp_path / "in.mkv"),
        "-o",
        str(output_path),
        "--preset",
        "Fast 1080p30",
        "--encoder",
        "x265",
        "--verbose",
        "1",
    ]


@pytest.mark.asyncio
async def test_cmd_omits_encoder_args_when_empty(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    captured: list[tuple[Any, ...]] = []
    _stub_subprocess(monkeypatch, captured)
    output_path = tmp_path / "out.mkv"
    output_path.write_bytes(b"x")

    await transcode_handbrake(
        input_path=tmp_path / "in.mkv",
        output_path=output_path,
        preset_ref="Fast 1080p30",
        extra_args=None,
        encoder_args=[],
        progress_callback=_noop_progress,
    )

    assert len(captured) == 1
    cmd = list(captured[0])
    assert "--encoder" not in cmd
