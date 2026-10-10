"""Engine seam: which encoder the dispatcher asked for, and how the
HandBrake engine turns an `EncoderSpec` into `--encoder` args."""

from __future__ import annotations

import pytest

from arm_common.encoders import get_encoder
from arm_transcode.engines import selected_encoder
from arm_transcode.engines.handbrake_engine import encoder_args


def test_selected_encoder_from_new_env(monkeypatch):
    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "qsv_h265")
    assert selected_encoder().id == "qsv_h265"


def test_selected_encoder_legacy_env(monkeypatch):
    monkeypatch.delenv("ARM_TRANSCODE_ENCODER", raising=False)
    monkeypatch.setenv("ARM_GPU_VENDOR", "nvenc")
    monkeypatch.setenv("ARM_GPU_CODEC", "h264")
    assert selected_encoder().id == "nvenc_h264"


def test_selected_encoder_legacy_vaapi_has_no_handbrake_mapping(monkeypatch):
    monkeypatch.delenv("ARM_TRANSCODE_ENCODER", raising=False)
    monkeypatch.setenv("ARM_GPU_VENDOR", "vaapi")
    monkeypatch.setenv("ARM_GPU_CODEC", "h265")
    assert selected_encoder() is None


def test_selected_encoder_none(monkeypatch):
    for k in ("ARM_TRANSCODE_ENCODER", "ARM_GPU_VENDOR", "ARM_GPU_CODEC"):
        monkeypatch.delenv(k, raising=False)
    assert selected_encoder() is None


def test_selected_encoder_unknown_id_raises(monkeypatch):
    monkeypatch.setenv("ARM_TRANSCODE_ENCODER", "vce_h265")
    with pytest.raises(ValueError):
        selected_encoder()


@pytest.mark.parametrize(
    ("eid", "args"),
    [
        ("preset", []),
        ("cpu_h265", ["--encoder", "x265"]),
        ("qsv_av1", ["--encoder", "qsv_av1"]),
    ],
)
def test_encoder_args(eid, args):
    assert encoder_args(get_encoder(eid)) == args


def test_encoder_args_none():
    assert encoder_args(None) == []
