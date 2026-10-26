"""HeartbeatPump reports the whole ProgressState on both surfaces (D-242, D-248)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

import arm_transcode.heartbeat as hb
from arm_transcode.heartbeat import HeartbeatPump, ProgressState


class _FakeApi:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def heartbeat(self, task_id: str, **kwargs: Any) -> None:
        self.calls.append({"task_id": task_id, **kwargs})


class _FakeWs:
    def __init__(self) -> None:
        self.published: list[dict[str, Any]] = []

    async def publish(self, *, topic: str, event_type: str, payload: dict[str, Any]) -> None:
        self.published.append({"topic": topic, "event_type": event_type, "payload": payload})


@pytest.mark.asyncio
async def test_pump_sends_eta_pass_and_frame_rates_over_rest_and_ws(monkeypatch) -> None:
    monkeypatch.setattr(hb, "REST_HEARTBEAT_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(hb, "WS_PUBLISH_INTERVAL_SECONDS", 0.01)
    api, ws = _FakeApi(), _FakeWs()
    state = ProgressState(pct=42, eta_seconds=600, current_pass="1/2", fps=45.67, avg_fps=23.45)

    async with HeartbeatPump(api=api, ws=ws, task_id="txt_1", state=state):  # type: ignore[arg-type]
        for _ in range(100):
            if api.calls and ws.published:
                break
            await asyncio.sleep(0.01)

    assert api.calls[0] == {
        "task_id": "txt_1",
        "progress_pct": 42,
        "current_pass": "1/2",
        "eta_seconds": 600,
        "fps": 45.67,
        "avg_fps": 23.45,
    }
    assert ws.published[0]["topic"] == "transcode.progress.txt_1"
    assert ws.published[0]["payload"] == {
        "task_id": "txt_1",
        "progress_pct": 42,
        "eta_seconds": 600,
        "current_pass": "1/2",
        "fps": 45.67,
        "avg_fps": 23.45,
    }
