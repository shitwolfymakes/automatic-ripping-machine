"""ISO "preparing" status: what an ISO ripper reports before identify creates
its job (scanning the image, unpacking it for MakeMKV), so the dashboard can
show the rip instead of nothing. Held in memory; the ripper re-sends it as a
keepalive, and identify / retire clear it."""

from __future__ import annotations

import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from arm_backend import iso_prepare, iso_rips  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.db import get_session  # noqa: E402
from arm_backend.routers import iso as iso_router  # noqa: E402
from arm_backend.routers import ripper as ripper_router  # noqa: E402
from arm_common import (  # noqa: E402
    Drive,
    DriveKind,
    DriveLifecycle,
    DriveSourceKind,
    DriveStatus,
    IsoPreparePhase,
    User,
)
from arm_common.schemas import IsoPrepareReport  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402

_SERVICE = {"Authorization": "Bearer tok-service"}


class _Hub:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def emit(self, topic, event_type, payload, *, persist=True, job_id=None, track_id=None, session=None):
        self.events.append({"topic": topic, "event_type": event_type, "payload": payload, "persist": persist})


@pytest.fixture(autouse=True)
def _empty_registry() -> None:
    iso_prepare.clear_all()
    yield
    iso_prepare.clear_all()


def _virtual(drive_id: str = "drv_iso1") -> Drive:
    return Drive(
        id=drive_id,
        hostname=f"iso-{drive_id}",
        device_path="/source/x.iso",
        status=DriveStatus.ONLINE,
        lifecycle=DriveLifecycle.ENROLLED,
        kind=DriveKind.VIRTUAL,
        source_kind=DriveSourceKind.ISO,
        source_path="x.iso",
    )


def _app(db: FakeSession, hub: _Hub, signing_key: bytes) -> FastAPI:
    app = FastAPI()
    app.state.signing_key = signing_key
    app.state.ws_hub = hub
    app.state.ripper_manager = None
    app.include_router(ripper_router.router)
    app.include_router(iso_router.router)

    async def _s() -> FakeSession:
        return db

    app.dependency_overrides[get_session] = _s
    return app


def _jwt(db: FakeSession, signing_key: bytes) -> dict[str, str]:
    db.rows.setdefault("users", []).append(
        User(id="usr_admin", username="admin", password_hash="x", password_must_change=False)
    )
    token, _ = issue_access_token("usr_admin", "admin", signing_key)
    return {"Authorization": f"Bearer {token}"}


def test_a_report_is_listed_as_preparing_and_pushed_to_the_dashboard() -> None:
    key = secrets.token_bytes(32)
    db = FakeSession()
    db.rows["drives"] = [_virtual()]
    hub = _Hub()
    report = {"drive_id": "drv_iso1", "phase": "extracting", "progress_pct": 42, "current_file": "BDMV/STREAM/1.m2ts"}
    with TestClient(_app(db, hub, key)) as client:
        r = client.post("/api/ripper/iso-prepare", json=report, headers=_SERVICE)
        listed = client.get("/api/iso/rips/preparing", headers=_jwt(db, key)).json()

    assert r.status_code == 204, r.text
    assert len(listed) == 1
    assert {k: listed[0][k] for k in report} == report
    assert listed[0]["updated_at"]
    # Not persisted: a progress tick is not an event-log entry; it only wakes
    # the dashboard's ripper.events refresh.
    assert [(e["topic"], e["event_type"], e["persist"]) for e in hub.events] == [
        ("ripper.events", "iso.preparing", False)
    ]


def test_report_for_an_unknown_drive_is_404() -> None:
    db = FakeSession()
    db.rows["drives"] = []
    with TestClient(_app(db, _Hub(), secrets.token_bytes(32))) as client:
        r = client.post("/api/ripper/iso-prepare", json={"drive_id": "drv_x", "phase": "scanning"}, headers=_SERVICE)
    assert r.status_code == 404
    assert iso_prepare.views() == []


def test_report_requires_the_service_token() -> None:
    db = FakeSession()
    db.rows["drives"] = [_virtual()]
    with TestClient(_app(db, _Hub(), secrets.token_bytes(32))) as client:
        r = client.post("/api/ripper/iso-prepare", json={"drive_id": "drv_iso1", "phase": "scanning"})
    assert r.status_code in (401, 403)


def test_a_report_the_ripper_stopped_refreshing_is_dropped() -> None:
    """A ripper that died without its drive being retired yet must not leave
    a frozen "preparing" row behind."""
    iso_prepare.record(IsoPrepareReport(drive_id="drv_old", phase=IsoPreparePhase.SCANNING))
    iso_prepare.record(IsoPrepareReport(drive_id="drv_new", phase=IsoPreparePhase.SCANNING))
    iso_prepare._views["drv_old"] = iso_prepare._views["drv_old"].model_copy(
        update={"updated_at": datetime.now(UTC) - timedelta(seconds=iso_prepare.STALE_SECONDS + 1)}
    )

    assert [v.drive_id for v in iso_prepare.views()] == ["drv_new"]


def test_identify_clears_the_drives_preparing_status() -> None:
    from tests.test_ripper_router import _config, _drive, _make_app, _scan_dict

    iso_prepare.record(IsoPrepareReport(drive_id="drv_x", phase=IsoPreparePhase.SCANNING))
    iso_prepare.record(IsoPrepareReport(drive_id="drv_other", phase=IsoPreparePhase.SCANNING))
    db = FakeSession()
    db.rows["drives"] = [_drive()]
    db.rows["config"] = [_config()]
    with TestClient(_make_app(db)) as client:
        r = client.post(
            "/api/ripper/identify", json={"drive_id": "drv_x", "scan_result": _scan_dict()}, headers=_SERVICE
        )
    assert r.status_code == 200, r.text
    assert [v.drive_id for v in iso_prepare.views()] == ["drv_other"]


@pytest.mark.asyncio
async def test_retire_clears_the_drives_preparing_status() -> None:
    from tests.test_iso_rips import _Manager

    iso_prepare.record(IsoPrepareReport(drive_id="drv_iso1", phase=IsoPreparePhase.EXTRACTING, progress_pct=10))
    await iso_rips.retire_virtual_drive(FakeSession(), _Manager(), _virtual())  # type: ignore[arg-type]
    assert iso_prepare.views() == []
