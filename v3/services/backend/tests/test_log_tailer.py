"""Phase 12 — `LogTailer.tick` behaviour with a fake WSHub.

The tailer scans a log dir, parses JSONL, gates on subscriber count via
the hub, and re-emits to `logs.{job_id}` for any line whose job_id has
at least one subscriber.

Tests work directly against `LogTailer.tick()` — no asyncio.run loop —
so we can step the tailer one drain at a time and inspect emit calls.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from arm_backend.log_tailer import LogTailer


@dataclass
class _RecordedEmit:
    topic: str
    event_type: str
    payload: dict[str, Any]
    persist: bool
    job_id: str | None
    track_id: str | None


@dataclass
class _FakeHub:
    """Mimics the slice of `WSHub` the tailer uses.

    `subscriber_count` returns the integer the test pre-loaded into
    `subscriptions[topic]`. `emit` records every call for assertion.
    """

    subscriptions: dict[str, int] = field(default_factory=dict)
    emits: list[_RecordedEmit] = field(default_factory=list)

    def subscriber_count(self, topic: str) -> int:
        return self.subscriptions.get(topic, 0)

    async def emit(
        self,
        *,
        topic: str,
        event_type: str,
        payload: dict[str, Any],
        persist: bool = True,
        job_id: str | None = None,
        track_id: str | None = None,
    ) -> None:
        self.emits.append(
            _RecordedEmit(
                topic=topic,
                event_type=event_type,
                payload=payload,
                persist=persist,
                job_id=job_id,
                track_id=track_id,
            )
        )


def _append(path: Path, record: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")


def _record(
    *,
    job_id: str | None = "job_01JZXR7K3M5Q8N4VWA00000001",
    track_id: str | None = None,
    msg: str = "ok",
    service: str = "arm-backend",
    logger_name: str = "arm_backend.test",
) -> dict[str, Any]:
    return {
        "ts": "2026-04-30T00:00:00+00:00",
        "level": "info",
        "service": service,
        "job_id": job_id,
        "track_id": track_id,
        "session_application_id": None,
        "msg": msg,
        "extra": {"logger": logger_name},
    }


@pytest.mark.asyncio
async def test_emits_when_job_has_subscriber(tmp_path: Path) -> None:
    log_path = tmp_path / "arm-backend.log"
    log_path.touch()
    hub = _FakeHub(subscriptions={"logs.job_01JZXR7K3M5Q8N4VWA00000001": 1})
    tailer = LogTailer(hub, log_dir=str(tmp_path))  # type: ignore[arg-type]

    await tailer.tick()  # discover + seek-to-end
    _append(log_path, _record())
    await tailer.tick()

    assert len(hub.emits) == 1
    emit = hub.emits[0]
    assert emit.topic == "logs.job_01JZXR7K3M5Q8N4VWA00000001"
    assert emit.event_type == "log.line"
    assert emit.persist is False
    assert emit.job_id == "job_01JZXR7K3M5Q8N4VWA00000001"
    assert emit.payload["msg"] == "ok"


@pytest.mark.asyncio
async def test_skips_record_with_null_job_id(tmp_path: Path) -> None:
    log_path = tmp_path / "arm-backend.log"
    log_path.touch()
    hub = _FakeHub(subscriptions={"logs.job_01JZXR7K3M5Q8N4VWA00000001": 1})
    tailer = LogTailer(hub, log_dir=str(tmp_path))  # type: ignore[arg-type]

    await tailer.tick()
    _append(log_path, _record(job_id=None))
    await tailer.tick()

    assert hub.emits == []


@pytest.mark.asyncio
async def test_skips_when_no_subscribers(tmp_path: Path) -> None:
    log_path = tmp_path / "arm-backend.log"
    log_path.touch()
    hub = _FakeHub()  # no subscriptions
    tailer = LogTailer(hub, log_dir=str(tmp_path))  # type: ignore[arg-type]

    await tailer.tick()
    _append(log_path, _record())
    await tailer.tick()

    assert hub.emits == []


@pytest.mark.asyncio
async def test_bad_json_is_silently_skipped(tmp_path: Path) -> None:
    log_path = tmp_path / "arm-backend.log"
    log_path.touch()
    hub = _FakeHub(subscriptions={"logs.job_01JZXR7K3M5Q8N4VWA00000001": 1})
    tailer = LogTailer(hub, log_dir=str(tmp_path))  # type: ignore[arg-type]

    await tailer.tick()
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write("this is not json\n")
        fh.write(json.dumps(_record()) + "\n")
    await tailer.tick()

    # The bad line is dropped; the good line is emitted.
    assert len(hub.emits) == 1
    assert hub.emits[0].topic == "logs.job_01JZXR7K3M5Q8N4VWA00000001"


@pytest.mark.asyncio
async def test_loop_guard_skips_hub_self_logs(tmp_path: Path) -> None:
    """Records emitted from `arm_backend.ws.hub.*` must not feed back into the tailer."""
    log_path = tmp_path / "arm-backend.log"
    log_path.touch()
    hub = _FakeHub(subscriptions={"logs.job_01JZXR7K3M5Q8N4VWA00000001": 1})
    tailer = LogTailer(hub, log_dir=str(tmp_path))  # type: ignore[arg-type]

    await tailer.tick()
    _append(log_path, _record(logger_name="arm_backend.ws.hub"))
    _append(log_path, _record(logger_name="arm_backend.ws.hub.send"))
    _append(log_path, _record(logger_name="arm_backend.routers.ripper"))
    await tailer.tick()

    # Only the third (non-hub) line is emitted.
    assert len(hub.emits) == 1
    assert hub.emits[0].payload["extra"]["logger"] == "arm_backend.routers.ripper"


@pytest.mark.asyncio
async def test_rotation_via_inode_change(tmp_path: Path) -> None:
    """RotatingFileHandler renames the live file and opens a new one;
    the tailer must follow by reopening on inode mismatch.
    """
    log_path = tmp_path / "arm-backend.log"
    log_path.touch()
    hub = _FakeHub(subscriptions={"logs.job_01JZXR7K3M5Q8N4VWA00000001": 1})
    tailer = LogTailer(hub, log_dir=str(tmp_path))  # type: ignore[arg-type]

    await tailer.tick()  # open + seek-to-end on empty file

    # Append one line in the original file, drain.
    _append(log_path, _record(msg="pre-rotate"))
    await tailer.tick()
    assert len(hub.emits) == 1

    # Simulate rotation: rename to .1, create a fresh file at the same path.
    rotated = tmp_path / "arm-backend.log.1"
    os.rename(log_path, rotated)
    log_path.touch()
    _append(log_path, _record(msg="post-rotate"))
    await tailer.tick()

    msgs = [e.payload["msg"] for e in hub.emits]
    assert "pre-rotate" in msgs
    assert "post-rotate" in msgs


@pytest.mark.asyncio
async def test_new_file_picked_up_on_subsequent_tick(tmp_path: Path) -> None:
    """A transcode container that starts mid-run creates a new log file
    (`arm-transcode-<task>.log`); the tailer's scandir picks it up.
    """
    hub = _FakeHub(subscriptions={"logs.job_01JZXR7K3M5Q8N4VWA00000001": 1})
    tailer = LogTailer(hub, log_dir=str(tmp_path))  # type: ignore[arg-type]

    await tailer.tick()  # discovers nothing
    new_path = tmp_path / "arm-transcode-abcdef.log"
    new_path.touch()
    _append(new_path, _record(msg="transcoder started"))
    await tailer.tick()  # discover + seek-to-end (skip past the line)
    _append(new_path, _record(msg="track done"))
    await tailer.tick()

    msgs = [e.payload["msg"] for e in hub.emits]
    # The pre-discovery line is skipped (we seek-to-end on open). Only
    # post-discovery lines reach the hub.
    assert "track done" in msgs
    assert "transcoder started" not in msgs


@pytest.mark.asyncio
async def test_per_job_log_appended_for_lines_with_job_id(tmp_path: Path) -> None:
    """Every line carrying a `job_id` lands in `<log_dir>/jobs/<job_id>.log`,
    not just the WS topic. This file is the source of truth for the zip /
    stream endpoints and is removed on job-delete."""
    log_path = tmp_path / "arm-backend.log"
    log_path.touch()
    hub = _FakeHub(subscriptions={"logs.job_01JZXR7K3M5Q8N4VWA00000001": 1})
    tailer = LogTailer(hub, log_dir=str(tmp_path))  # type: ignore[arg-type]

    await tailer.tick()
    _append(log_path, _record(msg="line one"))
    _append(log_path, _record(msg="line two"))
    await tailer.tick()

    per_job = tmp_path / "jobs" / "job_01JZXR7K3M5Q8N4VWA00000001.log"
    assert per_job.is_file()
    lines = [json.loads(line) for line in per_job.read_text().splitlines()]
    assert [line["msg"] for line in lines] == ["line one", "line two"]


@pytest.mark.asyncio
async def test_per_job_log_aggregates_multiple_services(tmp_path: Path) -> None:
    """Lines from different service log files but the same job_id all
    end up in the same per-job file, in the order the tailer drains them."""
    backend_log = tmp_path / "arm-backend.log"
    ripper_log = tmp_path / "arm-ripper-sr0.log"
    backend_log.touch()
    ripper_log.touch()
    hub = _FakeHub()  # no WS subscribers; per-job write is independent
    tailer = LogTailer(hub, log_dir=str(tmp_path))  # type: ignore[arg-type]

    await tailer.tick()
    _append(backend_log, _record(service="arm-backend", msg="backend line"))
    _append(ripper_log, _record(service="arm-ripper-sr0", msg="ripper line"))
    await tailer.tick()

    per_job = tmp_path / "jobs" / "job_01JZXR7K3M5Q8N4VWA00000001.log"
    services = {json.loads(line)["service"] for line in per_job.read_text().splitlines()}
    assert services == {"arm-backend", "arm-ripper-sr0"}


@pytest.mark.asyncio
async def test_per_job_log_skipped_for_lines_without_job_id(tmp_path: Path) -> None:
    """Records with `job_id=None` are not file-persisted (there's no
    file to write to). The jobs/ dir may or may not be created."""
    log_path = tmp_path / "arm-backend.log"
    log_path.touch()
    hub = _FakeHub()
    tailer = LogTailer(hub, log_dir=str(tmp_path))  # type: ignore[arg-type]

    await tailer.tick()
    _append(log_path, _record(job_id=None, msg="orphan"))
    await tailer.tick()

    jobs_dir = tmp_path / "jobs"
    if jobs_dir.exists():
        assert list(jobs_dir.iterdir()) == []


@pytest.mark.asyncio
async def test_per_job_log_records_hub_self_lines(tmp_path: Path) -> None:
    """The WS-emit loop guard skips re-publishing hub-self records onto
    the WS, but those records still hit the per-job file — the file is
    a passive append-only store with no feedback risk, and a hub-emit
    failure is genuinely useful diagnostic content."""
    log_path = tmp_path / "arm-backend.log"
    log_path.touch()
    hub = _FakeHub(subscriptions={"logs.job_01JZXR7K3M5Q8N4VWA00000001": 1})
    tailer = LogTailer(hub, log_dir=str(tmp_path))  # type: ignore[arg-type]

    await tailer.tick()
    _append(log_path, _record(logger_name="arm_backend.ws.hub.fanout", msg="hub self log"))
    await tailer.tick()

    # Loop guard kept this off the WS.
    assert hub.emits == []
    # But it's in the per-job file.
    per_job = tmp_path / "jobs" / "job_01JZXR7K3M5Q8N4VWA00000001.log"
    assert per_job.is_file()
    assert "hub self log" in per_job.read_text()
