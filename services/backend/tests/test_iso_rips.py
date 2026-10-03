from __future__ import annotations

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

from arm_backend import iso_library, iso_rips  # noqa: E402
from arm_backend.config import settings  # noqa: E402
from arm_backend.ripper_manager import RipperManagerError  # noqa: E402
from arm_common import (  # noqa: E402
    DiscType,
    Drive,
    DriveKind,
    DriveLifecycle,
    DriveSourceKind,
    DriveStatus,
    Job,
    JobStatus,
    Track,
    TrackKind,
    TrackStatus,
)

from tests._fakes import FakeSession  # noqa: E402


class _Manager:
    """Stands in for RipperManager: `container_statuses` answers from a dict,
    `remove` records the drive ids (or raises)."""

    def __init__(self, states: dict[str, str] | None = None, remove_raises: Exception | None = None) -> None:
        self._states = states or {}
        self._remove_raises = remove_raises
        self.removed: list[str] = []
        self.status_calls: list[list[str]] = []

    def container_statuses(self, drive_ids):
        ids = list(drive_ids)
        self.status_calls.append(ids)
        return {i: (self._states.get(i, "missing"), None) for i in ids}

    def remove(self, drive_id: str) -> int:
        if self._remove_raises is not None:
            raise self._remove_raises
        self.removed.append(drive_id)
        return 1


class _OrderingManager(_Manager):
    """A `_Manager` that logs `remove` into the session's `call_log`, so a
    test can assert removal came after the commit."""

    def __init__(self, db: FakeSession, states: dict[str, str] | None = None) -> None:
        super().__init__(states)
        self._db = db
        self.committed_at_remove: list[int] = []

    def remove(self, drive_id: str) -> int:
        self._db.call_log.append("remove")
        self.committed_at_remove.append(self._db.committed)
        return super().remove(drive_id)


class _RaceSession(FakeSession):
    """Runs `on_lock(table)` the first time a table is selected FOR UPDATE:
    stands in for a cancel that committed while the sweep waited for the
    lock (between its listing and its action)."""

    def __init__(self, on_lock: dict[str, Any]) -> None:
        super().__init__()
        self._on_lock = dict(on_lock)

    async def execute(self, stmt: Any) -> Any:
        if getattr(stmt, "_for_update_arg", None) is not None:
            hook = self._on_lock.pop(stmt.get_final_froms()[0].name, None)
            if hook is not None:
                hook()
        return await super().execute(stmt)


class _Hub:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def emit(self, topic, event_type, payload, *, persist=True, job_id=None, track_id=None, session=None):
        self.events.append(
            {"topic": topic, "event_type": event_type, "payload": payload, "job_id": job_id, "session": session}
        )


def _virtual(drive_id: str = "drv_iso1", lifecycle: DriveLifecycle = DriveLifecycle.ENROLLED) -> Drive:
    return Drive(
        id=drive_id,
        hostname=f"iso-{drive_id}",
        device_path="/source/Blade Runner.iso",
        status=DriveStatus.ONLINE,
        lifecycle=lifecycle,
        kind=DriveKind.VIRTUAL,
        source_kind=DriveSourceKind.ISO,
        source_path="Movies/Blade Runner.iso",
    )


def _optical(drive_id: str = "drv_sr0") -> Drive:
    return Drive(
        id=drive_id,
        hostname=f"scan-{drive_id}",
        device_path="/dev/sr0",
        status=DriveStatus.ONLINE,
        lifecycle=DriveLifecycle.ENROLLED,
    )


def _job(job_id: str, drive_id: str, status: JobStatus, created_at: datetime | None = None) -> Job:
    return Job(id=job_id, drive_id=drive_id, status=status, disc_type=DiscType.DVD, created_at=created_at)


# --- library helpers ---------------------------------------------------------


def test_library_configured_requires_env_and_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ISO_INGRESS_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "ARM_HOST_ISO_LIBRARY_PATH", "")
    assert iso_library.library_configured() is False  # env unset
    monkeypatch.setattr(settings, "ARM_HOST_ISO_LIBRARY_PATH", "/mnt/nas/iso")
    assert iso_library.library_configured() is True
    assert iso_library.library_host_path() == "/mnt/nas/iso"
    monkeypatch.setattr(settings, "ISO_INGRESS_ROOT", str(tmp_path / "absent"))
    assert iso_library.library_configured() is False  # mount missing


def test_library_configured_rejects_a_relative_host_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Docker reads a relative bind source as a named volume, so a relative
    ARM_HOST_ISO_LIBRARY_PATH is "not configured" even with the mount present."""
    monkeypatch.setattr(settings, "ISO_INGRESS_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "ARM_HOST_ISO_LIBRARY_PATH", "isos")
    assert iso_library.library_configured() is False
    monkeypatch.setattr(settings, "ARM_HOST_ISO_LIBRARY_PATH", "./mnt/iso")
    assert iso_library.library_configured() is False


def test_iso_host_path_joins_relative_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "ARM_HOST_ISO_LIBRARY_PATH", "/mnt/nas/iso/")
    assert iso_library.iso_host_path("Movies/Blade Runner.iso") == "/mnt/nas/iso/Movies/Blade Runner.iso"
    # An explicit library (the ripper manager's own Settings) wins over the global one.
    assert iso_library.iso_host_path("a.iso", library_host="/srv/isos") == "/srv/isos/a.iso"


# --- retire ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retire_marks_retired_offline_absent_and_removes_the_container() -> None:
    db = FakeSession()
    drive = _virtual()
    db.rows["drives"] = [drive]
    manager = _Manager()
    await iso_rips.retire_virtual_drive(db, manager, drive)  # type: ignore[arg-type]
    assert drive.lifecycle is DriveLifecycle.RETIRED
    assert drive.status is DriveStatus.OFFLINE
    assert drive.present is False
    assert manager.removed == ["drv_iso1"]
    assert drive in db.added
    assert db.committed == 1


@pytest.mark.asyncio
async def test_retire_commits_before_removing_the_container() -> None:
    """I1: the commit lands first, so a slow docker stop never holds the
    transaction (and the drive's row lock) open."""
    db = FakeSession()
    drive = _virtual()
    manager = _OrderingManager(db)
    await iso_rips.retire_virtual_drive(db, manager, drive)  # type: ignore[arg-type]
    assert db.call_log[-2:] == ["commit", "remove"]
    assert manager.committed_at_remove == [1]


@pytest.mark.asyncio
async def test_retire_logs_and_continues_when_removal_fails(caplog: pytest.LogCaptureFixture) -> None:
    db = FakeSession()
    drive = _virtual()
    manager = _Manager(remove_raises=RipperManagerError("APIError: boom"))
    with caplog.at_level(logging.WARNING, logger="arm_backend.iso_rips"):
        await iso_rips.retire_virtual_drive(db, manager, drive)  # type: ignore[arg-type]
    assert drive.lifecycle is DriveLifecycle.RETIRED
    assert "boom" in caplog.text


@pytest.mark.asyncio
async def test_retire_removes_the_rippers_iso_extraction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A ripper stopped mid-rip (cancel, crash) can't remove its unpacked
    image; retiring the drive does, and leaves other drives' extractions."""
    monkeypatch.setattr(settings, "RAW_ROOT", str(tmp_path))
    mine = tmp_path / ".iso-extract" / "drv_iso1" / "Blade Runner" / "BDMV"
    other = tmp_path / ".iso-extract" / "drv_iso2" / "Alien" / "BDMV"
    mine.mkdir(parents=True)
    other.mkdir(parents=True)
    (mine / "index.bdmv").write_bytes(b"x")

    await iso_rips.retire_virtual_drive(FakeSession(), _Manager(), _virtual())  # type: ignore[arg-type]

    assert not (tmp_path / ".iso-extract" / "drv_iso1").exists()
    assert other.is_dir()


# --- sweep -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sweep_returns_zero_without_virtual_drives() -> None:
    db = FakeSession()
    db.rows["drives"] = [_optical()]
    manager = _Manager()
    assert await iso_rips.sweep_virtual_drives(db, manager, _Hub()) == 0  # type: ignore[arg-type]
    assert manager.status_calls == []  # docker is not asked when there is nothing to check


@pytest.mark.asyncio
async def test_sweep_skips_running() -> None:
    db = FakeSession()
    drive = _virtual()
    db.rows["drives"] = [drive]
    db.rows["jobs"] = [_job("job_1", "drv_iso1", JobStatus.RIPPING)]
    manager, hub = _Manager({"drv_iso1": "running"}), _Hub()
    assert await iso_rips.sweep_virtual_drives(db, manager, hub) == 0  # type: ignore[arg-type]
    assert drive.lifecycle is DriveLifecycle.ENROLLED
    assert db.rows["jobs"][0].status is JobStatus.RIPPING
    assert manager.removed == [] and hub.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("state", ["unknown", "paused", "created", "restarting"])
async def test_sweep_leaves_unknown_and_live_states_alone(state: str) -> None:
    """Docker unreachable ("unknown") or a container not yet exited is never
    read as a dead rip: retiring on a guess would fail a live job."""
    db = FakeSession()
    drive = _virtual()
    db.rows["drives"] = [drive]
    db.rows["jobs"] = [_job("job_1", "drv_iso1", JobStatus.RIPPING)]
    manager = _Manager({"drv_iso1": state})
    assert await iso_rips.sweep_virtual_drives(db, manager, _Hub()) == 0  # type: ignore[arg-type]
    assert drive.lifecycle is DriveLifecycle.ENROLLED and manager.removed == []


@pytest.mark.asyncio
async def test_sweep_grace_skips_missing_within_window() -> None:
    """A `created_at` inside `SPAWN_GRACE_SECONDS`: the create-race window
    (the row is committed before `ensure_running` makes the container) — a
    "missing" container here is just that race, not a dead rip."""
    db = FakeSession()
    drive = _virtual()
    drive.created_at = datetime.now(UTC) - timedelta(seconds=10)
    db.rows["drives"] = [drive]
    manager, hub = _Manager(), _Hub()  # no container at all -> "missing"
    assert await iso_rips.sweep_virtual_drives(db, manager, hub) == 0  # type: ignore[arg-type]
    assert drive.lifecycle is DriveLifecycle.ENROLLED
    assert manager.removed == [] and hub.events == []


@pytest.mark.asyncio
async def test_sweep_grace_expired_retires() -> None:
    """Past the grace window, "missing" is judged the same as any other
    dead state."""
    db = FakeSession()
    drive = _virtual()
    drive.created_at = datetime.now(UTC) - timedelta(seconds=iso_rips.SPAWN_GRACE_SECONDS + 1)
    db.rows["drives"] = [drive]
    manager, hub = _Manager(), _Hub()
    assert await iso_rips.sweep_virtual_drives(db, manager, hub) == 1  # type: ignore[arg-type]
    assert drive.lifecycle is DriveLifecycle.RETIRED
    assert manager.removed == ["drv_iso1"]


@pytest.mark.asyncio
async def test_sweep_grace_none_created_at_retires_immediately() -> None:
    """A drive with no `created_at` gets no grace — nothing to measure the
    window from, so a "missing" container is judged immediately."""
    db = FakeSession()
    drive = _virtual()
    assert drive.created_at is None
    db.rows["drives"] = [drive]
    manager, hub = _Manager(), _Hub()
    assert await iso_rips.sweep_virtual_drives(db, manager, hub) == 1  # type: ignore[arg-type]
    assert drive.lifecycle is DriveLifecycle.RETIRED
    assert manager.removed == ["drv_iso1"]


@pytest.mark.asyncio
async def test_sweep_retires_exited_with_terminal_job() -> None:
    db = FakeSession()
    drive = _virtual()
    db.rows["drives"] = [drive]
    db.rows["jobs"] = [_job("job_1", "drv_iso1", JobStatus.RIPPED)]
    manager, hub = _Manager({"drv_iso1": "exited"}), _Hub()
    assert await iso_rips.sweep_virtual_drives(db, manager, hub) == 1  # type: ignore[arg-type]
    assert drive.lifecycle is DriveLifecycle.RETIRED
    assert manager.removed == ["drv_iso1"]
    assert db.rows["jobs"][0].status is JobStatus.RIPPED
    assert hub.events == []
    assert db.committed == 1


@pytest.mark.asyncio
async def test_sweep_retires_exited_with_no_job() -> None:
    """The scan failed before a job existed: the ripper exited, nothing to fail."""
    db = FakeSession()
    drive = _virtual()
    db.rows["drives"] = [drive]
    manager, hub = _Manager({"drv_iso1": "exited"}), _Hub()
    assert await iso_rips.sweep_virtual_drives(db, manager, hub) == 1  # type: ignore[arg-type]
    assert drive.lifecycle is DriveLifecycle.RETIRED and manager.removed == ["drv_iso1"]
    assert hub.events == []


@pytest.mark.asyncio
async def test_sweep_fails_unfinished_job_and_retires() -> None:
    db = FakeSession()
    drive = _virtual()
    db.rows["drives"] = [drive]
    job = _job("job_1", "drv_iso1", JobStatus.RIPPING)
    db.rows["jobs"] = [job]
    db.rows["tracks"] = [
        Track(job_id="job_1", kind=TrackKind.VIDEO_TITLE, index=0, source_ref="0", status=TrackStatus.DONE),
        Track(job_id="job_1", kind=TrackKind.VIDEO_TITLE, index=1, source_ref="1", status=TrackStatus.FAILED),
        Track(job_id="job_1", kind=TrackKind.VIDEO_TITLE, index=2, source_ref="2", status=TrackStatus.IN_PROGRESS),
        Track(job_id="job_other", kind=TrackKind.VIDEO_TITLE, index=0, source_ref="0", status=TrackStatus.DONE),
    ]
    manager, hub = _Manager(), _Hub()  # no container at all -> "missing"
    assert await iso_rips.sweep_virtual_drives(db, manager, hub) == 1  # type: ignore[arg-type]
    assert job.status is JobStatus.FAILED
    assert job.ripped_at is not None  # same as every other rip_complete outcome
    assert drive.lifecycle is DriveLifecycle.RETIRED and manager.removed == ["drv_iso1"]
    assert len(hub.events) == 1
    event = hub.events[0]
    assert event["topic"] == "ripper.events" and event["event_type"] == "rip.failed"
    assert event["job_id"] == "job_1" and event["session"] is db
    assert event["payload"] == {
        "job_id": "job_1",
        "drive_id": "drv_iso1",
        "status": "failed",
        "tracks_done": 1,
        "tracks_failed": 1,
        "tracks_total": 3,
        "reason": "ISO ripper stopped unexpectedly",
    }
    assert db.committed == 1


@pytest.mark.asyncio
async def test_sweep_judges_the_latest_job() -> None:
    db = FakeSession()
    drive = _virtual()
    db.rows["drives"] = [drive]
    now = datetime.now(UTC)
    old = _job("job_old", "drv_iso1", JobStatus.RIPPING, created_at=now - timedelta(hours=1))
    new = _job("job_new", "drv_iso1", JobStatus.RIPPED, created_at=now)
    db.rows["jobs"] = [new, old]
    hub = _Hub()
    assert await iso_rips.sweep_virtual_drives(db, _Manager({"drv_iso1": "exited"}), hub) == 1  # type: ignore[arg-type]
    assert old.status is JobStatus.RIPPING and hub.events == []


@pytest.mark.asyncio
async def test_sweep_ignores_optical_and_retired() -> None:
    db = FakeSession()
    optical = _optical()
    retired = _virtual("drv_gone", lifecycle=DriveLifecycle.RETIRED)
    db.rows["drives"] = [optical, retired]
    db.rows["jobs"] = [_job("job_1", "drv_sr0", JobStatus.RIPPING), _job("job_2", "drv_gone", JobStatus.RIPPING)]
    manager = _Manager()
    assert await iso_rips.sweep_virtual_drives(db, manager, _Hub()) == 0  # type: ignore[arg-type]
    assert optical.lifecycle is DriveLifecycle.ENROLLED and retired.lifecycle is DriveLifecycle.RETIRED
    assert all(j.status is JobStatus.RIPPING for j in db.rows["jobs"])
    assert manager.removed == [] and manager.status_calls == []


@pytest.mark.asyncio
async def test_sweep_skips_a_drive_retired_after_the_listing() -> None:
    """I1: a cancel abandoned the job and retired the drive between the
    sweep's listing and its action. The locked re-read sees that, so the
    abandoned job is not turned into a failure and nothing is removed twice."""
    job = _job("job_1", "drv_iso1", JobStatus.RIPPING)
    drive = _virtual()

    def cancel_committed() -> None:
        job.status = JobStatus.ABANDONED
        drive.lifecycle = DriveLifecycle.RETIRED

    db = _RaceSession({"drives": cancel_committed})
    db.rows["drives"] = [drive]
    db.rows["jobs"] = [job]
    manager, hub = _Manager({"drv_iso1": "exited"}), _Hub()
    assert await iso_rips.sweep_virtual_drives(db, manager, hub) == 0  # type: ignore[arg-type]
    assert job.status is JobStatus.ABANDONED
    assert hub.events == [] and manager.removed == []
    assert db.locked == ["drives"]
    assert db.committed == 1  # the lock is released


@pytest.mark.asyncio
async def test_sweep_does_not_fail_a_job_that_became_terminal_after_the_listing() -> None:
    """I1: the job went terminal after the listing while the drive is still
    enrolled. The fresh job read wins: retire only, no `rip.failed`."""
    job = _job("job_1", "drv_iso1", JobStatus.RIPPING)
    drive = _virtual()

    def finished() -> None:
        job.status = JobStatus.ABANDONED

    db = _RaceSession({"jobs": finished})
    db.rows["drives"] = [drive]
    db.rows["jobs"] = [job]
    manager, hub = _OrderingManager(db, {"drv_iso1": "exited"}), _Hub()
    assert await iso_rips.sweep_virtual_drives(db, manager, hub) == 1  # type: ignore[arg-type]
    assert job.status is JobStatus.ABANDONED and hub.events == []
    assert drive.lifecycle is DriveLifecycle.RETIRED
    assert db.locked == ["drives", "jobs"]
    assert db.call_log[-2:] == ["commit", "remove"]


@pytest.mark.asyncio
async def test_sweep_skips_a_drive_deleted_after_the_listing() -> None:
    drive = _virtual()
    db = _RaceSession({"drives": lambda: db.rows["drives"].clear()})
    db.rows["drives"] = [drive]
    manager = _Manager({"drv_iso1": "exited"})
    assert await iso_rips.sweep_virtual_drives(db, manager, _Hub()) == 0  # type: ignore[arg-type]
    assert manager.removed == []


@pytest.mark.asyncio
async def test_cancel_commits_the_abandon_before_removing_the_container() -> None:
    """I1: cancel locks the drive, stages abandon + retire, commits, and
    only then removes the container."""
    db = FakeSession()
    drive = _virtual()
    job = _job("job_1", "drv_iso1", JobStatus.RIPPING)
    db.rows["drives"] = [drive]
    db.rows["jobs"] = [job]
    manager, hub = _OrderingManager(db), _Hub()
    await iso_rips.cancel_iso_rip(db, manager, hub, "drv_iso1")  # type: ignore[arg-type]
    assert job.status is JobStatus.ABANDONED and drive.lifecycle is DriveLifecycle.RETIRED
    assert db.locked == ["drives", "jobs"]
    assert db.call_log[-2:] == ["commit", "remove"]
    assert manager.committed_at_remove == [1]


# --- watchdog ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_watchdog_sweeps_logs_failures_and_stops_on_cancel(caplog: pytest.LogCaptureFixture) -> None:
    db = FakeSession()
    drive = _virtual()
    db.rows["drives"] = [drive]
    calls = 0

    def factory() -> FakeSession:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("db down")
        if calls == 3:
            raise asyncio.CancelledError
        return db

    manager = _Manager({"drv_iso1": "exited"})
    with caplog.at_level(logging.INFO, logger="arm_backend.iso_rips"), pytest.raises(asyncio.CancelledError):
        await iso_rips.run_virtual_drive_watchdog(factory, manager, _Hub(), interval=0)  # type: ignore[arg-type]
    assert calls == 3
    assert "db down" in caplog.text  # the first pass failed and the loop kept going
    assert drive.lifecycle is DriveLifecycle.RETIRED  # the second pass swept
