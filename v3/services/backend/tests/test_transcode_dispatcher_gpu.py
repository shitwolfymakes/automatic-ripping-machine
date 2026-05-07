"""Tests for the GPU dispatch matrix added in Phase 7b.

The matrix:

| hw_preference | matching GPU available | matching GPU busy | no matching GPU |
|---------------|-----------------------|-------------------|-----------------|
| cpu_only      | CPU                   | CPU               | CPU             |
| any           | GPU                   | CPU               | CPU             |
| NULL (default)| GPU                   | queue             | CPU             |

Plus: stale-claim sweep releases the GPU it held; a per-codec mismatch
keeps the task on CPU even if a GPU is available.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

from arm_backend.config import Settings  # noqa: E402
from arm_backend.transcode_dispatcher import TranscodeDispatcher  # noqa: E402
from arm_backend.ws import WSHub  # noqa: E402
from arm_common import (  # noqa: E402
    Gpu,
    GpuStatus,
    GpuVendor,
    HwPreference,
    Session,
    SessionApplication,
    SessionApplicationStatus,
    TranscodePreset,
    TranscodeTask,
    TranscodeTaskStatus,
    VideoCodec,
)
from arm_common.enums import ContainerFormat, MediaType, TranscodeTool  # noqa: E402
from tests._fakes import FakeSession  # noqa: E402


def _settings(**overrides: Any) -> Settings:
    base = {
        "DATABASE_URL": "postgresql://x:x@localhost/x",
        "ARM_SERVICE_TOKEN": "tok-service",
        "MAX_PARALLEL_TRANSCODES": 2,
        "ARM_TRANSCODE_STALE_THRESHOLD_SECONDS": 90,
        "ARM_TRANSCODE_MAX_ATTEMPTS": 3,
        "ARM_TRANSCODE_IMAGE": "arm-transcode:dev",
        "ARM_HOST_RAW_PATH": "/host/raw",
        "ARM_HOST_MEDIA_PATH": "/host/media",
        "ARM_HOST_LOGS_PATH": "/host/logs",
        "ARM_HOST_CERTS_PATH": "/host/certs",
        "ARM_DOCKER_NETWORK": "armv3_default",
        "ARM_TRANSCODE_DISPATCH_INTERVAL_SECONDS": 5,
    }
    base.update(overrides)
    return Settings.model_construct(**base)


def _db_factory(db: FakeSession) -> Any:
    class _Factory:
        def __call__(self) -> "_Factory":
            return self

        async def __aenter__(self) -> FakeSession:
            return db

        async def __aexit__(self, *exc: Any) -> None:
            return None

    return _Factory()


def _build_db(
    *,
    hw_preference: HwPreference | None,
    codec: VideoCodec | None = VideoCodec.H265,
    gpus: list[tuple[GpuVendor, GpuStatus, list[str], str | None]] | None = None,
) -> FakeSession:
    """Stand up a FakeSession with one queued task, one session pointing at
    a TranscodePreset with the given hw_preference + codec, plus the supplied
    GPU rows.
    """
    db = FakeSession()
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_x",
            session_id="ses_x",
            job_id="job_x",
            status=SessionApplicationStatus.QUEUED,
            overwrite=False,
        )
    ]
    db.rows["sessions"] = [
        Session(
            id="ses_x",
            name="Movie → Plex",
            media_type=MediaType.MOVIE,
            is_builtin=True,
            rip_preset_id="rpr_x",
            transcode_preset_id="tpr_x",
            output_path_template="{title}/{title}.mkv",
        )
    ]
    db.rows["transcode_presets"] = [
        TranscodePreset(
            id="tpr_x",
            name="Plex 1080p",
            media_type=MediaType.MOVIE,
            is_builtin=True,
            tool=TranscodeTool.HANDBRAKE,
            preset_ref="H.265 MKV 1080p30",
            container=ContainerFormat.MKV,
            codec=codec,
            hw_preference=hw_preference,
        )
    ]
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_1",
            session_application_id="sap_x",
            source_track_id="trk_1",
            status=TranscodeTaskStatus.QUEUED,
            attempts=0,
            progress_pct=0,
            output_path="Iron Man (2008)/Iron Man.mkv",
            created_at=datetime.now(UTC),
        )
    ]
    db.rows["gpus"] = []
    for i, (vendor, status, kinds, claimed_by) in enumerate(gpus or []):
        db.rows["gpus"].append(
            Gpu(
                id=f"gpu_{i}",
                vendor=vendor,
                device_path="/dev/dri/renderD128" if vendor != GpuVendor.NVENC else "nvidia://0",
                encoder_kinds=kinds,
                status=status,
                claimed_by_task_id=claimed_by,
            )
        )
    return db


# --- CPU-only host (no gpus rows) ---------------------------------------------


@pytest.mark.parametrize("hw", [None, HwPreference.ANY, HwPreference.CPU_ONLY])
async def test_no_gpus_on_host_always_spawns_cpu(hw: HwPreference | None) -> None:
    db = _build_db(hw_preference=hw, gpus=[])
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    spawned = await disp.spawn_pending(db)
    assert spawned == 1
    kwargs = docker.containers.run.call_args.kwargs
    assert "ARM_GPU_VENDOR" not in kwargs["environment"]
    assert "devices" not in kwargs
    assert "runtime" not in kwargs


# --- CPU_ONLY ----------------------------------------------------------------


async def test_cpu_only_with_available_gpu_spawns_cpu() -> None:
    db = _build_db(
        hw_preference=HwPreference.CPU_ONLY,
        gpus=[(GpuVendor.VAAPI, GpuStatus.AVAILABLE, ["h264", "h265"], None)],
    )
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    await disp.spawn_pending(db)
    kwargs = docker.containers.run.call_args.kwargs
    assert "ARM_GPU_VENDOR" not in kwargs["environment"]
    # GPU was untouched.
    assert db.rows["gpus"][0].status == GpuStatus.AVAILABLE
    assert db.rows["gpus"][0].claimed_by_task_id is None


# --- VAAPI / QSV: devices= injection -----------------------------------------


async def test_vaapi_available_claims_gpu_and_injects_devices() -> None:
    db = _build_db(
        hw_preference=None,
        codec=VideoCodec.H265,
        gpus=[(GpuVendor.VAAPI, GpuStatus.AVAILABLE, ["h264", "h265"], None)],
    )
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    await disp.spawn_pending(db)
    kwargs = docker.containers.run.call_args.kwargs
    assert kwargs["environment"]["ARM_GPU_VENDOR"] == "vaapi"
    assert kwargs["environment"]["ARM_GPU_CODEC"] == "h265"
    assert kwargs["environment"]["ARM_GPU_DEVICE"] == "/dev/dri/renderD128"
    assert kwargs["devices"] == ["/dev/dri/renderD128:/dev/dri/renderD128:rwm"]
    # GPU is claimed.
    assert db.rows["gpus"][0].status == GpuStatus.BUSY
    assert db.rows["gpus"][0].claimed_by_task_id == "txt_1"


async def test_qsv_available_uses_devices_injection() -> None:
    db = _build_db(
        hw_preference=HwPreference.ANY,
        gpus=[(GpuVendor.QSV, GpuStatus.AVAILABLE, ["h264", "h265"], None)],
    )
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    await disp.spawn_pending(db)
    kwargs = docker.containers.run.call_args.kwargs
    assert kwargs["environment"]["ARM_GPU_VENDOR"] == "qsv"
    assert "devices" in kwargs


# --- NVENC: runtime + device_requests injection ------------------------------


async def test_nvenc_available_uses_runtime_and_device_requests() -> None:
    db = _build_db(
        hw_preference=None,
        gpus=[(GpuVendor.NVENC, GpuStatus.AVAILABLE, ["h264", "h265"], None)],
    )
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    await disp.spawn_pending(db)
    kwargs = docker.containers.run.call_args.kwargs
    assert kwargs["environment"]["ARM_GPU_VENDOR"] == "nvenc"
    assert kwargs["runtime"] == "nvidia"
    assert "device_requests" in kwargs
    assert kwargs["device_requests"]  # non-empty
    # Pin to the specific GPU index (`nvidia://0` → DeviceIDs=["0"]). The
    # docker daemon rejects requests that set BOTH Count > 0 AND DeviceIDs
    # ("cannot set both Count and DeviceIDs on device request") — docker-py's
    # DeviceRequest always serialises Count, but defaults it to 0, so we
    # just need to never pass `count=1` when device_ids is set.
    req = kwargs["device_requests"][0]
    assert req["DeviceIDs"] == ["0"]
    assert req.get("Count", 0) == 0


# --- NULL hw_preference matrix -----------------------------------------------


async def test_null_pref_with_busy_gpu_leaves_task_queued() -> None:
    db = _build_db(
        hw_preference=None,
        gpus=[(GpuVendor.VAAPI, GpuStatus.BUSY, ["h264", "h265"], "other-task")],
    )
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    spawned = await disp.spawn_pending(db)
    assert spawned == 0
    docker.containers.run.assert_not_called()
    # Task is still queued (next tick will retry).
    assert db.rows["transcode_tasks"][0].status == TranscodeTaskStatus.QUEUED


async def test_null_pref_no_codec_match_falls_back_to_cpu() -> None:
    """Preset wants h265 but the only GPU only advertises h264 → CPU spawn,
    not queue (per arch doc: NULL means CPU only when no GPU on host has
    this codec)."""
    db = _build_db(
        hw_preference=None,
        codec=VideoCodec.H265,
        gpus=[(GpuVendor.VAAPI, GpuStatus.AVAILABLE, ["h264"], None)],
    )
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    spawned = await disp.spawn_pending(db)
    assert spawned == 1
    kwargs = docker.containers.run.call_args.kwargs
    assert "ARM_GPU_VENDOR" not in kwargs["environment"]
    # The GPU should NOT have been claimed.
    assert db.rows["gpus"][0].status == GpuStatus.AVAILABLE


# --- ANY preference: busy GPU → CPU instead of queue --------------------------


async def test_any_pref_with_busy_gpu_spawns_cpu() -> None:
    db = _build_db(
        hw_preference=HwPreference.ANY,
        gpus=[(GpuVendor.VAAPI, GpuStatus.BUSY, ["h264", "h265"], "other-task")],
    )
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    spawned = await disp.spawn_pending(db)
    assert spawned == 1
    kwargs = docker.containers.run.call_args.kwargs
    assert "ARM_GPU_VENDOR" not in kwargs["environment"]


# --- Stale-claim sweep also releases the GPU ---------------------------------


async def test_stale_claim_sweep_releases_gpu() -> None:
    db = _build_db(
        hw_preference=None,
        gpus=[(GpuVendor.VAAPI, GpuStatus.BUSY, ["h264", "h265"], "txt_stale")],
    )
    # Replace the queued task with a stale in-progress one held by the GPU.
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_stale",
            session_application_id="sap_x",
            source_track_id="trk_1",
            status=TranscodeTaskStatus.IN_PROGRESS,
            attempts=1,
            progress_pct=50,
            claimed_by="dead-host",
            claim_heartbeat_at=datetime.now(UTC) - timedelta(seconds=300),
            output_path="x.mkv",
        )
    ]
    disp = TranscodeDispatcher(_settings(), _db_factory(db), MagicMock(), WSHub())
    touched = await disp.sweep_stale_claims(db)
    assert touched == 1
    # GPU is released back to AVAILABLE.
    gpu = db.rows["gpus"][0]
    assert gpu.status == GpuStatus.AVAILABLE
    assert gpu.claimed_by_task_id is None
    # Task reverted to queued (attempts=1 < MAX_ATTEMPTS=3 so it's not hard-failed).
    assert db.rows["transcode_tasks"][0].status == TranscodeTaskStatus.QUEUED


# --- Spawn failure rolls back the GPU claim ----------------------------------


async def test_spawn_failure_releases_gpu_claim() -> None:
    db = _build_db(
        hw_preference=None,
        gpus=[(GpuVendor.VAAPI, GpuStatus.AVAILABLE, ["h264", "h265"], None)],
    )
    docker = MagicMock()
    docker.containers.run.side_effect = RuntimeError("docker daemon unhappy")
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    spawned = await disp.spawn_pending(db)
    assert spawned == 0
    # GPU claim was rolled back so the next dispatch tick can retry.
    assert db.rows["gpus"][0].status == GpuStatus.AVAILABLE
    assert db.rows["gpus"][0].claimed_by_task_id is None
