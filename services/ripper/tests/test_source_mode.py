"""Ripper source mode: ARM_SOURCE_PATH replaces the old manual-trigger hook.

`run_source_mode` is the one-shot entry point `amain` calls when the backend
spawned this container for an ISO rip (no ARM_DRIVE_DEV, no optical poll loop):
run the pipeline exactly once through `handle_manual_trigger`, then return so
the container exits 0 — the backend's virtual-drive watchdog does the rest.
"""

from __future__ import annotations

import asyncio
import os

# arm_ripper.config builds a pydantic Settings at import time and refuses to
# load without these vars. ARM_DRIVE_DEV is deliberately NOT set here: it is
# now optional (source mode has no device node), and other test modules'
# collection-time `os.environ.setdefault("ARM_DRIVE_DEV", ...)` calls would
# otherwise mask a regression in that optionality.
os.environ.setdefault("ARM_DRIVE_ID", "drv_test")
os.environ.setdefault("ARM_BACKEND_URL", "https://backend.invalid")
os.environ.setdefault("ARM_SERVICE_TOKEN", "test-token")

from arm_ripper.config import Settings  # noqa: E402
from arm_ripper.main import run_source_mode  # noqa: E402


class FakeController:
    """Records which JobController entry point source mode used."""

    def __init__(self, *, raise_cancelled: bool = False) -> None:
        self.calls: list[str | None] = []
        self.disc_inserted_calls: list[str] = []
        self._raise_cancelled = raise_cancelled

    async def handle_manual_trigger(self, session_id: str | None) -> None:
        self.calls.append(session_id)
        if self._raise_cancelled:
            raise asyncio.CancelledError()

    async def handle_disc_inserted(self, device_path: str) -> None:  # pragma: no cover - must not be called
        self.disc_inserted_calls.append(device_path)


async def test_source_mode_runs_pipeline_once_with_session():
    controller = FakeController()

    await run_source_mode(controller, "sess_1")  # type: ignore[arg-type]

    assert controller.calls == ["sess_1"]


async def test_source_mode_ignores_auto_rip_flag():
    """Source mode goes through handle_manual_trigger — which bypasses the
    auto_rip_on_insert check — never handle_disc_inserted (which honours it)."""
    controller = FakeController()

    await run_source_mode(controller, None)  # type: ignore[arg-type]

    assert controller.calls == [None]
    assert controller.disc_inserted_calls == []


async def test_source_mode_returns_when_pipeline_cancelled():
    """Cancellation (the operator abandoned the ISO rip) stays inside the
    pipeline task — run_source_mode returns normally so the container exits 0;
    the backend watchdog retires the virtual drive and removes the container."""
    controller = FakeController(raise_cancelled=True)

    await run_source_mode(controller, None)  # type: ignore[arg-type]  # must not raise

    assert controller.calls == [None]


def test_settings_allow_missing_drive_dev_with_source(monkeypatch):
    """ARM_DRIVE_DEV is optional once ARM_SOURCE_PATH is set — the backend
    spawns an ISO-rip container with no device node at all."""
    monkeypatch.delenv("ARM_DRIVE_DEV", raising=False)

    s = Settings(
        ARM_SOURCE_PATH="/source/sintel.iso",
        ARM_DRIVE_ID="drv_test",
        ARM_BACKEND_URL="https://backend.invalid",
        ARM_SERVICE_TOKEN="test-token",
    )  # type: ignore[call-arg]

    assert s.ARM_DRIVE_DEV is None
    assert s.ARM_SOURCE_PATH == "/source/sintel.iso"
    assert s.ARM_SOURCE_KIND == "iso"
    assert s.ARM_SOURCE_SESSION_ID is None
