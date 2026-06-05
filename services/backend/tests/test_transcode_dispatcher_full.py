"""Residual TranscodeDispatcher coverage: run-loop error/timeout, _tick,
spawn slots<=0, _resolve_preset_for_task None paths, the GPU run-kwarg
injector (every vendor + NVENC idx/no-idx + unknown), sweep_arm_inprogress
unlink OSError, and cancel_running's row-gone / docker-stop-error paths.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

from arm_backend import transcode_dispatcher as tdmod  # noqa: E402
from arm_backend.transcode_dispatcher import TranscodeDispatcher  # noqa: E402
from arm_backend.ws import WSHub  # noqa: E402
from arm_common import (  # noqa: E402
    Gpu,
    GpuStatus,
    GpuVendor,
    SessionApplication,
    SessionApplicationStatus,
    TranscodeTask,
    TranscodeTaskStatus,
)

from tests._fakes import FakeSession  # noqa: E402
from tests.test_transcode_dispatcher import _db_factory, _settings  # noqa: E402


def _disp(db: FakeSession, **sett: Any) -> TranscodeDispatcher:
    return TranscodeDispatcher(
        settings=_settings(**sett),
        db_factory=_db_factory(db),
        docker_client=MagicMock(),
        hub=WSHub(),
    )


async def test_run_loop_swallows_tick_error(monkeypatch: pytest.MonkeyPatch) -> None:
    d = _disp(FakeSession())
    d._tick_interval = 0.01
    n = 0

    async def _boom() -> None:
        nonlocal n
        n += 1
        d.stop()  # stop after the first tick so the loop exits deterministically
        raise RuntimeError("tick boom")

    monkeypatch.setattr(d, "_tick", _boom)
    await asyncio.wait_for(d.run(), timeout=2.0)
    assert n == 1  # tick ran, raised, was swallowed, loop exited on stop


async def test_tick_runs_sweep_and_spawn() -> None:
    db = FakeSession()
    db.rows["transcode_tasks"] = []
    db.rows["gpus"] = []
    await _disp(db)._tick()  # no rows → both helpers no-op cleanly


async def test_spawn_pending_no_slots() -> None:
    db = FakeSession()
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_run",
            session_application_id="sap",
            source_track_id="trk",
            status=TranscodeTaskStatus.IN_PROGRESS,
            progress_pct=10,
            attempts=1,
        )
    ]
    spawned = await _disp(db, MAX_PARALLEL_TRANSCODES=1).spawn_pending(db)
    assert spawned == 0


async def test_resolve_preset_none_paths() -> None:
    db = FakeSession()
    d = _disp(db)
    task = TranscodeTask(
        id="txt_1",
        session_application_id="sap_missing",
        source_track_id="trk",
        status=TranscodeTaskStatus.QUEUED,
        progress_pct=0,
        attempts=0,
    )
    # application missing → None
    assert await d._resolve_preset_for_task(db, task) is None

    # application present but session has no transcode preset → None
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_missing",
            session_id="ses_x",
            job_id="job_01JZXR7K3M5Q8N4VWA00000001",
            status=SessionApplicationStatus.QUEUED,
            overwrite=False,
        )
    ]
    db.rows["sessions"] = []
    assert await d._resolve_preset_for_task(db, task) is None


def _gpu(vendor: GpuVendor, device_path: str) -> Gpu:
    return Gpu(id="gpu_1", vendor=vendor, device_path=device_path, encoder_kinds=["h264"], status=GpuStatus.AVAILABLE)


def test_inject_gpu_kwargs_vaapi_qsv() -> None:
    d = _disp(FakeSession())
    for vendor in (GpuVendor.VAAPI, GpuVendor.QSV):
        kw: dict[str, Any] = {}
        d._inject_gpu_run_kwargs(kw, _gpu(vendor, "/dev/dri/renderD128"))
        assert kw["devices"] == ["/dev/dri/renderD128:/dev/dri/renderD128:rwm"]


def test_inject_gpu_kwargs_nvenc_with_and_without_index() -> None:
    d = _disp(FakeSession())
    with_idx: dict[str, Any] = {}
    d._inject_gpu_run_kwargs(with_idx, _gpu(GpuVendor.NVENC, "nvidia://1"))
    assert with_idx["runtime"] == "nvidia"
    assert with_idx["device_requests"]

    no_idx: dict[str, Any] = {}
    d._inject_gpu_run_kwargs(no_idx, _gpu(GpuVendor.NVENC, "nvidia://"))
    assert no_idx["runtime"] == "nvidia"


def test_inject_gpu_kwargs_unknown_vendor_noop() -> None:
    d = _disp(FakeSession())
    kw: dict[str, Any] = {}
    # A vendor that's neither VAAPI/QSV nor NVENC → both ifs fall through.
    fake = _gpu(GpuVendor.NVENC, "x")
    object.__setattr__(fake, "vendor", "unknown-vendor")
    d._inject_gpu_run_kwargs(kw, fake)
    assert kw == {}


async def test_sweep_arm_inprogress_unlink_oserror(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    orphan = tmp_path / "movie.mkv.arm-inprogress"
    orphan.write_text("partial")

    real_unlink = Path.unlink

    def _bad_unlink(self: Path, *a: Any, **k: Any) -> None:
        if self.name.endswith(".arm-inprogress"):
            raise OSError("locked")
        real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", _bad_unlink)
    deleted = await _disp(FakeSession()).sweep_arm_inprogress(tmp_path)
    assert deleted == 0  # unlink failed, swallowed


@pytest.fixture
def _no_grace(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip cancel_running's 10s grace sleep. Patches the dispatcher's bound
    asyncio.sleep only (not autouse — `asyncio` is a shared module, so a
    global patch would break timing in unrelated tests)."""
    real_sleep = asyncio.sleep

    async def _maybe_instant(secs: float) -> None:
        if secs == tdmod._CANCEL_GRACE_SECONDS:
            return None
        await real_sleep(secs)

    monkeypatch.setattr(tdmod.asyncio, "sleep", _maybe_instant)


async def test_cancel_running_row_gone_after_grace(_no_grace: None) -> None:
    db = FakeSession()
    db.rows["transcode_tasks"] = []  # nothing at task_id → post-grace fetch None
    await _disp(db).cancel_running("txt_gone")  # returns at the 519-520 guard


async def test_cancel_running_docker_stop_error(_no_grace: None) -> None:
    db = FakeSession()
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_1",
            session_application_id="sap_1",
            source_track_id="trk_1",
            status=TranscodeTaskStatus.IN_PROGRESS,
            progress_pct=50,
            attempts=1,
        )
    ]
    d = _disp(db)
    d._docker.containers.list.side_effect = RuntimeError("docker down")
    await d.cancel_running("txt_1")  # docker-stop exception swallowed, row then deleted
    assert db.deleted  # the task row was removed


async def test_run_loop_tick_ok_then_timeout_then_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    """First tick succeeds; the stop-wait times out (112-113 pass) so the
    loop spins again; the second tick stops it."""
    d = _disp(FakeSession())
    d._tick_interval = 0.01
    n = 0

    async def _tick() -> None:
        nonlocal n
        n += 1
        if n >= 2:
            d.stop()

    monkeypatch.setattr(d, "_tick", _tick)
    await asyncio.wait_for(d.run(), timeout=2.0)
    assert n >= 2


async def test_spawn_pending_cpu_path_no_gpu() -> None:
    """A queued task with no GPUs in the inventory → assignment is None →
    the GPU-env block is skipped (384->386)."""
    db = FakeSession()
    db.rows["session_applications"] = [
        SessionApplication(
            id="sap_x",
            session_id="ses_x",
            job_id="job_01JZXR7K3M5Q8N4VWA00000001",
            status=SessionApplicationStatus.RUNNING,
            overwrite=False,
        )
    ]
    db.rows["gpus"] = []
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_cpu",
            session_application_id="sap_x",
            source_track_id="trk_a",
            status=TranscodeTaskStatus.QUEUED,
            attempts=0,
            progress_pct=0,
            output_path="cpu.mkv",
            created_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        )
    ]
    disp = TranscodeDispatcher(_settings(), _db_factory(db), MagicMock(), WSHub())
    spawned = await disp.spawn_pending(db)
    assert spawned == 1
