from __future__ import annotations

import os
import stat
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

import pytest  # noqa: E402

from arm_backend.notifications.bash_listener import BashListener  # noqa: E402
from arm_backend.notifications.message import Message  # noqa: E402
from arm_common import DiscType, Job, JobStatus, NotificationChannel, NotificationDispatchLog  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402


def _script(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text('#!/usr/bin/env bash\n# arm-input: TO label="Recipient" required\n' + body)
    p.chmod(p.stat().st_mode | stat.S_IXUSR)
    return p


def _job() -> Job:
    return Job(id="job_1", drive_id="sr0", disc_type=DiscType.DVD, title="Dune", year=2021, status=JobStatus.RIPPED, metadata_json={}, resumed_from_crash=False)


def _msg(*, enabled: bool = True, event_type: str = "rip.completed") -> Message:
    return Message(
        event_id="evt_1", event_type=event_type, job_id="job_1",
        default_title="ARM: rip completed - {job_title}", default_body="{job_title} done ({tracks_done}/{tracks_total}).",
        job=_job(), payload={"tracks_done": 3, "tracks_total": 3}, apprise_enabled=enabled,
    )


def _channel(script: str, *, enabled: bool = True, events=("rip.completed",), templates=None, inputs=None) -> NotificationChannel:
    return NotificationChannel(
        id="ncl_bash", type="bash", name="hook", enabled=enabled,
        config={"type": "bash", "script": script, "timeout_seconds": 5, "inputs": inputs if inputs is not None else {"TO": "me@x"}, "secret_keys": []},
        subscribed_events=list(events), templates=templates or {},
    )


def _listener(tmp_path: Path) -> BashListener:
    return BashListener(scripts_root=str(tmp_path), media_root="/media", raw_root="/raw")


def _logs(db: FakeSession) -> list[NotificationDispatchLog]:
    return [o for o in db.added if isinstance(o, NotificationDispatchLog)]


@pytest.mark.asyncio
async def test_runs_script_and_logs_success(tmp_path: Path) -> None:
    out = tmp_path / "out.txt"
    _script(tmp_path, "ok.sh", f'printf "%s|%s|%s|%s" "$1" "$ARM_JOB_TITLE" "$ARM_TRACKS_DONE" "$TO" > "{out}"\n')
    ch = _channel("ok.sh", templates={"rip.completed": {"inputs": {"TO": "oncall@x"}}})
    db = FakeSession()
    db.rows["notification_channels"] = [ch]
    await _listener(tmp_path).handle(db, _msg())
    assert out.read_text() == "ARM: rip completed - Dune|Dune|3|oncall@x"
    assert ch.last_success_at is not None and ch.last_error is None
    (log,) = _logs(db)
    assert log.success and log.channel_id == "ncl_bash" and log.event_id == "evt_1" and log.title == "ARM: rip completed - Dune"


@pytest.mark.asyncio
async def test_script_failure_recorded(tmp_path: Path) -> None:
    _script(tmp_path, "bad.sh", "echo nope >&2; exit 2\n")
    ch = _channel("bad.sh")
    db = FakeSession()
    db.rows["notification_channels"] = [ch]
    await _listener(tmp_path).handle(db, _msg())
    assert ch.last_error == "script exit code 2: nope" and ch.last_success_at is None
    (log,) = _logs(db)
    assert not log.success and log.error == "script exit code 2: nope"


@pytest.mark.asyncio
async def test_hook_error_recorded_with_empty_title(tmp_path: Path) -> None:
    _script(tmp_path, "ok.sh", "exit 0\n")
    ch = _channel("ok.sh", inputs={})  # TO required
    db = FakeSession()
    db.rows["notification_channels"] = [ch]
    await _listener(tmp_path).handle(db, _msg())
    assert ch.last_error == "input TO is required"
    (log,) = _logs(db)
    assert not log.success and log.title == ""


@pytest.mark.asyncio
async def test_skips_when_notifications_disabled(tmp_path: Path) -> None:
    _script(tmp_path, "ok.sh", "exit 0\n")
    ch = _channel("ok.sh")
    db = FakeSession()
    db.rows["notification_channels"] = [ch]
    await _listener(tmp_path).handle(db, _msg(enabled=False))
    assert ch.last_fired_at is None and _logs(db) == []


@pytest.mark.asyncio
async def test_skips_disabled_unsubscribed_and_other_types(tmp_path: Path) -> None:
    _script(tmp_path, "ok.sh", "exit 0\n")
    db = FakeSession()
    db.rows["notification_channels"] = [
        _channel("ok.sh", enabled=False),
        _channel("ok.sh", events=("rip.failed",)),
        NotificationChannel(id="ncl_a", type="apprise", name="a", enabled=True, config={"type": "apprise", "url": "json://x"}, subscribed_events=["rip.completed"], templates={}),
    ]
    await _listener(tmp_path).handle(db, _msg())
    assert _logs(db) == []
