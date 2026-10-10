"""Unit tests for arm_transcode.main helpers."""

from __future__ import annotations

import asyncio

import pytest

from arm_common import ContainerFormat, MediaType, TranscodeTool
from arm_common.schemas import TranscodePresetView
from arm_transcode.heartbeat import ProgressState
from arm_transcode.main import _MAX_ERROR_CHARS, _clip_error


def test_clip_error_passes_short_messages_through() -> None:
    msg = "HandBrakeCLI exited rc=3\nstderr tail:\nDriver does not support nvenc"
    assert _clip_error(msg) == msg


def test_clip_error_keeps_the_tail_not_the_head() -> None:
    # The decisive encoder error is the LAST line; the historical str(exc)[:500]
    # kept the head and dropped exactly this line. Verify we keep the tail.
    head = "x" * (_MAX_ERROR_CHARS * 2)
    msg = head + "\nDriver does not support the required nvenc API version"
    clipped = _clip_error(msg)
    assert len(clipped) <= _MAX_ERROR_CHARS + len("…(truncated)…\n")
    assert clipped.startswith("…(truncated)…\n")
    assert "Driver does not support the required nvenc API version" in clipped


def test_clip_error_at_exact_boundary_is_unchanged() -> None:
    msg = "y" * _MAX_ERROR_CHARS
    assert _clip_error(msg) == msg


def test_probe_device_mode_prints_json(monkeypatch, capsys) -> None:
    import json

    import arm_transcode.main as m

    monkeypatch.setattr(m.sys, "argv", ["arm_transcode", "--probe-device"])
    monkeypatch.setenv("ARM_GPU_VENDOR", "qsv")
    monkeypatch.setenv("ARM_GPU_DEVICE", "/dev/dri/renderD129")
    monkeypatch.setattr(m, "probe_device", lambda v, d: {"verified": ["h265"], "errors": {}})
    rc = m.main()
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert json.loads(out) == {"verified": ["h265"], "errors": {}}
    assert "\n" not in out  # exactly one JSON line


def test_probe_device_mode_requires_env(monkeypatch, capsys) -> None:
    import arm_transcode.main as m

    monkeypatch.setattr(m.sys, "argv", ["arm_transcode", "--probe-device"])
    monkeypatch.delenv("ARM_GPU_VENDOR", raising=False)
    monkeypatch.delenv("ARM_GPU_DEVICE", raising=False)
    rc = m.main()
    assert rc == 2
    assert capsys.readouterr().err.strip()


def test_probe_device_mode_reports_setup_error(monkeypatch, capsys) -> None:
    import arm_transcode.main as m

    monkeypatch.setattr(m.sys, "argv", ["arm_transcode", "--probe-device"])
    monkeypatch.setenv("ARM_GPU_VENDOR", "qsv")
    monkeypatch.setenv("ARM_GPU_DEVICE", "/dev/dri/renderD129")

    def boom(vendor, device):
        raise m.ProbeSetupError("could not generate the test clip: clip failed")

    monkeypatch.setattr(m, "probe_device", boom)
    rc = m.main()
    assert rc == 3
    assert "could not generate the test clip" in capsys.readouterr().err


def test_probe_device_mode_rejects_unknown_vendor(monkeypatch, capsys) -> None:
    import arm_transcode.main as m

    monkeypatch.setattr(m.sys, "argv", ["arm_transcode", "--probe-device"])
    monkeypatch.setenv("ARM_GPU_VENDOR", "not-a-real-vendor")
    monkeypatch.setenv("ARM_GPU_DEVICE", "/dev/dri/renderD129")

    def must_not_call(vendor, device):
        raise AssertionError("probe_device should not run for an unknown vendor")

    monkeypatch.setattr(m, "probe_device", must_not_call)
    rc = m.main()
    assert rc == 2
    err = capsys.readouterr().err
    assert "not-a-real-vendor" in err
    assert "qsv" in err  # names a valid vendor


def test_probe_encoders_mode_is_deprecated_and_empty(monkeypatch, capsys) -> None:
    import json

    import arm_transcode.main as m

    monkeypatch.setattr(m.sys, "argv", ["arm_transcode", "--probe-encoders"])
    rc = m.main()
    assert rc == 0
    captured = capsys.readouterr()
    assert json.loads(captured.out.strip()) == {}
    assert "deprecated" in captured.err.lower()
    assert "--probe-device" in captured.err


def _handbrake_preset(*, preset_ref: str | None, extra_args: str | None = None) -> TranscodePresetView:
    return TranscodePresetView(
        id="p1",
        name="AMD HEVC",
        media_type=MediaType.MOVIE,
        is_builtin=True,
        tool=TranscodeTool.HANDBRAKE,
        preset_ref=preset_ref,
        preset_json=None,
        container=ContainerFormat.MKV,
        encoder="vaapi_h265",
        extra_args=extra_args,
        created_by_user_id=None,
        created_at=None,
        updated_at=None,
    )


@pytest.mark.asyncio
async def test_run_encoder_ffmpeg_vaapi_routes_without_preset_ref(monkeypatch, tmp_path) -> None:
    """A HandBrake-tool preset with a vaapi encoder and no preset_ref routes
    to transcode_ffmpeg_vaapi instead of raising the "requires a preset_ref"
    guard meant for HandBrake/ABCDE."""
    import arm_transcode.main as m

    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "vaapi_h265")
    monkeypatch.setenv("ARM_GPU_DEVICE", "/dev/dri/renderD128")

    called: dict = {}

    async def fake_transcode_ffmpeg_vaapi(**kwargs):
        called.update(kwargs)
        kwargs["output_path"].write_bytes(b"z" * 99)
        return 99

    monkeypatch.setattr(m, "transcode_ffmpeg_vaapi", fake_transcode_ffmpeg_vaapi)

    preset = _handbrake_preset(preset_ref=None)
    state = ProgressState()
    size = await m._run_encoder(
        tool=TranscodeTool.HANDBRAKE,
        preset=preset,
        raw_input=tmp_path / "in.mkv",
        final_output=tmp_path / "out.mkv",
        duration_seconds=100,
        state=state,
        cancel_event=asyncio.Event(),
    )
    assert size == 99
    assert state.pct == 100
    assert called["device"] == "/dev/dri/renderD128"
    assert called["container"] == ContainerFormat.MKV
    assert called["spec"].id == "vaapi_h265"


@pytest.mark.asyncio
async def test_run_encoder_ffmpeg_vaapi_requires_gpu_device(monkeypatch, tmp_path) -> None:
    import arm_transcode.main as m

    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "vaapi_h265")
    monkeypatch.delenv("ARM_GPU_DEVICE", raising=False)

    async def must_not_call(**_kwargs):
        raise AssertionError("transcode_ffmpeg_vaapi should not be invoked without ARM_GPU_DEVICE")

    monkeypatch.setattr(m, "transcode_ffmpeg_vaapi", must_not_call)

    preset = _handbrake_preset(preset_ref=None)
    state = ProgressState()
    with pytest.raises(RuntimeError, match="ffmpeg_vaapi encoder requires ARM_GPU_DEVICE"):
        await m._run_encoder(
            tool=TranscodeTool.HANDBRAKE,
            preset=preset,
            raw_input=tmp_path / "in.mkv",
            final_output=tmp_path / "out.mkv",
            duration_seconds=100,
            state=state,
            cancel_event=asyncio.Event(),
        )
