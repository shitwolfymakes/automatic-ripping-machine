"""Tests for the encoder-first GPU claim, keyed on the preset's catalog encoder.

A GPU row is eligible for a codec only when it is enabled, has been probed,
and its probe verified that codec; rows currently being re-probed are never
claimed.

| encoder kind  | eligible GPU free | eligible GPUs busy | no eligible GPU      |
|---------------|-------------------|--------------------|----------------------|
| preset / cpu  | CPU               | CPU                | CPU                  |
| any_<codec>   | best-ranked GPU   | queue              | CPU (cpu_<codec>)    |
| <vendor>_<c>  | that vendor's GPU | queue              | task fails           |

Plus: stale-claim sweep releases the GPU it held; a spawn failure releases
the claim; the worker env carries the resolved catalog encoder id.
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
    Session,
    SessionApplication,
    SessionApplicationStatus,
    TranscodePreset,
    TranscodeTask,
    TranscodeTaskStatus,
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
        "ARM_TRANSCODE_IMAGE": "arm-transcode:latest",
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
    encoder: str = "any_h265",
    gpus: list[tuple[GpuVendor, GpuStatus, list[str], str | None]] | None = None,
) -> FakeSession:
    """Stand up a FakeSession with one queued task, one session pointing at
    a TranscodePreset with the given catalog encoder, plus the supplied
    GPU rows.
    """
    db = FakeSession()
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_x",
            session_id="ses_x",
            job_id="job_01JZXR7K3M5Q8N4VWA00000001",
            status=SessionApplicationStatus.QUEUED,
            overwrite=False,
        )
    ]
    db.rows["sessions"] = [
        Session(
            id="ses_x",
            name="Movie to Plex",
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
            encoder=encoder,
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
                device_path=f"/dev/dri/renderD{128 + i}" if vendor != GpuVendor.NVENC else f"nvidia://{i}",
                encoder_kinds=kinds,
                status=status,
                claimed_by_task_id=claimed_by,
                probed_at=datetime.now(UTC),
            )
        )
    return db


def _capture_hub() -> tuple[WSHub, list[dict[str, Any]]]:
    hub = WSHub()
    sent: list[dict[str, Any]] = []

    async def _capture(**kwargs: Any) -> None:
        sent.append(kwargs)

    hub.emit = _capture  # type: ignore[method-assign]
    return hub, sent


async def _claim(db: FakeSession, disp: TranscodeDispatcher | None = None) -> Any:
    disp = disp or TranscodeDispatcher(_settings(), _db_factory(db), MagicMock(), WSHub())
    task = db.rows["transcode_tasks"][0]
    preset = db.rows["transcode_presets"][0]
    return await disp._claim_gpu_for_task(db, task, preset)


# --- CPU-only host (no gpus rows) ---------------------------------------------


@pytest.mark.parametrize("encoder", ["any_h265", "cpu_h265", "preset"])
async def test_no_gpus_on_host_spawns_cpu(encoder: str) -> None:
    db = _build_db(encoder=encoder, gpus=[])
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    spawned = await disp.spawn_pending(db)
    assert spawned == 1
    kwargs = docker.containers.run.call_args.kwargs
    assert "ARM_GPU_VENDOR" not in kwargs["environment"]
    assert "devices" not in kwargs
    assert "runtime" not in kwargs


# --- CPU encoder ----------------------------------------------------------------


async def test_cpu_encoder_with_available_gpu_spawns_cpu() -> None:
    db = _build_db(
        encoder="cpu_h265",
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
        encoder="any_h265",
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
    # No render GID configured → no RENDER_GID env; the entrypoint derives the
    # gid from the mounted render node itself (derivation is the default).
    assert "RENDER_GID" not in kwargs["environment"]
    # GPU is claimed.
    assert db.rows["gpus"][0].status == GpuStatus.BUSY
    assert db.rows["gpus"][0].claimed_by_task_id == "txt_1"


async def test_qsv_available_uses_devices_injection() -> None:
    db = _build_db(
        encoder="any_h265",
        gpus=[(GpuVendor.QSV, GpuStatus.AVAILABLE, ["h264", "h265"], None)],
    )
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    await disp.spawn_pending(db)
    kwargs = docker.containers.run.call_args.kwargs
    assert kwargs["environment"]["ARM_GPU_VENDOR"] == "qsv"
    assert "devices" in kwargs


async def test_render_gid_passed_as_env_for_qsv() -> None:
    """With ARM_RENDER_GID set, VAAPI/QSV spawns get RENDER_GID in the env as a
    forced override — the entrypoint honors it over its own derivation from
    the mounted node."""
    db = _build_db(
        encoder="any_h265",
        gpus=[(GpuVendor.QSV, GpuStatus.AVAILABLE, ["h264", "h265"], None)],
    )
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(ARM_RENDER_GID="110"), _db_factory(db), docker, WSHub())
    await disp.spawn_pending(db)
    kwargs = docker.containers.run.call_args.kwargs
    assert kwargs["environment"]["RENDER_GID"] == "110"
    assert kwargs["devices"] == ["/dev/dri/renderD128:/dev/dri/renderD128:rwm"]


# --- NVENC: runtime + device_requests injection ------------------------------


async def test_nvenc_available_uses_runtime_and_device_requests() -> None:
    db = _build_db(
        encoder="any_h265",
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


# --- GPU encoder matrix -----------------------------------------------


async def test_any_encoder_with_busy_gpu_leaves_task_queued() -> None:
    db = _build_db(
        encoder="any_h265",
        gpus=[(GpuVendor.VAAPI, GpuStatus.BUSY, ["h264", "h265"], "other-task")],
    )
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    spawned = await disp.spawn_pending(db)
    assert spawned == 0
    docker.containers.run.assert_not_called()
    # Task is still queued (next tick will retry).
    assert db.rows["transcode_tasks"][0].status == TranscodeTaskStatus.QUEUED


async def test_any_encoder_no_codec_match_falls_back_to_cpu() -> None:
    """Preset wants h265 but the only GPU only verified h264 -> CPU spawn,
    not queue: no GPU on the host has this codec."""
    db = _build_db(
        encoder="any_h265",
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


# --- Vendor encoder: busy GPU → queue ---------------------------------------


async def test_vendor_encoder_with_busy_gpu_leaves_task_queued() -> None:
    db = _build_db(
        encoder="qsv_h265",
        gpus=[(GpuVendor.QSV, GpuStatus.BUSY, ["h264", "h265"], "other-task")],
    )
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    spawned = await disp.spawn_pending(db)
    assert spawned == 0
    docker.containers.run.assert_not_called()
    assert db.rows["transcode_tasks"][0].status == TranscodeTaskStatus.QUEUED


# --- Stale-claim sweep also releases the GPU ---------------------------------


async def test_stale_claim_sweep_releases_gpu() -> None:
    db = _build_db(
        encoder="any_h265",
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
        encoder="any_h265",
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


async def test_uncommitted_claim_is_marked_in_process_until_commit() -> None:
    db = _build_db(encoder="any_h265", gpus=[(GpuVendor.VAAPI, GpuStatus.AVAILABLE, ["h265"], None)])
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    during_spawn: list[set[str]] = []
    docker.containers.run.side_effect = lambda **_kw: during_spawn.append(set(disp.claimed_gpu_ids))
    assert await disp.spawn_pending(db) == 1
    assert during_spawn == [{"gpu_0"}]  # visible while the spawn runs, before the commit
    assert disp.claimed_gpu_ids == set()  # released once committed


async def test_uncommitted_claim_marker_released_after_spawn_failure() -> None:
    db = _build_db(encoder="any_h265", gpus=[(GpuVendor.VAAPI, GpuStatus.AVAILABLE, ["h265"], None)])
    docker = MagicMock()
    docker.containers.run.side_effect = RuntimeError("docker daemon unhappy")
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    assert await disp.spawn_pending(db) == 0
    assert disp.claimed_gpu_ids == set()


async def test_uncommitted_claim_marker_released_when_the_release_commit_fails() -> None:
    db = _build_db(encoder="any_h265", gpus=[(GpuVendor.VAAPI, GpuStatus.AVAILABLE, ["h265"], None)])
    docker = MagicMock()

    def _spawn_then_break_commits(**_kw: Any) -> None:
        db.commit_raises = RuntimeError("db gone")
        raise RuntimeError("docker daemon unhappy")

    docker.containers.run.side_effect = _spawn_then_break_commits
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    with pytest.raises(RuntimeError, match="db gone"):
        await disp.spawn_pending(db)
    assert disp.claimed_gpu_ids == set()


async def test_cpu_spawn_leaves_no_claim_marker() -> None:
    db = _build_db(encoder="cpu_h265", gpus=[])
    disp = TranscodeDispatcher(_settings(), _db_factory(db), MagicMock(), WSHub())
    assert await disp.spawn_pending(db) == 1
    assert disp.claimed_gpu_ids == set()


# --- enabled switch + deterministic vendor ordering ---------------------------


async def test_disabled_gpu_is_never_claimed() -> None:
    db = _build_db(
        encoder="any_h265",
        gpus=[(GpuVendor.QSV, GpuStatus.AVAILABLE, ["h264", "h265"], None)],
    )
    db.rows["gpus"][0].enabled = False
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    spawned = await disp.spawn_pending(db)
    # Only disabled silicon advertises the codec -> CPU spawn, GPU untouched.
    assert spawned == 1
    kwargs = docker.containers.run.call_args.kwargs
    assert "ARM_GPU_VENDOR" not in kwargs["environment"]
    assert db.rows["gpus"][0].status == GpuStatus.AVAILABLE
    assert db.rows["gpus"][0].claimed_by_task_id is None


async def test_claim_prefers_vendor_order_not_row_order() -> None:
    # vaapi row FIRST: row order must not decide; nvenc > qsv > vaapi.
    db = _build_db(
        encoder="any_h265",
        gpus=[
            (GpuVendor.VAAPI, GpuStatus.AVAILABLE, ["h264", "h265"], None),
            (GpuVendor.QSV, GpuStatus.AVAILABLE, ["h264", "h265"], None),
        ],
    )
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    await disp.spawn_pending(db)
    kwargs = docker.containers.run.call_args.kwargs
    assert kwargs["environment"]["ARM_GPU_VENDOR"] == "qsv"
    claimed = [g for g in db.rows["gpus"] if g.claimed_by_task_id == "txt_1"]
    assert len(claimed) == 1 and claimed[0].vendor == GpuVendor.QSV


async def test_disabled_preferred_vendor_falls_through_to_next() -> None:
    db = _build_db(
        encoder="any_h265",
        gpus=[
            (GpuVendor.NVENC, GpuStatus.AVAILABLE, ["h264", "h265"], None),
            (GpuVendor.VAAPI, GpuStatus.AVAILABLE, ["h264", "h265"], None),
        ],
    )
    db.rows["gpus"][0].enabled = False  # nvenc disabled by the operator
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    await disp.spawn_pending(db)
    kwargs = docker.containers.run.call_args.kwargs
    assert kwargs["environment"]["ARM_GPU_VENDOR"] == "vaapi"


# --- Encoder-first claim matrix ------------------------------------------------


async def test_pinned_encoder_queues_on_busy_device_never_other_vendor() -> None:
    """A VAAPI row that verified nothing sits free next to a busy QSV row that
    verified h265: a qsv_h265 preset waits for the QSV device and never lands
    on the VAAPI one."""
    db = _build_db(
        encoder="qsv_h265",
        gpus=[
            (GpuVendor.VAAPI, GpuStatus.AVAILABLE, [], None),
            (GpuVendor.QSV, GpuStatus.BUSY, ["h265"], "other-task"),
        ],
    )
    assignment = await _claim(db)
    assert assignment.action == "queue"
    assert assignment.gpu is None
    assert assignment.encoder is not None and assignment.encoder.id == "qsv_h265"
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    assert await disp.spawn_pending(db) == 0
    docker.containers.run.assert_not_called()
    assert db.rows["gpus"][0].status == GpuStatus.AVAILABLE
    assert db.rows["gpus"][0].claimed_by_task_id is None
    assert db.rows["transcode_tasks"][0].status == TranscodeTaskStatus.QUEUED


async def test_any_encoder_skips_device_without_verified_codec() -> None:
    db = _build_db(
        encoder="any_h265",
        gpus=[
            (GpuVendor.NVENC, GpuStatus.AVAILABLE, ["h264"], None),
            (GpuVendor.QSV, GpuStatus.AVAILABLE, ["h265"], None),
        ],
    )
    assignment = await _claim(db)
    assert assignment.action == "spawn"
    assert assignment.gpu is not None and assignment.gpu.vendor == GpuVendor.QSV
    assert assignment.encoder.id == "qsv_h265"
    assert db.rows["gpus"][1].claimed_by_task_id == "txt_1"
    assert db.rows["gpus"][0].claimed_by_task_id is None


async def test_any_encoder_prefers_vendor_rank() -> None:
    db = _build_db(
        encoder="any_h265",
        gpus=[
            (GpuVendor.QSV, GpuStatus.AVAILABLE, ["h265"], None),
            (GpuVendor.NVENC, GpuStatus.AVAILABLE, ["h265"], None),
        ],
    )
    assignment = await _claim(db)
    assert assignment.gpu is not None and assignment.gpu.vendor == GpuVendor.NVENC
    assert assignment.encoder.id == "nvenc_h265"


async def test_any_encoder_without_eligible_device_falls_back_to_cpu_encoder() -> None:
    db = _build_db(
        encoder="any_h265",
        gpus=[
            (GpuVendor.QSV, GpuStatus.AVAILABLE, ["h265"], None),
            (GpuVendor.VAAPI, GpuStatus.AVAILABLE, ["h265"], None),
        ],
    )
    db.rows["gpus"][0].probed_at = None  # never probed
    db.rows["gpus"][1].enabled = False  # operator-disabled
    assignment = await _claim(db)
    assert assignment.action == "spawn"
    assert assignment.gpu is None
    assert assignment.encoder.id == "cpu_h265"
    assert all(g.status == GpuStatus.AVAILABLE for g in db.rows["gpus"])


async def test_any_encoder_all_eligible_busy_queues() -> None:
    db = _build_db(
        encoder="any_h265",
        gpus=[
            (GpuVendor.QSV, GpuStatus.BUSY, ["h265"], "t_a"),
            (GpuVendor.NVENC, GpuStatus.BUSY, ["h265"], "t_b"),
        ],
    )
    assignment = await _claim(db)
    assert assignment.action == "queue"
    assert assignment.gpu is None


async def test_vaapi_encoder_claims_eligible_vaapi_row() -> None:
    db = _build_db(
        encoder="vaapi_h265",
        gpus=[
            (GpuVendor.NVENC, GpuStatus.AVAILABLE, ["h265"], None),
            (GpuVendor.VAAPI, GpuStatus.AVAILABLE, ["h265"], None),
        ],
    )
    assignment = await _claim(db)
    assert assignment.action == "spawn"
    assert assignment.gpu is not None and assignment.gpu.vendor == GpuVendor.VAAPI
    assert assignment.encoder.id == "vaapi_h265"


async def test_pinned_encoder_without_eligible_device_fails() -> None:
    db = _build_db(
        encoder="qsv_h265",
        gpus=[(GpuVendor.QSV, GpuStatus.AVAILABLE, ["h264"], None)],
    )
    assignment = await _claim(db)
    assert assignment.action == "fail"
    assert assignment.gpu is None
    assert assignment.reason == "no enabled device has verified qsv_h265; re-probe or enable it in Settings > GPUs"


async def test_spawn_pending_fails_task_when_pinned_encoder_vanished() -> None:
    db = _build_db(encoder="qsv_h265", gpus=[])
    hub, sent = _capture_hub()
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, hub)
    assert await disp.spawn_pending(db) == 0
    docker.containers.run.assert_not_called()
    task = db.rows["transcode_tasks"][0]
    assert task.status == TranscodeTaskStatus.FAILED
    assert task.last_error == "no enabled device has verified qsv_h265; re-probe or enable it in Settings > GPUs"
    failed = [e for e in sent if e["event_type"] == "task.failed"]
    assert len(failed) == 1
    assert failed[0]["payload"]["task_id"] == "txt_1"
    assert failed[0]["payload"]["last_error"] == task.last_error
    assert db.rows["session_applications"][0].status == SessionApplicationStatus.FAILED
    assert any(e["event_type"] == "session.failed" for e in sent)


async def test_probing_device_is_never_claimed() -> None:
    db = _build_db(
        encoder="any_h265",
        gpus=[
            (GpuVendor.NVENC, GpuStatus.AVAILABLE, ["h265"], None),
            (GpuVendor.VAAPI, GpuStatus.AVAILABLE, ["h265"], None),
        ],
    )
    disp = TranscodeDispatcher(_settings(), _db_factory(db), MagicMock(), WSHub())
    disp.probing_gpu_ids.add("gpu_0")
    assignment = await _claim(db, disp)
    assert assignment.gpu is not None and assignment.gpu.id == "gpu_1"
    assert db.rows["gpus"][0].claimed_by_task_id is None


async def test_pinned_encoder_whose_only_device_is_probing_queues() -> None:
    db = _build_db(
        encoder="qsv_h265",
        gpus=[(GpuVendor.QSV, GpuStatus.AVAILABLE, ["h265"], None)],
    )
    disp = TranscodeDispatcher(_settings(), _db_factory(db), MagicMock(), WSHub())
    disp.probing_gpu_ids.add("gpu_0")
    assignment = await _claim(db, disp)
    assert assignment.action == "queue"
    assert assignment.gpu is None
    assert db.rows["gpus"][0].status == GpuStatus.AVAILABLE


async def test_any_encoder_whose_only_device_is_probing_queues() -> None:
    db = _build_db(
        encoder="any_h265",
        gpus=[(GpuVendor.NVENC, GpuStatus.AVAILABLE, ["h265"], None)],
    )
    disp = TranscodeDispatcher(_settings(), _db_factory(db), MagicMock(), WSHub())
    disp.probing_gpu_ids.add("gpu_0")
    assignment = await _claim(db, disp)
    assert assignment.action == "queue"


@pytest.mark.parametrize(("encoder", "resolved"), [("preset", None), ("cpu_h264", "cpu_h264")])
async def test_preset_and_cpu_encoders_spawn_without_gpu(encoder: str, resolved: str | None) -> None:
    db = _build_db(
        encoder=encoder,
        gpus=[(GpuVendor.NVENC, GpuStatus.AVAILABLE, ["h264", "h265"], None)],
    )
    assignment = await _claim(db)
    assert assignment.action == "spawn"
    assert assignment.gpu is None
    assert (assignment.encoder.id if assignment.encoder else None) == resolved
    assert db.rows["gpus"][0].status == GpuStatus.AVAILABLE


async def test_no_preset_spawns_without_gpu_or_encoder() -> None:
    db = _build_db(gpus=[(GpuVendor.NVENC, GpuStatus.AVAILABLE, ["h265"], None)])
    disp = TranscodeDispatcher(_settings(), _db_factory(db), MagicMock(), WSHub())
    assignment = await disp._claim_gpu_for_task(db, db.rows["transcode_tasks"][0], None)
    assert (assignment.gpu, assignment.encoder, assignment.action) == (None, None, "spawn")


def _add_second_task(db: FakeSession, *, encoder: str) -> None:
    """A second queued task (created after txt_1) on its own session + preset."""
    db.rows["session_applications"].append(
        SessionApplication(
            id="sap_y",
            session_id="ses_y",
            job_id="job_01JZXR7K3M5Q8N4VWA00000002",
            status=SessionApplicationStatus.QUEUED,
            overwrite=False,
        )
    )
    db.rows["sessions"].append(
        Session(
            id="ses_y",
            name="Other",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            rip_preset_id="rpr_x",
            transcode_preset_id="tpr_y",
            output_path_template="{title}/{title}.mkv",
        )
    )
    db.rows["transcode_presets"].append(
        TranscodePreset(
            id="tpr_y",
            name="Other",
            media_type=MediaType.MOVIE,
            is_builtin=False,
            tool=TranscodeTool.HANDBRAKE,
            preset_ref="H.265 MKV 1080p30",
            container=ContainerFormat.MKV,
            encoder=encoder,
        )
    )
    db.rows["transcode_tasks"].append(
        TranscodeTask(
            id="txt_2",
            session_application_id="sap_y",
            source_track_id="trk_2",
            status=TranscodeTaskStatus.QUEUED,
            attempts=0,
            progress_pct=0,
            output_path="Other/Other.mkv",
            created_at=datetime.now(UTC) + timedelta(seconds=1),
        )
    )


async def test_unknown_encoder_fails_only_that_task() -> None:
    db = _build_db(encoder="bogus_codec", gpus=[])
    _add_second_task(db, encoder="cpu_h265")
    hub, sent = _capture_hub()
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, hub)
    assert await disp.spawn_pending(db) == 1  # must not raise
    first, second = db.rows["transcode_tasks"]
    assert first.status == TranscodeTaskStatus.FAILED
    assert first.last_error == "preset tpr_x has unknown encoder 'bogus_codec'"
    assert any(e["event_type"] == "task.failed" and e["payload"]["task_id"] == "txt_1" for e in sent)
    # The later task still spawned, on the CPU encoder it asked for.
    env = docker.containers.run.call_args.kwargs["environment"]
    assert env["ARM_TRANSCODE_TASK_ID"] == "txt_2"
    assert env["ARM_TRANSCODE_ENCODER"] == "cpu_h265"
    assert second.status == TranscodeTaskStatus.QUEUED


async def test_fail_path_error_rolls_back_and_tick_continues() -> None:
    db = _build_db(encoder="qsv_h265", gpus=[])
    _add_second_task(db, encoder="cpu_h265")
    hub = WSHub()

    async def _boom(**_kwargs: Any) -> None:
        raise RuntimeError("ws down")

    hub.emit = _boom  # type: ignore[method-assign]
    rollbacks: list[int] = []
    real_rollback = db.rollback

    async def _spy_rollback() -> None:
        rollbacks.append(1)
        await real_rollback()

    db.rollback = _spy_rollback  # type: ignore[method-assign]
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, hub)
    assert await disp.spawn_pending(db) == 1  # must not raise
    assert rollbacks == [1]
    assert docker.containers.run.call_args.kwargs["environment"]["ARM_TRANSCODE_TASK_ID"] == "txt_2"


# --- Worker env contract ---------------------------------------------------------


async def test_env_for_pinned_gpu_claim_carries_encoder_and_legacy_gpu_vars() -> None:
    db = _build_db(
        encoder="qsv_h265",
        gpus=[(GpuVendor.QSV, GpuStatus.AVAILABLE, ["h264", "h265"], None)],
    )
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    assert await disp.spawn_pending(db) == 1
    env = docker.containers.run.call_args.kwargs["environment"]
    assert env["ARM_TRANSCODE_ENCODER"] == "qsv_h265"
    assert env["ARM_GPU_VENDOR"] == "qsv"
    assert env["ARM_GPU_DEVICE"] == "/dev/dri/renderD128"
    assert env["ARM_GPU_CODEC"] == "h265"


async def test_env_for_any_encoder_cpu_fallback_has_no_gpu_vars() -> None:
    db = _build_db(encoder="any_h265", gpus=[])
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    assert await disp.spawn_pending(db) == 1
    env = docker.containers.run.call_args.kwargs["environment"]
    assert env["ARM_TRANSCODE_ENCODER"] == "cpu_h265"
    assert not [k for k in env if k.startswith("ARM_GPU_")]


async def test_env_for_preset_encoder_has_no_encoder_var() -> None:
    db = _build_db(encoder="preset", gpus=[])
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    assert await disp.spawn_pending(db) == 1
    env = docker.containers.run.call_args.kwargs["environment"]
    assert "ARM_TRANSCODE_ENCODER" not in env
    assert not [k for k in env if k.startswith("ARM_GPU_")]


# --- max_parallel_transcodes from operator config -----------------------------


async def test_max_parallel_read_from_config_row() -> None:
    from arm_backend.seeders import CONFIG_SINGLETON_ID
    from arm_common import Config

    db = _build_db(gpus=[])
    db.rows["config"] = [Config(id=CONFIG_SINGLETON_ID, max_parallel_transcodes=0)]
    docker = MagicMock()
    # env says 2, operator config says 0 -> config wins, nothing spawns.
    disp = TranscodeDispatcher(_settings(MAX_PARALLEL_TRANSCODES=2), _db_factory(db), docker, WSHub())
    spawned = await disp.spawn_pending(db)
    assert spawned == 0
    docker.containers.run.assert_not_called()


async def test_max_parallel_falls_back_to_env_when_unseeded() -> None:
    from arm_backend.seeders import CONFIG_SINGLETON_ID
    from arm_common import Config

    db = _build_db(gpus=[])
    db.rows["config"] = [Config(id=CONFIG_SINGLETON_ID, max_parallel_transcodes=None)]
    docker = MagicMock()
    disp = TranscodeDispatcher(_settings(MAX_PARALLEL_TRANSCODES=1), _db_factory(db), docker, WSHub())
    spawned = await disp.spawn_pending(db)
    assert spawned == 1


# --- per-vendor image selection -------------------------------------------------


async def test_qsv_spawn_uses_derived_variant_when_it_exists() -> None:
    db = _build_db(
        encoder="any_h265",
        gpus=[(GpuVendor.QSV, GpuStatus.AVAILABLE, ["h264", "h265"], None)],
    )
    docker = MagicMock()  # every image "exists" (default MagicMock never raises)
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker, WSHub())
    await disp.spawn_pending(db)
    assert docker.containers.run.call_args.kwargs["image"] == "arm-transcode:latest-intel"


async def test_vaapi_spawn_falls_back_to_base_when_variant_missing() -> None:
    import docker.errors as docker_errors

    db = _build_db(
        encoder="any_h265",
        gpus=[(GpuVendor.VAAPI, GpuStatus.AVAILABLE, ["h264", "h265"], None)],
    )
    docker_client = MagicMock()
    docker_client.images.get.side_effect = docker_errors.ImageNotFound("nope")
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker_client, WSHub())
    await disp.spawn_pending(db)
    assert docker_client.containers.run.call_args.kwargs["image"] == "arm-transcode:latest"


async def test_nvenc_spawn_uses_base_image_and_never_checks_a_variant() -> None:
    db = _build_db(
        encoder="any_h265",
        gpus=[(GpuVendor.NVENC, GpuStatus.AVAILABLE, ["h264", "h265"], None)],
    )
    docker_client = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker_client, WSHub())
    await disp.spawn_pending(db)
    assert docker_client.containers.run.call_args.kwargs["image"] == "arm-transcode:latest"
    # NVENC has no derived variant, so the image-exists probe never runs.
    docker_client.images.get.assert_not_called()


async def test_cpu_spawn_uses_base_image() -> None:
    db = _build_db(encoder="preset", gpus=[])
    docker_client = MagicMock()
    disp = TranscodeDispatcher(_settings(), _db_factory(db), docker_client, WSHub())
    await disp.spawn_pending(db)
    assert docker_client.containers.run.call_args.kwargs["image"] == "arm-transcode:latest"


async def test_qsv_spawn_uses_override_without_checking_variant_exists() -> None:
    db = _build_db(
        encoder="any_h265",
        gpus=[(GpuVendor.QSV, GpuStatus.AVAILABLE, ["h264", "h265"], None)],
    )
    docker_client = MagicMock()
    disp = TranscodeDispatcher(
        _settings(ARM_TRANSCODE_IMAGE_QSV="custom-qsv:latest"), _db_factory(db), docker_client, WSHub()
    )
    await disp.spawn_pending(db)
    assert docker_client.containers.run.call_args.kwargs["image"] == "custom-qsv:latest"
    docker_client.images.get.assert_not_called()
