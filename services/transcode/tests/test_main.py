"""Unit tests for arm_transcode.main helpers."""

from __future__ import annotations

import asyncio

import pytest

from arm_common import ContainerFormat, MediaType, TranscodeTool
from arm_common.schemas import TranscodePresetView
from arm_common.schemas.handbrake import HandbrakeSettings
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
        handbrake_settings=None,
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
async def test_run_encoder_progress_callback_records_frame_rates(monkeypatch, tmp_path) -> None:
    """Every field the engine reports lands on the ProgressState the heartbeat
    pump reads, the frame rates included (D-248)."""
    import arm_transcode.main as m

    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "vaapi_h265")
    monkeypatch.setenv("ARM_GPU_DEVICE", "/dev/dri/renderD128")

    async def fake_transcode_ffmpeg_vaapi(**kwargs):
        await kwargs["progress_callback"](42, 600, "1/2", 45.67, 23.45)
        kwargs["output_path"].write_bytes(b"z")
        return 1

    monkeypatch.setattr(m, "transcode_ffmpeg_vaapi", fake_transcode_ffmpeg_vaapi)
    state = ProgressState()
    await m._run_encoder(
        tool=TranscodeTool.HANDBRAKE,
        preset=_handbrake_preset(preset_ref=None),
        raw_input=tmp_path / "in.mkv",
        final_output=tmp_path / "out.mkv",
        duration_seconds=100,
        state=state,
        cancel_event=asyncio.Event(),
    )
    assert (state.eta_seconds, state.current_pass, state.fps, state.avg_fps) == (600, "1/2", 45.67, 23.45)
    assert state.pct == 100


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


def _clear_encoder_env(monkeypatch) -> None:
    for name in ("ARM_TRANSCODE_ENCODER", "ARM_GPU_VENDOR", "ARM_GPU_CODEC"):
        monkeypatch.delenv(name, raising=False)


def _audio_preset(*, preset_ref: str | None) -> TranscodePresetView:
    return _handbrake_preset(preset_ref=preset_ref).model_copy(
        update={"tool": TranscodeTool.ABCDE, "container": ContainerFormat.FLAC}
    )


async def _call_run_encoder(tmp_path, *, tool, preset, state=None, cancel_event=None, duration_seconds=100):
    import arm_transcode.main as m

    return await m._run_encoder(
        tool=tool,
        preset=preset,
        raw_input=tmp_path / "in.mkv",
        final_output=tmp_path / "out.mkv",
        duration_seconds=duration_seconds,
        state=state if state is not None else ProgressState(),
        cancel_event=cancel_event if cancel_event is not None else asyncio.Event(),
    )


@pytest.mark.asyncio
async def test_run_encoder_none_copies_without_consulting_encoder(monkeypatch, tmp_path) -> None:
    import arm_transcode.main as m

    calls: list[tuple] = []

    def fake_transcode_none(*args, **kwargs):
        calls.append((args, kwargs))
        return 1234

    def must_not_call():
        raise AssertionError("selected_encoder must not be consulted for tool=NONE")

    monkeypatch.setattr(m, "transcode_none", fake_transcode_none)
    monkeypatch.setattr(m, "selected_encoder", must_not_call)
    state = ProgressState()
    size = await _call_run_encoder(tmp_path, tool=TranscodeTool.NONE, preset=None, state=state)
    assert size == 1234
    assert calls == [((tmp_path / "in.mkv", tmp_path / "out.mkv"), {})]
    assert state.pct == 100


@pytest.mark.asyncio
async def test_run_encoder_handbrake_with_handbrake_engine_spec(monkeypatch, tmp_path) -> None:
    import arm_transcode.main as m

    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "nvenc_h265")
    called: dict = {}

    async def fake_transcode_handbrake(**kwargs):
        called.update(kwargs)
        kwargs["output_path"].write_bytes(b"h" * 7)
        return 7

    monkeypatch.setattr(m, "transcode_handbrake", fake_transcode_handbrake)
    state = ProgressState()
    preset = _handbrake_preset(preset_ref="HQ 1080p", extra_args="--foo")
    size = await _call_run_encoder(tmp_path, tool=TranscodeTool.HANDBRAKE, preset=preset, state=state)
    assert size == 7
    assert state.pct == 100
    assert called["input_path"] == tmp_path / "in.mkv"
    assert called["output_path"] == tmp_path / "out.mkv.arm-inprogress"
    assert called["preset_ref"] == "HQ 1080p"
    assert called["extra_args"] == "--foo"
    assert called["encoder_args"] == ["--encoder", "nvenc_h265"]
    assert (tmp_path / "out.mkv").read_bytes() == b"h" * 7
    assert not (tmp_path / "out.mkv.arm-inprogress").exists()


@pytest.mark.asyncio
async def test_run_encoder_handbrake_without_encoder_spec_passes_no_encoder_args(monkeypatch, tmp_path) -> None:
    import arm_transcode.main as m

    _clear_encoder_env(monkeypatch)
    called: dict = {}

    async def fake_transcode_handbrake(**kwargs):
        called.update(kwargs)
        kwargs["output_path"].write_bytes(b"h")
        return 1

    monkeypatch.setattr(m, "transcode_handbrake", fake_transcode_handbrake)
    await _call_run_encoder(tmp_path, tool=TranscodeTool.HANDBRAKE, preset=_handbrake_preset(preset_ref="Fast 1080p30"))
    assert called["encoder_args"] == []


@pytest.mark.asyncio
async def test_run_encoder_handbrake_requires_preset_ref(monkeypatch, tmp_path) -> None:
    _clear_encoder_env(monkeypatch)
    with pytest.raises(RuntimeError, match="transcode tool=handbrake requires a preset_ref"):
        await _call_run_encoder(tmp_path, tool=TranscodeTool.HANDBRAKE, preset=_handbrake_preset(preset_ref=None))


@pytest.mark.asyncio
async def test_run_encoder_handbrake_with_empty_settings_still_requires_preset_ref(monkeypatch, tmp_path) -> None:
    _clear_encoder_env(monkeypatch)
    preset = _handbrake_preset(preset_ref=None).model_copy(update={"handbrake_settings": HandbrakeSettings()})
    with pytest.raises(RuntimeError, match="transcode tool=handbrake requires a preset_ref"):
        await _call_run_encoder(tmp_path, tool=TranscodeTool.HANDBRAKE, preset=preset)


@pytest.mark.asyncio
async def test_run_encoder_abcde_with_settings_still_requires_preset_ref(monkeypatch, tmp_path) -> None:
    _clear_encoder_env(monkeypatch)
    settings = HandbrakeSettings(common={"PictureWidth": 1280})
    preset = _audio_preset(preset_ref=None).model_copy(update={"handbrake_settings": settings})
    with pytest.raises(RuntimeError, match="transcode tool=abcde requires a preset_ref"):
        await _call_run_encoder(tmp_path, tool=TranscodeTool.ABCDE, preset=preset)


@pytest.mark.asyncio
async def test_run_encoder_abcde_requires_a_preset(monkeypatch, tmp_path) -> None:
    _clear_encoder_env(monkeypatch)
    with pytest.raises(RuntimeError, match="transcode tool=abcde requires a preset_ref"):
        await _call_run_encoder(tmp_path, tool=TranscodeTool.ABCDE, preset=None)


@pytest.mark.asyncio
async def test_run_encoder_abcde_encodes_audio_with_preset_ref(monkeypatch, tmp_path) -> None:
    import arm_transcode.main as m

    _clear_encoder_env(monkeypatch)
    called: dict = {}

    async def fake_transcode_audio(**kwargs):
        called.update(kwargs)
        kwargs["output_path"].write_bytes(b"a" * 5)
        return 5

    monkeypatch.setattr(m, "transcode_audio", fake_transcode_audio)
    state = ProgressState()
    size = await _call_run_encoder(
        tmp_path,
        tool=TranscodeTool.ABCDE,
        preset=_audio_preset(preset_ref="mp3"),
        state=state,
        duration_seconds=321,
    )
    assert size == 5
    assert state.pct == 100
    assert called["input_path"] == tmp_path / "in.mkv"
    assert called["output_path"] == tmp_path / "out.mkv.arm-inprogress"
    assert called["preset_ref"] == "mp3"
    assert called["duration_seconds"] == 321
    assert (tmp_path / "out.mkv").read_bytes() == b"a" * 5


@pytest.mark.asyncio
async def test_run_encoder_abcde_empty_preset_ref_falls_back_to_container(monkeypatch, tmp_path) -> None:
    import arm_transcode.main as m

    _clear_encoder_env(monkeypatch)
    called: dict = {}

    async def fake_transcode_audio(**kwargs):
        called.update(kwargs)
        kwargs["output_path"].write_bytes(b"a")
        return 1

    monkeypatch.setattr(m, "transcode_audio", fake_transcode_audio)
    await _call_run_encoder(tmp_path, tool=TranscodeTool.ABCDE, preset=_audio_preset(preset_ref=""))
    assert called["preset_ref"] == "flac"


@pytest.mark.asyncio
async def test_run_encoder_abcde_ignores_vaapi_encoder(monkeypatch, tmp_path) -> None:
    import arm_transcode.main as m

    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "vaapi_h265")
    monkeypatch.setenv("ARM_GPU_DEVICE", "/dev/dri/renderD128")
    called: dict = {}

    async def fake_transcode_audio(**kwargs):
        called.update(kwargs)
        kwargs["output_path"].write_bytes(b"a")
        return 1

    async def must_not_call(**_kwargs):
        raise AssertionError("the vaapi route is HANDBRAKE-only")

    monkeypatch.setattr(m, "transcode_audio", fake_transcode_audio)
    monkeypatch.setattr(m, "transcode_ffmpeg_vaapi", must_not_call)
    size = await _call_run_encoder(tmp_path, tool=TranscodeTool.ABCDE, preset=_audio_preset(preset_ref="mp3"))
    assert size == 1
    assert called["preset_ref"] == "mp3"


@pytest.mark.asyncio
async def test_run_encoder_cancel_raises_from_progress_after_recording_state(monkeypatch, tmp_path) -> None:
    import arm_transcode.main as m

    _clear_encoder_env(monkeypatch)

    async def fake_transcode_handbrake(**kwargs):
        await kwargs["progress_callback"](10, None, None, None, None)
        kwargs["output_path"].write_bytes(b"h")
        return 1

    monkeypatch.setattr(m, "transcode_handbrake", fake_transcode_handbrake)
    cancel_event = asyncio.Event()
    cancel_event.set()
    state = ProgressState()
    with pytest.raises(m.CancelRequested, match="task.cancel received"):
        await _call_run_encoder(
            tmp_path,
            tool=TranscodeTool.HANDBRAKE,
            preset=_handbrake_preset(preset_ref="Fast 1080p30"),
            state=state,
            cancel_event=cancel_event,
        )
    assert state.pct == 10
    assert not (tmp_path / "out.mkv").exists()


@pytest.mark.asyncio
async def test_run_encoder_unknown_tool_raises(monkeypatch, tmp_path) -> None:
    import types

    _clear_encoder_env(monkeypatch)
    bogus = types.SimpleNamespace(value="bogus")
    with pytest.raises(RuntimeError, match="unknown transcode tool=bogus"):
        await _call_run_encoder(
            tmp_path,
            tool=bogus,  # type: ignore[arg-type]
            preset=_handbrake_preset(preset_ref="x"),
        )


async def test_progress_recorder_records_all_fields_while_not_cancelled() -> None:
    import arm_transcode.main as m

    state = ProgressState()
    on_progress = m._progress_recorder(state, asyncio.Event())

    result = await on_progress(42, 90, "pass 1", 24.5, 23.0)

    assert result is None
    assert (state.pct, state.eta_seconds, state.current_pass, state.fps, state.avg_fps) == (
        42,
        90,
        "pass 1",
        24.5,
        23.0,
    )


async def test_progress_recorder_records_then_raises_once_cancelled() -> None:
    import arm_transcode.main as m

    state = ProgressState()
    cancel_event = asyncio.Event()
    cancel_event.set()
    on_progress = m._progress_recorder(state, cancel_event)

    with pytest.raises(m.CancelRequested, match="task.cancel received"):
        await on_progress(7, None, None, 1.5, 1.0)

    assert (state.pct, state.eta_seconds, state.current_pass, state.fps, state.avg_fps) == (7, None, None, 1.5, 1.0)


def test_require_gpu_device_returns_the_configured_path(monkeypatch: pytest.MonkeyPatch) -> None:
    import arm_transcode.main as m

    monkeypatch.setenv("ARM_GPU_DEVICE", "/dev/dri/renderD128")

    assert m._require_gpu_device() == "/dev/dri/renderD128"


def test_require_gpu_device_raises_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    import arm_transcode.main as m

    monkeypatch.delenv("ARM_GPU_DEVICE", raising=False)

    with pytest.raises(RuntimeError, match="ffmpeg_vaapi encoder requires ARM_GPU_DEVICE"):
        m._require_gpu_device()


def test_require_gpu_device_raises_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    import arm_transcode.main as m

    monkeypatch.setenv("ARM_GPU_DEVICE", "")

    with pytest.raises(RuntimeError, match="ffmpeg_vaapi encoder requires ARM_GPU_DEVICE"):
        m._require_gpu_device()


def test_main_runs_the_task_when_no_mode_flag_is_given(monkeypatch: pytest.MonkeyPatch) -> None:
    from arm_transcode import main as m

    async def fake_run() -> int:
        return 7

    monkeypatch.setattr(m.sys, "argv", ["arm_transcode.main"])
    monkeypatch.setattr(m, "run", fake_run)
    assert m.main() == 7


def test_dump_schema_mode_needs_no_backend_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from arm_transcode import main as m

    calls: list[str] = []
    monkeypatch.setattr(m.sys, "argv", ["arm_transcode.main", "--dump-schema"])
    monkeypatch.setattr(m, "dump_schema", lambda: calls.append("dump") or 0)
    monkeypatch.setattr(m, "run", lambda: pytest.fail("must not start the task"))
    assert m.main() == 0
    assert calls == ["dump"]
