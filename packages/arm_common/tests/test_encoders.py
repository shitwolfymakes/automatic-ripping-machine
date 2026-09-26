from datetime import UTC, datetime

import pytest

from arm_common import Gpu, GpuVendor, TranscodeTool
from arm_common.encoders import (
    ENCODERS,
    PRESET_ENCODER_ID,
    VENDOR_RANK,
    cpu_encoder_for,
    encoder_allowed_for_tool,
    get_encoder,
    gpu_encoder_for,
    gpu_encoders_for_vendor,
    gpu_is_eligible,
)

EXPECTED_IDS = [
    "preset",
    "cpu_h264",
    "cpu_h265",
    "cpu_av1",
    "any_h264",
    "any_h265",
    "any_av1",
    "qsv_h264",
    "qsv_h265",
    "qsv_av1",
    "nvenc_h264",
    "nvenc_h265",
    "nvenc_av1",
    "vaapi_h264",
    "vaapi_h265",
    "vaapi_av1",
]


def test_catalog_ids_and_order() -> None:
    assert list(ENCODERS) == EXPECTED_IDS


@pytest.mark.parametrize(
    ("encoder_id", "engine", "engine_encoder", "kind", "vendor", "codec"),
    [
        ("preset", "handbrake", None, "preset", None, None),
        ("cpu_h265", "handbrake", "x265", "cpu", None, "h265"),
        ("cpu_av1", "handbrake", "svt_av1", "cpu", None, "av1"),
        ("any_h264", "handbrake", None, "any", None, "h264"),
        ("qsv_av1", "handbrake", "qsv_av1", "gpu", GpuVendor.QSV, "av1"),
        ("nvenc_h265", "handbrake", "nvenc_h265", "gpu", GpuVendor.NVENC, "h265"),
        ("vaapi_h265", "ffmpeg_vaapi", "hevc_vaapi", "gpu", GpuVendor.VAAPI, "h265"),
        ("vaapi_h264", "ffmpeg_vaapi", "h264_vaapi", "gpu", GpuVendor.VAAPI, "h264"),
        ("vaapi_av1", "ffmpeg_vaapi", "av1_vaapi", "gpu", GpuVendor.VAAPI, "av1"),
    ],
)
def test_entry_fields(encoder_id, engine, engine_encoder, kind, vendor, codec) -> None:
    spec = get_encoder(encoder_id)
    assert (spec.engine, spec.engine_encoder, spec.kind, spec.vendor, spec.codec) == (
        engine,
        engine_encoder,
        kind,
        vendor,
        codec,
    )
    assert spec.label


def test_get_encoder_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown encoder"):
        get_encoder("vce_h265")


def test_tool_scope() -> None:
    assert encoder_allowed_for_tool("qsv_h265", TranscodeTool.HANDBRAKE)
    assert encoder_allowed_for_tool(PRESET_ENCODER_ID, TranscodeTool.ABCDE)
    assert encoder_allowed_for_tool(PRESET_ENCODER_ID, TranscodeTool.NONE)
    assert not encoder_allowed_for_tool("cpu_h265", TranscodeTool.ABCDE)
    assert not encoder_allowed_for_tool("vaapi_h265", TranscodeTool.NONE)
    assert not encoder_allowed_for_tool("bogus", TranscodeTool.HANDBRAKE)


def test_vendor_helpers() -> None:
    assert [e.id for e in gpu_encoders_for_vendor(GpuVendor.QSV)] == ["qsv_h264", "qsv_h265", "qsv_av1"]
    assert cpu_encoder_for("h265").id == "cpu_h265"
    assert gpu_encoder_for(GpuVendor.VAAPI, "h264").id == "vaapi_h264"
    assert gpu_encoder_for(GpuVendor.NVENC, "vp9") is None
    assert VENDOR_RANK == {GpuVendor.NVENC: 0, GpuVendor.QSV: 1, GpuVendor.VAAPI: 2}


def _gpu(**kw) -> Gpu:
    base = dict(
        vendor=GpuVendor.QSV,
        device_path="/dev/dri/renderD129",
        encoder_kinds=["h265"],
        enabled=True,
        probed_at=datetime.now(UTC),
    )
    base.update(kw)
    return Gpu(**base)


def test_eligibility() -> None:
    assert gpu_is_eligible(_gpu(), "h265")
    assert not gpu_is_eligible(_gpu(), "h264")
    assert not gpu_is_eligible(_gpu(enabled=False), "h265")
    assert not gpu_is_eligible(_gpu(probed_at=None), "h265")
    assert not gpu_is_eligible(_gpu(encoder_kinds=None), "h265")
