"""`default_roots` names every storage root the backend creates and reports."""

from __future__ import annotations

import pytest

from arm_backend import utils
from arm_backend.config import settings


def test_default_roots_include_the_staging_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "RAW_ROOT", "/raw")
    monkeypatch.setattr(settings, "ARM_HOST_STAGING_PATH", "")
    roots = utils.default_roots()
    assert roots["STAGING_ROOT"] == "/raw/.staging"
    assert {"MEDIA_ROOT", "RAW_ROOT", "LOG_DIR"} <= set(roots)


def test_default_roots_use_staging_root_setting_outside_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ARM_HOST_RAW_PATH", "/h/raw")
    monkeypatch.setattr(settings, "ARM_HOST_STAGING_PATH", "/h/stage")
    monkeypatch.setattr(settings, "STAGING_ROOT", "/staging")
    assert utils.default_roots()["STAGING_ROOT"] == "/staging"


def test_disk_refresh_roots_prefers_the_injected_roots() -> None:
    assert utils.disk_refresh_roots({"RAW_ROOT": "/r", "STAGING_ROOT": "/s"}) == ["/r", "/s"]


def test_disk_refresh_roots_default_to_every_root_and_the_iso_ingress(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "RAW_ROOT", "/raw")
    monkeypatch.setattr(settings, "ARM_HOST_STAGING_PATH", "")
    monkeypatch.setattr(settings, "ISO_INGRESS_ROOT", "/iso")
    roots = utils.disk_refresh_roots(None)
    assert "/raw/.staging" in roots and roots[-1] == "/iso"
    assert utils.disk_refresh_roots({}) == roots


async def test_start_disk_refresher_caches_the_resolved_roots(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    from arm_backend import main

    created: list[list[str]] = []

    class _Refresher:
        def __init__(self, roots: list[str]) -> None:
            created.append(roots)

        async def run(self) -> None:
            return None

    monkeypatch.setattr(main, "DiskRefresher", _Refresher)
    services = SimpleNamespace(_app=SimpleNamespace(state=SimpleNamespace(system_paths={"STAGING_ROOT": "/s"})))
    main._BackendServices._start_disk_refresher(services)  # type: ignore[arg-type]
    await services._disk_refresher_task
    assert created == [["/s"]]
    assert services._app.state.disk_refresher is services._disk_refresher
