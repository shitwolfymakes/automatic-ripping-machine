"""GPU inventory router (/api/gpus): list, enable/disable, delete, and the
claimed-row delete guard. The table is DB-authoritative (seed-once is covered
in test_main_unit); this drives the management surface the Settings > GPUs
card calls."""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import secrets  # noqa: E402
from datetime import UTC, datetime  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend.db import get_session  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.routers import gpus as gpus_router  # noqa: E402
from arm_common import Gpu, User  # noqa: E402
from arm_common.enums import GpuStatus, GpuVendor  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


def _app(gpus: list[Gpu]) -> tuple[FastAPI, str, FakeSession]:
    key = secrets.token_bytes(32)
    db = FakeSession()
    db.rows["users"] = [User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)]
    db.rows["gpus"] = gpus

    app = FastAPI()
    app.state.signing_key = key
    app.include_router(gpus_router.router)

    async def _override_session() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _override_session
    token, _ = issue_access_token("usr_admin", "admin", key)
    return app, token, db


def _auth(t: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {t}"}


def _gpu(gpu_id: str = "gpu_1", vendor: GpuVendor = GpuVendor.QSV, **kw: object) -> Gpu:
    defaults: dict = {
        "id": gpu_id,
        "vendor": vendor,
        "device_path": "/dev/dri/renderD128",
        "encoder_kinds": ["h264", "h265"],
        "status": GpuStatus.AVAILABLE,
        "enabled": True,
    }
    defaults.update(kw)
    return Gpu(**defaults)


def test_list_returns_inventory() -> None:
    app, token, _db = _app([_gpu(), _gpu("gpu_2", GpuVendor.VAAPI, device_path="/dev/dri/renderD129")])
    with TestClient(app) as c:
        r = c.get("/api/gpus", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body) == 2
    assert {g["vendor"] for g in body} == {"qsv", "vaapi"}
    assert all(g["enabled"] is True for g in body)


def test_list_surfaces_probe_state() -> None:
    probed = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
    app, token, _db = _app(
        [
            _gpu(probed_at=probed),
            _gpu("gpu_2", GpuVendor.VAAPI, device_path="/dev/dri/renderD129", probe_error="vaapi init failed"),
        ]
    )
    with TestClient(app) as c:
        r = c.get("/api/gpus", headers=_auth(token))
    assert r.status_code == 200, r.text
    by_id = {g["id"]: g for g in r.json()}
    assert by_id["gpu_1"]["probed_at"].startswith("2026-09-26T12:00:00")
    assert by_id["gpu_1"]["probe_error"] is None
    assert by_id["gpu_2"]["probed_at"] is None
    assert by_id["gpu_2"]["probe_error"] == "vaapi init failed"


def test_patch_toggles_enabled() -> None:
    app, token, db = _app([_gpu()])
    with TestClient(app) as c:
        r = c.patch("/api/gpus/gpu_1", json={"enabled": False}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is False
    assert db.rows["gpus"][0].enabled is False


def test_patch_rejects_unknown_fields() -> None:
    # extra="forbid": only the operator switch is editable — hardware facts
    # (vendor, path, encoder kinds) are re-seeded, never patched.
    app, token, _db = _app([_gpu()])
    with TestClient(app) as c:
        r = c.patch("/api/gpus/gpu_1", json={"enabled": False, "vendor": "nvenc"}, headers=_auth(token))
    assert r.status_code == 422


def test_patch_unknown_gpu_404() -> None:
    app, token, _db = _app([])
    with TestClient(app) as c:
        r = c.patch("/api/gpus/gpu_missing", json={"enabled": False}, headers=_auth(token))
    assert r.status_code == 404


def test_delete_removes_row() -> None:
    app, token, db = _app([_gpu()])
    with TestClient(app) as c:
        r = c.delete("/api/gpus/gpu_1", headers=_auth(token))
    assert r.status_code == 204
    assert db.rows["gpus"] == []


def test_delete_claimed_gpu_409() -> None:
    app, token, db = _app([_gpu(status=GpuStatus.BUSY, claimed_by_task_id="tt_running")])
    with TestClient(app) as c:
        r = c.delete("/api/gpus/gpu_1", headers=_auth(token))
    assert r.status_code == 409
    assert len(db.rows["gpus"]) == 1  # row survives


# --- re-probe endpoints ------------------------------------------------------


class _Runner:
    """Stands in for GpuProbeRunner: records what the endpoints schedule."""

    def __init__(self, *, capable: bool = True, probing: set[str] | None = None) -> None:
        self._capable = capable
        self.probing = probing or set()
        self.started: list[str] = []

    def capable(self) -> bool:
        return self._capable

    def gpu_in_use(self, gpu: Gpu) -> bool:
        return gpu.claimed_by_task_id is not None or gpu.status == GpuStatus.BUSY

    def start_probe(self, gpu_id: str) -> bool:
        if gpu_id in self.probing:
            return False
        self.probing.add(gpu_id)
        self.started.append(gpu_id)
        return True


def _real_runner(claimed: set[str]) -> object:
    """A real GpuProbeRunner over a real dispatcher whose in-process claim
    marker holds `claimed` (a claim not yet committed: the row still reads
    AVAILABLE from any other session)."""
    from unittest.mock import MagicMock

    from arm_backend.config import Settings
    from arm_backend.gpu_probe_runner import GpuProbeRunner
    from arm_backend.transcode_dispatcher import TranscodeDispatcher

    settings = Settings.model_construct(
        ARM_TRANSCODE_CAPABLE=True, ARM_TRANSCODE_DOCKER_HOST="", ARM_TRANSCODE_DISPATCH_INTERVAL_SECONDS=5
    )
    dispatcher = TranscodeDispatcher(settings, MagicMock(), MagicMock(), MagicMock())
    dispatcher.claimed_gpu_ids.update(claimed)
    return GpuProbeRunner(settings, MagicMock(), dispatcher, MagicMock())


def test_probe_one_uncommitted_claim_409() -> None:
    app, token, _db = _app([_gpu()])  # AVAILABLE as far as this session can see
    app.state.gpu_probe_runner = _real_runner({"gpu_1"})
    with TestClient(app) as c:
        r = c.post("/api/gpus/gpu_1/probe", headers=_auth(token))
    assert r.status_code == 409
    assert r.json()["detail"] == "gpu is in use by a running transcode"


def test_probe_all_skips_uncommitted_claim() -> None:
    app, token, _db = _app([_gpu()])
    runner = _real_runner({"gpu_1"})
    app.state.gpu_probe_runner = runner
    with TestClient(app) as c:
        r = c.post("/api/gpus/probe", headers=_auth(token))
    assert r.status_code == 202, r.text
    assert r.json() == {"scheduled": []}


def test_probe_one_schedules_202() -> None:
    app, token, _db = _app([_gpu()])
    runner = _Runner()
    app.state.gpu_probe_runner = runner
    with TestClient(app) as c:
        r = c.post("/api/gpus/gpu_1/probe", headers=_auth(token))
    assert r.status_code == 202, r.text
    assert r.json() == {"scheduled": True}
    assert runner.started == ["gpu_1"]


def test_probe_one_unknown_404() -> None:
    app, token, _db = _app([])
    app.state.gpu_probe_runner = _Runner()
    with TestClient(app) as c:
        r = c.post("/api/gpus/gpu_missing/probe", headers=_auth(token))
    assert r.status_code == 404


def test_probe_one_busy_409() -> None:
    app, token, _db = _app([_gpu(status=GpuStatus.BUSY, claimed_by_task_id="tt_running")])
    runner = _Runner()
    app.state.gpu_probe_runner = runner
    with TestClient(app) as c:
        r = c.post("/api/gpus/gpu_1/probe", headers=_auth(token))
    assert r.status_code == 409
    assert r.json()["detail"] == "gpu is in use by a running transcode"
    assert runner.started == []


def test_probe_one_not_capable_409() -> None:
    app, token, _db = _app([_gpu()])
    app.state.gpu_probe_runner = _Runner(capable=False)
    with TestClient(app) as c:
        r = c.post("/api/gpus/gpu_1/probe", headers=_auth(token))
    assert r.status_code == 409
    assert r.json()["detail"] == "no docker client (ripper-only deployment or docker unavailable)"


def test_probe_one_without_a_runner_is_not_capable_409() -> None:
    app, token, _db = _app([_gpu()])
    with TestClient(app) as c:
        r = c.post("/api/gpus/gpu_1/probe", headers=_auth(token))
    assert r.status_code == 409
    assert r.json()["detail"] == "no docker client (ripper-only deployment or docker unavailable)"


def test_probe_one_already_probing_409() -> None:
    app, token, _db = _app([_gpu()])
    app.state.gpu_probe_runner = _Runner(probing={"gpu_1"})
    with TestClient(app) as c:
        r = c.post("/api/gpus/gpu_1/probe", headers=_auth(token))
    assert r.status_code == 409
    assert r.json()["detail"] == "gpu probe already running"


def test_probe_all_skips_busy_disabled_and_already_probing() -> None:
    app, token, _db = _app(
        [
            _gpu("gpu_free"),
            _gpu("gpu_busy", status=GpuStatus.BUSY, claimed_by_task_id="tt_running"),
            _gpu("gpu_off", enabled=False),
            _gpu("gpu_probing"),
            _gpu("gpu_free2", GpuVendor.NVENC, device_path="nvidia://0"),
        ]
    )
    runner = _Runner(probing={"gpu_probing"})
    app.state.gpu_probe_runner = runner
    with TestClient(app) as c:
        r = c.post("/api/gpus/probe", headers=_auth(token))
    assert r.status_code == 202, r.text
    assert r.json() == {"scheduled": ["gpu_free", "gpu_free2"]}
    assert runner.started == ["gpu_free", "gpu_free2"]


def test_probe_all_not_capable_409() -> None:
    app, token, _db = _app([_gpu()])
    app.state.gpu_probe_runner = _Runner(capable=False)
    with TestClient(app) as c:
        r = c.post("/api/gpus/probe", headers=_auth(token))
    assert r.status_code == 409
    assert r.json()["detail"] == "no docker client (ripper-only deployment or docker unavailable)"


# --- probe on enable ------------------------------------------------------------


def test_enabling_a_never_probed_row_schedules_its_probe() -> None:
    app, token, db = _app([_gpu(enabled=False, probed_at=None)])
    runner = _Runner()
    app.state.gpu_probe_runner = runner
    with TestClient(app) as c:
        r = c.patch("/api/gpus/gpu_1", json={"enabled": True}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert db.rows["gpus"][0].enabled is True
    assert runner.started == ["gpu_1"]


def test_enabling_an_already_probed_row_does_not_probe() -> None:
    app, token, _db = _app([_gpu(enabled=False, probed_at=datetime(2026, 9, 26, tzinfo=UTC))])
    runner = _Runner()
    app.state.gpu_probe_runner = runner
    with TestClient(app) as c:
        r = c.patch("/api/gpus/gpu_1", json={"enabled": True}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert runner.started == []


def test_patching_an_enabled_row_enabled_again_does_not_probe() -> None:
    app, token, _db = _app([_gpu(probed_at=None)])
    runner = _Runner()
    app.state.gpu_probe_runner = runner
    with TestClient(app) as c:
        r = c.patch("/api/gpus/gpu_1", json={"enabled": True}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert runner.started == []


def test_disabling_a_never_probed_row_does_not_probe() -> None:
    app, token, _db = _app([_gpu(probed_at=None)])
    runner = _Runner()
    app.state.gpu_probe_runner = runner
    with TestClient(app) as c:
        r = c.patch("/api/gpus/gpu_1", json={"enabled": False}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert runner.started == []


def test_enabling_succeeds_when_the_probe_cannot_start() -> None:
    rows = [
        _gpu("gpu_busy", enabled=False, status=GpuStatus.BUSY, claimed_by_task_id="tt_running"),
        _gpu("gpu_probing", enabled=False),
    ]
    app, token, db = _app(rows)
    runner = _Runner(probing={"gpu_probing"})
    app.state.gpu_probe_runner = runner
    with TestClient(app) as c:
        busy = c.patch("/api/gpus/gpu_busy", json={"enabled": True}, headers=_auth(token))
        probing = c.patch("/api/gpus/gpu_probing", json={"enabled": True}, headers=_auth(token))
    assert (busy.status_code, probing.status_code) == (200, 200)
    assert all(g.enabled for g in db.rows["gpus"])
    assert runner.started == []


def test_enabling_on_a_host_that_cannot_probe_still_succeeds() -> None:
    for runner in (_Runner(capable=False), None):
        app, token, db = _app([_gpu(enabled=False)])
        if runner is not None:
            app.state.gpu_probe_runner = runner
        with TestClient(app) as c:
            r = c.patch("/api/gpus/gpu_1", json={"enabled": True}, headers=_auth(token))
        assert r.status_code == 200, r.text
        assert db.rows["gpus"][0].enabled is True
        assert runner is None or runner.started == []


def test_delete_unknown_gpu_404() -> None:
    app, token, _db = _app([])
    with TestClient(app) as c:
        r = c.delete("/api/gpus/gpu_missing", headers=_auth(token))
    assert r.status_code == 404
    assert r.json()["detail"] == "gpu not found"
