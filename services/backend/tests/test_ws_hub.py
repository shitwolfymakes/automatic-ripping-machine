"""WSHub fan-out, throttle, and persist semantics."""

from __future__ import annotations

import asyncio
import os
from typing import Any


os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

from arm_backend.ws.hub import PROGRESS_THROTTLE_SECONDS, WSHub  # noqa: E402


class _FakeWS:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.fail_send = False

    async def send_json(self, frame: dict[str, Any]) -> None:
        if self.fail_send:
            raise ConnectionError("simulated send failure")
        self.sent.append(frame)


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[Any] = []
        self.flushed = 0

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        self.flushed += 1


async def test_subscribe_then_emit_fans_out() -> None:
    hub = WSHub()
    ws = _FakeWS()
    await hub.subscribe(ws, "ripper.events")  # type: ignore[arg-type]
    sess = _FakeSession()

    await hub.emit(
        topic="ripper.events",
        event_type="rip.started",
        payload={"job_id": "job_01JZXR7K3M5Q8N4VWA00000001"},
        job_id="job_01JZXR7K3M5Q8N4VWA00000001",
        session=sess,  # type: ignore[arg-type]
    )

    assert len(ws.sent) == 1
    assert ws.sent[0]["event_type"] == "rip.started"
    assert ws.sent[0]["topic"] == "ripper.events"
    # Persist=True path adds an Event row.
    assert len(sess.added) == 1


async def test_emit_no_subscribers_is_noop() -> None:
    hub = WSHub()
    sess = _FakeSession()
    await hub.emit(
        topic="ripper.events",
        event_type="rip.started",
        payload={},
        session=sess,  # type: ignore[arg-type]
    )
    # Still persists even without subscribers.
    assert len(sess.added) == 1


async def test_progress_topic_is_not_persisted() -> None:
    hub = WSHub()
    ws = _FakeWS()
    await hub.subscribe(ws, "ripper.progress.job_01JZXR7K3M5Q8N4VWA00000001")  # type: ignore[arg-type]
    sess = _FakeSession()

    await hub.emit(
        topic="ripper.progress.job_01JZXR7K3M5Q8N4VWA00000001",
        event_type="ripper.progress",
        payload={"track_id": "trk_1", "progress_pct": 12.3},
        persist=False,
        track_id="trk_1",
    )

    assert len(ws.sent) == 1
    assert sess.added == []


async def test_progress_throttle_collapses_bursts() -> None:
    hub = WSHub()
    ws = _FakeWS()
    await hub.subscribe(ws, "ripper.progress.job_01JZXR7K3M5Q8N4VWA00000001")  # type: ignore[arg-type]

    for pct in range(10):
        await hub.emit(
            topic="ripper.progress.job_01JZXR7K3M5Q8N4VWA00000001",
            event_type="ripper.progress",
            payload={"track_id": "trk_1", "progress_pct": pct},
            persist=False,
            track_id="trk_1",
        )

    # 10 emits within the throttle window → 1 delivery
    assert len(ws.sent) == 1
    assert ws.sent[0]["payload"]["progress_pct"] == 0


async def test_progress_throttle_admits_after_window() -> None:
    hub = WSHub()
    ws = _FakeWS()
    await hub.subscribe(ws, "ripper.progress.job_01JZXR7K3M5Q8N4VWA00000001")  # type: ignore[arg-type]

    await hub.emit(
        topic="ripper.progress.job_01JZXR7K3M5Q8N4VWA00000001",
        event_type="ripper.progress",
        payload={"track_id": "trk_1", "progress_pct": 0.0},
        persist=False,
        track_id="trk_1",
    )
    await asyncio.sleep(PROGRESS_THROTTLE_SECONDS + 0.05)
    await hub.emit(
        topic="ripper.progress.job_01JZXR7K3M5Q8N4VWA00000001",
        event_type="ripper.progress",
        payload={"track_id": "trk_1", "progress_pct": 50.0},
        persist=False,
        track_id="trk_1",
    )
    assert len(ws.sent) == 2


async def test_progress_throttle_is_per_track() -> None:
    hub = WSHub()
    ws = _FakeWS()
    await hub.subscribe(ws, "ripper.progress.job_01JZXR7K3M5Q8N4VWA00000001")  # type: ignore[arg-type]

    await hub.emit(
        topic="ripper.progress.job_01JZXR7K3M5Q8N4VWA00000001",
        event_type="ripper.progress",
        payload={"track_id": "trk_1"},
        persist=False,
        track_id="trk_1",
    )
    await hub.emit(
        topic="ripper.progress.job_01JZXR7K3M5Q8N4VWA00000001",
        event_type="ripper.progress",
        payload={"track_id": "trk_2"},
        persist=False,
        track_id="trk_2",
    )
    # Two distinct tracks → no cross-track throttle.
    assert len(ws.sent) == 2


async def test_unsubscribe_stops_delivery() -> None:
    hub = WSHub()
    ws = _FakeWS()
    sess = _FakeSession()
    await hub.subscribe(ws, "ripper.events")  # type: ignore[arg-type]
    await hub.unsubscribe(ws, "ripper.events")  # type: ignore[arg-type]

    await hub.emit(
        topic="ripper.events",
        event_type="rip.started",
        payload={},
        session=sess,  # type: ignore[arg-type]
    )
    assert ws.sent == []


async def test_failing_subscriber_is_evicted() -> None:
    hub = WSHub()
    good = _FakeWS()
    bad = _FakeWS()
    bad.fail_send = True
    sess = _FakeSession()
    await hub.subscribe(good, "ripper.events")  # type: ignore[arg-type]
    await hub.subscribe(bad, "ripper.events")  # type: ignore[arg-type]

    await hub.emit(
        topic="ripper.events",
        event_type="rip.started",
        payload={},
        session=sess,  # type: ignore[arg-type]
    )
    assert len(good.sent) == 1
    assert hub.subscriber_count("ripper.events") == 1


async def test_disconnect_cleans_all_subscriptions() -> None:
    hub = WSHub()
    ws = _FakeWS()
    await hub.subscribe(ws, "topic_a")  # type: ignore[arg-type]
    await hub.subscribe(ws, "topic_b")  # type: ignore[arg-type]
    await hub.disconnect(ws)  # type: ignore[arg-type]
    assert hub.subscriber_count("topic_a") == 0
    assert hub.subscriber_count("topic_b") == 0
