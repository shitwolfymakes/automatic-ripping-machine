"""Unit coverage for the backend entrypoint's helpers — _run_migrations,
docker_factory.build_docker_client (both branches), and main() — without
booting the app (the lifespan itself is exercised by the e2e harness).
"""

from __future__ import annotations

import subprocess


import pytest

from arm_backend import docker_factory, gpu_inventory
from arm_backend import main as main_mod
from arm_backend import thediscdb_schedule


def test_run_migrations_invokes_alembic(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []

    def _fake_run(cmd: list[str], **kw: object) -> None:
        calls.append({"cmd": cmd, "kw": kw})

    monkeypatch.setattr(main_mod.subprocess, "run", _fake_run)
    main_mod._run_migrations()
    assert calls[0]["cmd"] == ["alembic", "upgrade", "head"]
    assert calls[0]["kw"]["check"] is True


def test_run_migrations_propagates_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_a: object, **_k: object) -> None:
        raise subprocess.CalledProcessError(1, "alembic")

    monkeypatch.setattr(main_mod.subprocess, "run", _boom)
    with pytest.raises(subprocess.CalledProcessError):
        main_mod._run_migrations()


def test_build_docker_client_returns_client(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    fake_docker = type("D", (), {"from_env": staticmethod(lambda: sentinel)})
    monkeypatch.setitem(__import__("sys").modules, "docker", fake_docker)
    assert docker_factory.build_docker_client() is sentinel


def test_build_docker_client_returns_none_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise() -> object:
        raise RuntimeError("no socket")

    fake_docker = type("D", (), {"from_env": staticmethod(_raise)})
    monkeypatch.setitem(__import__("sys").modules, "docker", fake_docker)
    assert docker_factory.build_docker_client() is None


def test_build_docker_client_remote_uses_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = object()
    captured: dict[str, str] = {}

    def _docker_client(*, base_url: str) -> object:
        captured["base_url"] = base_url
        return sentinel

    fake_docker = type("D", (), {"DockerClient": staticmethod(_docker_client)})
    monkeypatch.setitem(__import__("sys").modules, "docker", fake_docker)
    assert docker_factory.build_docker_client("ssh://sam@transcoder-server") is sentinel
    assert captured["base_url"] == "ssh://sam@transcoder-server"


def test_build_docker_client_default_purpose_is_transcode_dispatcher(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def _raise() -> object:
        raise RuntimeError("no socket")

    fake_docker = type("D", (), {"from_env": staticmethod(_raise)})
    monkeypatch.setitem(__import__("sys").modules, "docker", fake_docker)
    with caplog.at_level("WARNING", logger="arm_backend"):
        assert docker_factory.build_docker_client() is None
    assert "transcode dispatcher disabled" in caplog.text


def test_build_docker_client_purpose_is_used_in_the_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The warning names whichever docker-backed feature failed to
    build a client, not always "transcode dispatcher"."""

    def _raise() -> object:
        raise RuntimeError("no socket")

    fake_docker = type("D", (), {"from_env": staticmethod(_raise)})
    monkeypatch.setitem(__import__("sys").modules, "docker", fake_docker)
    with caplog.at_level("WARNING", logger="arm_backend"):
        assert docker_factory.build_docker_client(purpose="ripper manager") is None
    assert "ripper manager disabled" in caplog.text
    assert "transcode dispatcher" not in caplog.text


def test_main_invokes_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_uvicorn_run(app: str, **kw: object) -> None:
        captured["app"] = app
        captured.update(kw)

    monkeypatch.setattr(main_mod.uvicorn, "run", _fake_uvicorn_run)
    main_mod.main()
    assert captured["app"] == "arm_backend.main:app"
    assert "host" in captured and "port" in captured


# --- refresh_gpu_inventory (both populated + empty branches) ----------------


class _SessionCtx:
    def __init__(self, db: object) -> None:
        self._db = db

    async def __aenter__(self) -> object:
        return self._db

    async def __aexit__(self, *_exc: object) -> bool:
        return False


class _Hub:
    def __init__(self) -> None:
        self.events: list[str] = []

    async def emit(self, *, topic: str, event_type: str, payload: object, session: object) -> None:
        self.events.append(event_type)


async def test_refresh_gpu_inventory_populates(monkeypatch: pytest.MonkeyPatch) -> None:
    from arm_backend.gpu_probe import ProbedGpu
    from arm_common.enums import GpuVendor

    from tests._fakes import FakeSession

    db = FakeSession()
    monkeypatch.setattr(gpu_inventory, "SessionLocal", lambda: _SessionCtx(db))
    monkeypatch.setattr(
        gpu_inventory,
        "load_configured_gpus",
        lambda _raw: [ProbedGpu(vendor=GpuVendor.QSV, device_path="/dev/dri/renderD128", encoder_kinds=["h264"])],
    )
    hub = _Hub()
    await gpu_inventory.refresh_gpu_inventory(hub)
    added = [r for r in db.added if type(r).__name__ == "Gpu"]
    assert len(added) == 1
    # The descriptor's encoder_kinds are hints only: a seeded row is unprobed
    # and claims nothing until the backend's own device probe verifies it.
    assert added[0].encoder_kinds == []
    assert added[0].probed_at is None
    assert hub.events == []  # GPU present → no hw_unavailable


async def test_refresh_gpu_inventory_empty_emits_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests._fakes import FakeSession

    db = FakeSession()
    monkeypatch.setattr(gpu_inventory, "SessionLocal", lambda: _SessionCtx(db))
    monkeypatch.setattr(gpu_inventory, "load_configured_gpus", lambda _raw: [])
    hub = _Hub()
    await gpu_inventory.refresh_gpu_inventory(hub)
    assert hub.events == ["transcode.hw_unavailable"]


async def test_refresh_gpu_inventory_respects_existing_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    """DB-authoritative: an already-populated gpus table is left untouched
    and ARM_GPUS is not even parsed (operator edits must survive restarts)."""
    from arm_common import Gpu
    from arm_common.enums import GpuVendor

    from tests._fakes import FakeSession

    db = FakeSession()
    db.rows["gpus"] = [Gpu(vendor=GpuVendor.NVENC, device_path="nvidia://0", encoder_kinds=["h265"], enabled=False)]
    monkeypatch.setattr(gpu_inventory, "SessionLocal", lambda: _SessionCtx(db))

    def _boom(_raw: object) -> list:
        raise AssertionError("ARM_GPUS must not be consulted when rows exist")

    monkeypatch.setattr(gpu_inventory, "load_configured_gpus", _boom)
    hub = _Hub()
    await gpu_inventory.refresh_gpu_inventory(hub)
    assert [r for r in db.added if type(r).__name__ == "Gpu"] == []
    assert db.rows["gpus"][0].enabled is False  # operator switch untouched
    assert hub.events == []


async def test_refresh_gpu_inventory_releases_orphaned_claims(monkeypatch: pytest.MonkeyPatch) -> None:
    """With seed-once inventory a BUSY row whose claim was nulled by a
    task delete, or whose task finished, is freed at boot. A QUEUED or
    IN_PROGRESS claimant may still be running and keeps its GPU."""
    from arm_common import Gpu, GpuStatus, TranscodeTask, TranscodeTaskStatus
    from arm_common.enums import GpuVendor

    from tests._fakes import FakeSession

    def gpu(gid: str, claim: str | None, status: GpuStatus = GpuStatus.BUSY) -> Gpu:
        return Gpu(
            id=gid, vendor=GpuVendor.VAAPI, device_path=f"/dev/dri/{gid}", status=status, claimed_by_task_id=claim
        )

    def task(tid: str, status: TranscodeTaskStatus) -> TranscodeTask:
        return TranscodeTask(id=tid, session_application_id="sap_1", source_track_id="trk_1", status=status)

    db = FakeSession()
    db.rows["gpus"] = [
        gpu("nulled", None),
        gpu("done", "txt_done"),
        gpu("gone", "txt_gone"),
        gpu("queued", "txt_q"),
        gpu("running", "txt_r"),
        gpu("free", None, GpuStatus.AVAILABLE),
    ]
    db.rows["transcode_tasks"] = [
        task("txt_done", TranscodeTaskStatus.DONE),
        task("txt_q", TranscodeTaskStatus.QUEUED),
        task("txt_r", TranscodeTaskStatus.IN_PROGRESS),
    ]
    monkeypatch.setattr(gpu_inventory, "SessionLocal", lambda: _SessionCtx(db))
    await gpu_inventory.refresh_gpu_inventory(_Hub())
    state = {g.id: (g.status, g.claimed_by_task_id) for g in db.rows["gpus"]}
    assert state == {
        "nulled": (GpuStatus.AVAILABLE, None),
        "done": (GpuStatus.AVAILABLE, None),
        "gone": (GpuStatus.AVAILABLE, None),
        "queued": (GpuStatus.BUSY, "txt_q"),
        "running": (GpuStatus.BUSY, "txt_r"),
        "free": (GpuStatus.AVAILABLE, None),
    }
    assert db.committed


async def test_thediscdb_refresh_loop_persists_refreshed_at(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    """With the feature enabled and no local index, the loop refreshes once,
    stamps thediscdb_refreshed_at on the singleton Config, commits, then
    parks on its daily sleep."""
    import asyncio
    from pathlib import Path

    from fastapi import FastAPI

    from arm_backend.identity.sources import thediscdb_refresh, thediscdb_snapshot as snap
    from arm_backend.constants import CONFIG_SINGLETON_ID
    from arm_common import Config, RetentionPolicy

    from tests._fakes import FakeSession

    cfg = Config(
        id=CONFIG_SINGLETON_ID,
        auto_transcode_on_idle=False,
        auto_rip_on_insert=True,
        block_on_miss=True,
        community_keydb_enabled=True,
        makemkv_sdf_enabled=True,
        hold_for_review=False,
        ripping_paused=False,
        thediscdb_enabled=True,
        thediscdb_refresh_days=7,
        thediscdb_refreshed_at=None,
        manual_wait_seconds=60,
        default_retention_policy=RetentionPolicy.PRUNE_AFTER_SESSION,
    )
    db = FakeSession()
    db.rows["config"] = [cfg]
    monkeypatch.setattr(thediscdb_schedule, "SessionLocal", lambda: _SessionCtx(db))
    monkeypatch.setattr(thediscdb_schedule.settings, "ARM_THEDISCDB_PATH", str(tmp_path))

    calls: list[tuple[object, Path]] = []

    async def _fake_refresh(http: object, path: Path) -> int:
        calls.append((http, path))
        return 3

    monkeypatch.setattr(thediscdb_refresh, "refresh", _fake_refresh)

    real_sleep = asyncio.sleep

    async def _sleep(delay: float, *a: object, **k: object) -> None:
        if delay >= 24 * 3600:  # the loop's daily park: end the test here
            raise asyncio.CancelledError
        await real_sleep(delay, *a, **k)

    monkeypatch.setattr(asyncio, "sleep", _sleep)

    app = FastAPI()
    app.state.http = object()
    app.state.thediscdb = snap.SnapshotStore(Path(str(tmp_path)))  # no index on disk → stale

    with pytest.raises(asyncio.CancelledError):
        await thediscdb_schedule.thediscdb_refresh_loop(app)

    assert calls == [(app.state.http, Path(str(tmp_path)))]
    assert cfg.thediscdb_refreshed_at is not None
    assert cfg in db.added


async def test_thediscdb_refresh_loop_skips_when_disabled(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    """With the feature disabled the loop skips the refresh and parks on its
    daily sleep."""
    import asyncio
    from pathlib import Path

    from fastapi import FastAPI

    from arm_backend.identity.sources import thediscdb_refresh, thediscdb_snapshot as snap
    from arm_backend.constants import CONFIG_SINGLETON_ID
    from arm_common import Config, RetentionPolicy

    from tests._fakes import FakeSession

    cfg = Config(
        id=CONFIG_SINGLETON_ID,
        auto_transcode_on_idle=False,
        auto_rip_on_insert=True,
        block_on_miss=True,
        community_keydb_enabled=True,
        makemkv_sdf_enabled=True,
        hold_for_review=False,
        ripping_paused=False,
        thediscdb_enabled=False,
        thediscdb_refresh_days=7,
        thediscdb_refreshed_at=None,
        manual_wait_seconds=60,
        default_retention_policy=RetentionPolicy.PRUNE_AFTER_SESSION,
    )
    db = FakeSession()
    db.rows["config"] = [cfg]
    monkeypatch.setattr(thediscdb_schedule, "SessionLocal", lambda: _SessionCtx(db))
    monkeypatch.setattr(thediscdb_schedule.settings, "ARM_THEDISCDB_PATH", str(tmp_path))

    calls: list[tuple[object, Path]] = []

    async def _fake_refresh(http: object, path: Path) -> int:
        calls.append((http, path))
        return 3

    monkeypatch.setattr(thediscdb_refresh, "refresh", _fake_refresh)

    real_sleep = asyncio.sleep

    async def _sleep(delay: float, *a: object, **k: object) -> None:
        if delay >= 24 * 3600:  # the loop's daily park: end the test here
            raise asyncio.CancelledError
        await real_sleep(delay, *a, **k)

    monkeypatch.setattr(asyncio, "sleep", _sleep)

    app = FastAPI()
    app.state.http = object()
    app.state.thediscdb = snap.SnapshotStore(Path(str(tmp_path)))

    with pytest.raises(asyncio.CancelledError):
        await thediscdb_schedule.thediscdb_refresh_loop(app)

    assert calls == []
    assert cfg.thediscdb_refreshed_at is None
    assert cfg not in db.added


async def test_thediscdb_refresh_loop_skips_a_fresh_index(monkeypatch: pytest.MonkeyPatch, tmp_path: object) -> None:
    """An enabled feature with an index on disk refreshed an hour ago is not
    stale, so the loop just sleeps."""
    import asyncio
    import types
    from datetime import UTC, datetime, timedelta
    from pathlib import Path

    from fastapi import FastAPI

    from arm_backend.identity.sources import thediscdb_refresh
    from arm_backend.constants import CONFIG_SINGLETON_ID
    from arm_common import Config, RetentionPolicy

    from tests._fakes import FakeSession

    refreshed_at = datetime.now(UTC) - timedelta(hours=1)
    cfg = Config(
        id=CONFIG_SINGLETON_ID,
        auto_transcode_on_idle=False,
        auto_rip_on_insert=True,
        block_on_miss=True,
        community_keydb_enabled=True,
        makemkv_sdf_enabled=True,
        hold_for_review=False,
        ripping_paused=False,
        thediscdb_enabled=True,
        thediscdb_refresh_days=7,
        thediscdb_refreshed_at=refreshed_at,
        manual_wait_seconds=60,
        default_retention_policy=RetentionPolicy.PRUNE_AFTER_SESSION,
    )
    db = FakeSession()
    db.rows["config"] = [cfg]
    monkeypatch.setattr(thediscdb_schedule, "SessionLocal", lambda: _SessionCtx(db))
    monkeypatch.setattr(thediscdb_schedule.settings, "ARM_THEDISCDB_PATH", str(tmp_path))

    calls: list[tuple[object, Path]] = []

    async def _fake_refresh(http: object, path: Path) -> int:
        calls.append((http, path))
        return 3

    monkeypatch.setattr(thediscdb_refresh, "refresh", _fake_refresh)

    real_sleep = asyncio.sleep

    async def _sleep(delay: float, *a: object, **k: object) -> None:
        if delay >= 24 * 3600:  # the loop's daily park: end the test here
            raise asyncio.CancelledError
        await real_sleep(delay, *a, **k)

    monkeypatch.setattr(asyncio, "sleep", _sleep)

    app = FastAPI()
    app.state.http = object()
    app.state.thediscdb = types.SimpleNamespace(exists=lambda: True)

    with pytest.raises(asyncio.CancelledError):
        await thediscdb_schedule.thediscdb_refresh_loop(app)

    assert calls == []
    assert cfg.thediscdb_refreshed_at == refreshed_at
    assert cfg not in db.added


async def test_thediscdb_refresh_loop_survives_an_error(monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    """A failing pass is logged and the loop sleeps until the next one. Pinned
    here because the e2e boot only reaches this line when its refresh happens
    to fail (no network), which made coverage environment-dependent."""
    import asyncio

    def _broken_session() -> object:
        raise RuntimeError("db down")

    async def _stop(_seconds: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(thediscdb_schedule, "SessionLocal", _broken_session)
    monkeypatch.setattr(thediscdb_schedule.asyncio, "sleep", _stop)
    with pytest.raises(asyncio.CancelledError):
        await thediscdb_schedule.thediscdb_refresh_loop(object())  # type: ignore[arg-type]
    assert "thediscdb: refresh loop error: db down" in caplog.text


def test_ensure_roots_never_raises(tmp_path, caplog) -> None:
    """A root that cannot be created (here: under a regular file) is logged,
    not raised, so a broken mount never crash-loops the API."""
    from arm_backend.utils import ensure_roots

    blocker = tmp_path / "file"
    blocker.write_text("")
    ensure_roots({"media": str(blocker / "media"), "raw": str(tmp_path / "raw")})
    assert (tmp_path / "raw").is_dir()
    assert "cannot create media" in caplog.text


# --- _startup_sweep ---------------------------------------------------------


async def test_startup_sweep_logs_the_count_when_rows_were_touched(caplog) -> None:
    async def _sweep() -> int:
        return 3

    with caplog.at_level("INFO", logger="arm_backend"):
        await main_mod._startup_sweep(_sweep, "swept %d rows", "sweep failed: %s")
    assert [(r.levelname, r.getMessage()) for r in caplog.records if r.name == "arm_backend"] == [
        ("INFO", "swept 3 rows")
    ]


async def test_startup_sweep_logs_nothing_when_no_rows_were_touched(caplog) -> None:
    async def _sweep() -> int:
        return 0

    with caplog.at_level("INFO", logger="arm_backend"):
        await main_mod._startup_sweep(_sweep, "swept %d rows", "sweep failed: %s")
    assert [r for r in caplog.records if r.name == "arm_backend"] == []


async def test_startup_sweep_swallows_a_failure_and_logs_it(caplog) -> None:
    async def _sweep() -> int:
        raise RuntimeError("boom")

    with caplog.at_level("INFO", logger="arm_backend"):
        await main_mod._startup_sweep(_sweep, "swept %d rows", "sweep failed: %s")
    records = [r for r in caplog.records if r.name == "arm_backend"]
    assert [(r.levelname, r.getMessage()) for r in records] == [("ERROR", "sweep failed: boom")]
