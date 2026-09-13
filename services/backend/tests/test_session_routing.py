"""G-01 (gap analysis §5.1): session ROUTING is separate from auto-apply
PERMISSION.

`resolve_routed_session_id` answers "which session is routed to this job"
(explicit per-rip choice, else the drive default) with NO
auto_transcode_on_idle gating — it shapes the rip and the naming preview.
`auto_apply_allowed` answers "may rip-complete queue it unattended" — the
flag, bypassed by an explicit per-rip choice.
"""

from __future__ import annotations

import os

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

from arm_backend.auto_session import auto_apply_allowed, resolve_routed_session_id  # noqa: E402
from arm_common import (  # noqa: E402
    Config,
    DiscType,
    Drive,
    DriveStatus,
    Job,
    JobStatus,
)

from tests._fakes import FakeSession  # noqa: E402


def _job(meta: dict | None = None) -> Job:
    return Job(
        id="job_01JZXR7K3M5Q8N4VWA00000001",
        drive_id="drv_x",
        disc_type=DiscType.DVD,
        status=JobStatus.RIPPED,
        metadata_json=meta or {},
    )


def _seed(db: FakeSession, *, default_session_id: str | None, flag: bool) -> None:
    db.rows["drives"] = [
        Drive(
            id="drv_x",
            hostname="h",
            device_path="/dev/sr0",
            status=DriveStatus.ONLINE,
            default_session_id=default_session_id,
        )
    ]
    db.rows["config"] = [Config(id=1, auto_transcode_on_idle=flag, auto_rip_on_insert=True, block_on_miss=True)]


@pytest.mark.asyncio
async def test_pending_choice_wins_over_drive_default() -> None:
    db = FakeSession()
    _seed(db, default_session_id="ses_default", flag=True)
    got = await resolve_routed_session_id(db, _job({"pending_session_id": "ses_chosen"}))  # type: ignore[arg-type]
    assert got == "ses_chosen"


@pytest.mark.asyncio
async def test_drive_default_routes_without_auto_flag() -> None:
    """The flag gates unattended QUEUEING, not routing: the drive default
    still shapes the rip and the preview when auto-transcode is off."""
    db = FakeSession()
    _seed(db, default_session_id="ses_default", flag=False)
    got = await resolve_routed_session_id(db, _job())  # type: ignore[arg-type]
    assert got == "ses_default"


@pytest.mark.asyncio
async def test_no_default_no_pending_routes_none() -> None:
    db = FakeSession()
    _seed(db, default_session_id=None, flag=True)
    assert await resolve_routed_session_id(db, _job()) is None  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_unknown_drive_routes_none() -> None:
    db = FakeSession()
    db.rows["drives"] = []
    db.rows["config"] = []
    assert await resolve_routed_session_id(db, _job()) is None  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_auto_apply_needs_flag_for_drive_default() -> None:
    db = FakeSession()
    _seed(db, default_session_id="ses_default", flag=False)
    assert await auto_apply_allowed(db, _job()) is False  # type: ignore[arg-type]
    _seed(db, default_session_id="ses_default", flag=True)
    assert await auto_apply_allowed(db, _job()) is True  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_auto_apply_pending_choice_bypasses_flag() -> None:
    """An explicit per-rip session choice is the user opting in for this one
    rip; the global flag must not veto it."""
    db = FakeSession()
    _seed(db, default_session_id=None, flag=False)
    assert await auto_apply_allowed(db, _job({"pending_session_id": "ses_chosen"})) is True  # type: ignore[arg-type]
