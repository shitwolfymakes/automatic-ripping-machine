"""Unit coverage for main.py's pure entrypoint helpers — _run_migrations,
_build_docker_client (both branches), and main() — without booting the app
(the lifespan itself is exercised by the e2e harness).
"""

from __future__ import annotations

import os
import subprocess

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

from arm_backend import main as main_mod  # noqa: E402


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
    assert main_mod._build_docker_client() is sentinel


def test_build_docker_client_returns_none_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise() -> object:
        raise RuntimeError("no socket")

    fake_docker = type("D", (), {"from_env": staticmethod(_raise)})
    monkeypatch.setitem(__import__("sys").modules, "docker", fake_docker)
    assert main_mod._build_docker_client() is None


def test_main_invokes_uvicorn(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_uvicorn_run(app: str, **kw: object) -> None:
        captured["app"] = app
        captured.update(kw)

    monkeypatch.setattr(main_mod.uvicorn, "run", _fake_uvicorn_run)
    main_mod.main()
    assert captured["app"] == "arm_backend.main:app"
    assert "host" in captured and "port" in captured


# --- _refresh_gpu_inventory (both populated + empty branches) ----------------


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
    monkeypatch.setattr(main_mod, "SessionLocal", lambda: _SessionCtx(db))
    monkeypatch.setattr(
        main_mod,
        "load_configured_gpus",
        lambda _raw: [ProbedGpu(vendor=GpuVendor.QSV, device_path="/dev/dri/renderD128", encoder_kinds=["h264"])],
    )
    hub = _Hub()
    await main_mod._refresh_gpu_inventory(hub)
    added = [r for r in db.added if type(r).__name__ == "Gpu"]
    assert len(added) == 1
    assert hub.events == []  # GPU present → no hw_unavailable


async def test_refresh_gpu_inventory_empty_emits_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests._fakes import FakeSession

    db = FakeSession()
    monkeypatch.setattr(main_mod, "SessionLocal", lambda: _SessionCtx(db))
    monkeypatch.setattr(main_mod, "load_configured_gpus", lambda _raw: [])
    hub = _Hub()
    await main_mod._refresh_gpu_inventory(hub)
    assert hub.events == ["transcode.hw_unavailable"]
