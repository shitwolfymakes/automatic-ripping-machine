"""The HandBrakeCLI argv the transcoder launches, with and without a preset's HandBrake settings."""

from __future__ import annotations

import asyncio
import dataclasses
import functools
import json
from pathlib import Path
from typing import Any

import pytest

import arm_transcode.main as m
from arm_common import ContainerFormat, MediaType, TranscodeTool
from arm_common.handbrake_schema.loader import load_schema
from arm_common.handbrake_schema.materialise import UnknownBasePreset
from arm_common.handbrake_schema.types import HandbrakeSchema
from arm_common.schemas import TranscodePresetView
from arm_common.schemas.handbrake import HandbrakeSettings
from arm_transcode import handbrake_preset_file
from arm_transcode.handbrake_preset_file import SettingsRejected, write_preset_file
from arm_transcode.heartbeat import ProgressState

FIXTURE = Path(__file__).parents[3] / "packages/arm_common/tests/fixtures/handbrake-schema-1.11.1.json"

# The Plex export's settings as stored (spec 4.3): common keys plus an nvenc_h264 block.
PLEX = HandbrakeSettings(
    common={
        "PictureWidth": 1280,
        "PictureHeight": 720,
        "VideoFramerateMode": "cfr",
        "AudioList": [{"AudioEncoder": "av_aac", "AudioMixdown": "5point1", "AudioBitrate": 384}],
    },
    encoders={
        "nvenc_h264": {
            "bit_depth": 8,
            "VideoPreset": "slower",
            "VideoProfile": "main",
            "VideoLevel": "4.0",
            "VideoQualitySlider": 18,
        }
    },
)


@functools.cache
def _schema() -> HandbrakeSchema:
    return load_schema(json.loads(FIXTURE.read_text()))


class _Proc:
    """A HandBrakeCLI run that exits 0 at once with no output."""

    def __init__(self) -> None:
        self.stdout = asyncio.StreamReader()
        self.stdout.feed_eof()
        self.stderr = asyncio.StreamReader()
        self.stderr.feed_eof()

    async def wait(self) -> int:
        return 0


class _Spawns:
    """Records each launched argv and writes the output file HandBrake would."""

    def __init__(self) -> None:
        self.argvs: list[list[str]] = []
        self.preset_files: list[dict[str, Any]] = []

    async def __call__(self, *argv: str, **_kwargs: Any) -> _Proc:
        self.argvs.append(list(argv))
        if "--preset-import-file" in argv:
            self.preset_files.append(json.loads(Path(argv[argv.index("--preset-import-file") + 1]).read_text()))
        Path(argv[argv.index("-o") + 1]).write_bytes(b"x")
        return _Proc()


@pytest.fixture
def spawns(monkeypatch: pytest.MonkeyPatch) -> _Spawns:
    recorder = _Spawns()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", recorder)
    return recorder


@pytest.fixture
def baked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(handbrake_preset_file, "load_baked_schema", _schema)


def _no_schema_expected() -> None:
    raise AssertionError("a settings-less preset must not consult the baked schema")


def _preset(**update: Any) -> TranscodePresetView:
    base = TranscodePresetView(
        id="tpr_builtin_plex_1080p_h265",
        name="Plex 1080p H.265",
        media_type=MediaType.MOVIE,
        is_builtin=True,
        tool=TranscodeTool.HANDBRAKE,
        preset_ref="H.265 MKV 1080p30",
        handbrake_settings=None,
        container=ContainerFormat.MKV,
        encoder="cpu_h265",
        extra_args=None,
        created_by_user_id=None,
        created_at=None,
        updated_at=None,
    )
    return base.model_copy(update=update)


async def _run(tmp_path: Path, preset: TranscodePresetView) -> int:
    return await m._run_encoder(
        tool=TranscodeTool.HANDBRAKE,
        preset=preset,
        raw_input=tmp_path / "in.mkv",
        final_output=tmp_path / "out.mkv",
        duration_seconds=100,
        state=ProgressState(),
        cancel_event=asyncio.Event(),
    )


@pytest.mark.asyncio
async def test_no_settings_argv_is_todays(monkeypatch, tmp_path, spawns) -> None:
    """M11: the builtin Plex H.265 preset launches exactly today's argv."""
    monkeypatch.setattr(handbrake_preset_file, "load_baked_schema", _no_schema_expected)
    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "cpu_h265")
    await _run(tmp_path, _preset(extra_args="--quality 20"))
    assert spawns.argvs == [
        [
            "HandBrakeCLI",
            "-i",
            str(tmp_path / "in.mkv"),
            "-o",
            str(tmp_path / "out.mkv.arm-inprogress"),
            "--preset",
            "H.265 MKV 1080p30",
            "--encoder",
            "x265",
            "--quality",
            "20",
        ]
    ]


def _import_argv(tmp_path: Path, preset_file: str, *tail: str) -> list[str]:
    return [
        "HandBrakeCLI",
        "-i",
        str(tmp_path / "in.mkv"),
        "-o",
        str(tmp_path / "out.mkv.arm-inprogress"),
        "--preset-import-file",
        preset_file,
        "--preset",
        "arm",
        *tail,
    ]


def _launched_preset_file(spawns: _Spawns) -> str:
    argv = spawns.argvs[0]
    return argv[argv.index("--preset-import-file") + 1]


@pytest.mark.asyncio
async def test_empty_settings_keep_todays_argv(monkeypatch, tmp_path, spawns) -> None:
    monkeypatch.setattr(handbrake_preset_file, "load_baked_schema", _no_schema_expected)
    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "cpu_h265")
    await _run(tmp_path, _preset(handbrake_settings=HandbrakeSettings(encoders={"x265": {}})))
    assert spawns.argvs[0][5:] == ["--preset", "H.265 MKV 1080p30", "--encoder", "x265"]


@pytest.mark.asyncio
async def test_plex_on_x264_sets_only_the_encoder(monkeypatch, tmp_path, spawns, baked) -> None:
    """Spike run 1: the block is for another family, so only --encoder x264 follows the import."""
    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "cpu_h264")
    await _run(tmp_path, _preset(preset_ref=None, encoder="cpu_h264", handbrake_settings=PLEX))
    assert spawns.argvs == [_import_argv(tmp_path, _launched_preset_file(spawns), "--encoder", "x264")]


@pytest.mark.asyncio
async def test_plex_on_nvenc_h264_adds_block_flags_then_extra_args(monkeypatch, tmp_path, spawns, baked) -> None:
    """Spike run 6 shape: the block's encoder keys become flags; extra_args still come last."""
    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "nvenc_h264")
    preset = _preset(preset_ref=None, encoder="nvenc_h264", handbrake_settings=PLEX, extra_args="-q 22")
    await _run(tmp_path, preset)
    flags = ["--encoder", "nvenc_h264", "--encoder-preset", "slower", "--encoder-profile", "main"]
    flags += ["--encoder-level", "4.0", "-q", "22"]
    assert spawns.argvs == [_import_argv(tmp_path, _launched_preset_file(spawns), *flags)]


@pytest.mark.asyncio
async def test_x265_ten_bit_block_picks_the_ten_bit_encoder(monkeypatch, tmp_path, spawns, baked) -> None:
    """Spike run 7: a 10-bit x265 block runs x265_10bit."""
    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "cpu_h265")
    settings = HandbrakeSettings(encoders={"x265": {"bit_depth": 10}})
    await _run(tmp_path, _preset(preset_ref=None, handbrake_settings=settings))
    assert spawns.argvs == [_import_argv(tmp_path, _launched_preset_file(spawns), "--encoder", "x265_10bit")]


@pytest.mark.asyncio
async def test_preset_encoder_runs_without_encoder_flag(monkeypatch, tmp_path, spawns, baked) -> None:
    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "preset")
    await _run(tmp_path, _preset(encoder="preset", handbrake_settings=PLEX))
    assert spawns.argvs == [_import_argv(tmp_path, _launched_preset_file(spawns))]


@pytest.mark.asyncio
async def test_preset_encoder_applies_the_base_family_block_without_encoder_flag(
    monkeypatch, tmp_path, spawns, baked
) -> None:
    """Ruling 24: the base's x265 block is written and flagged; the base keeps its own encoder."""
    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "preset")
    settings = HandbrakeSettings(encoders={"x265": {"VideoPreset": "slow", "VideoQualitySlider": 20}})
    await _run(tmp_path, _preset(encoder="preset", handbrake_settings=settings))
    assert spawns.argvs == [_import_argv(tmp_path, _launched_preset_file(spawns), "--encoder-preset", "slow")]
    [preset] = spawns.preset_files[0]["PresetList"]
    assert preset["VideoQualitySlider"] == 20
    assert preset["VideoEncoder"] == "x265_10bit"


@pytest.mark.asyncio
async def test_preset_encoder_without_base_has_no_block_flags(monkeypatch, tmp_path, spawns, baked) -> None:
    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "preset")
    settings = HandbrakeSettings(encoders={"x265": {"VideoPreset": "slow"}})
    await _run(tmp_path, _preset(preset_ref=None, encoder="preset", handbrake_settings=settings))
    assert spawns.argvs == [_import_argv(tmp_path, _launched_preset_file(spawns))]


@pytest.mark.asyncio
async def test_preset_encoder_invalid_base_family_block_is_rejected(monkeypatch, tmp_path, spawns, baked) -> None:
    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "preset")
    bad = HandbrakeSettings(encoders={"x265": {"VideoPreset": "bogus"}})
    with pytest.raises(SettingsRejected, match="bogus"):
        await _run(tmp_path, _preset(encoder="preset", handbrake_settings=bad))
    assert spawns.argvs == []


@pytest.mark.asyncio
async def test_preset_file_is_written_to_a_temp_work_dir_and_removed(monkeypatch, tmp_path, spawns, baked) -> None:
    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "cpu_h264")
    await _run(tmp_path, _preset(preset_ref=None, encoder="cpu_h264", handbrake_settings=PLEX))
    launched = Path(_launched_preset_file(spawns))
    assert launched.name == "arm-preset.json"
    assert launched.parent.name.startswith("arm-hb-")
    assert not launched.parent.exists()
    [preset] = spawns.preset_files[0]["PresetList"]
    assert preset["PresetName"] == "arm"
    assert preset["VideoHWDecode"] == 0
    assert preset["PictureWidth"] == 1280


@pytest.mark.asyncio
async def test_invalid_block_is_rejected_before_launch(monkeypatch, tmp_path, spawns, baked) -> None:
    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "nvenc_h264")
    bad = HandbrakeSettings(encoders={"nvenc_h264": {"VideoPreset": "bogus", "VideoProfile": "nope"}})
    with pytest.raises(SettingsRejected, match=r"^HandBrake settings rejected: .*bogus.*; .*nope"):
        await _run(tmp_path, _preset(preset_ref=None, encoder="nvenc_h264", handbrake_settings=bad))
    assert spawns.argvs == []


@pytest.mark.asyncio
async def test_unknown_base_fails_before_launch(monkeypatch, tmp_path, spawns, baked) -> None:
    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "preset")
    with pytest.raises(UnknownBasePreset, match="has no built-in preset named 'Nope'"):
        await _run(tmp_path, _preset(preset_ref="Nope", encoder="preset", handbrake_settings=PLEX))
    assert spawns.argvs == []


@pytest.mark.asyncio
async def test_settings_without_baked_schema_fail_before_launch(monkeypatch, tmp_path, spawns) -> None:
    monkeypatch.setattr(handbrake_preset_file, "load_baked_schema", lambda: None)
    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "cpu_h264")
    with pytest.raises(RuntimeError, match="^this transcode image has no HandBrake schema; rebuild or pull it$"):
        await _run(tmp_path, _preset(preset_ref=None, encoder="cpu_h264", handbrake_settings=PLEX))
    assert spawns.argvs == []


def test_write_preset_file_writes_arm_preset_json(tmp_path) -> None:
    path = write_preset_file(tmp_path, {"PresetList": [{"PresetName": "arm"}]})
    assert path == tmp_path / "arm-preset.json"
    assert json.loads(path.read_text()) == {"PresetList": [{"PresetName": "arm"}]}


def _stale_schema() -> HandbrakeSchema:
    """The baked schema of an image that predates `PictureWidth` (spec 4.10 version skew)."""
    schema = _schema()
    keys = {name: spec for name, spec in schema.keys.items() if name != "PictureWidth"}
    return dataclasses.replace(schema, keys=keys)


@pytest.mark.asyncio
async def test_common_key_unknown_to_the_baked_schema_is_rejected(monkeypatch, tmp_path, spawns) -> None:
    """M5: libhb would drop the key silently (spike run 5); the transcoder fails the task naming it."""
    monkeypatch.setattr(handbrake_preset_file, "load_baked_schema", _stale_schema)
    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "cpu_h264")
    with pytest.raises(SettingsRejected, match=r"^HandBrake settings rejected: .*PictureWidth"):
        await _run(tmp_path, _preset(preset_ref=None, encoder="cpu_h264", handbrake_settings=PLEX))
    assert spawns.argvs == []


@pytest.mark.asyncio
async def test_common_and_block_issues_are_joined(monkeypatch, tmp_path, spawns) -> None:
    monkeypatch.setattr(handbrake_preset_file, "load_baked_schema", _stale_schema)
    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "nvenc_h264")
    bad = PLEX.model_copy(update={"encoders": {"nvenc_h264": {"VideoPreset": "bogus"}}})
    with pytest.raises(SettingsRejected, match=r"^HandBrake settings rejected: .*PictureWidth.*; .*bogus"):
        await _run(tmp_path, _preset(preset_ref=None, encoder="nvenc_h264", handbrake_settings=bad))
    assert spawns.argvs == []


@pytest.mark.asyncio
async def test_valid_common_and_block_launch(monkeypatch, tmp_path, spawns, baked) -> None:
    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "nvenc_h264")
    await _run(tmp_path, _preset(preset_ref=None, encoder="nvenc_h264", handbrake_settings=PLEX))
    assert len(spawns.argvs) == 1
