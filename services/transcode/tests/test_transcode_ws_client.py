"""Characterization tests for `WSClient._run_once` against a faked websocket connection."""

from __future__ import annotations

import json
import logging
import ssl
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest

from arm_common.schemas import WSAck, WSAuthRequest, WSEnvelope, WSError, WSSubscribeRequest
from arm_transcode import ws_client as ws_module
from arm_transcode.ws_client import SERVICE_TOKEN_SUBPROTOCOL, WSAuthFailed, WSClient

URL = "wss://backend.test/ws"
TOKEN = "tok-123"
LOGGER = "arm_transcode.ws_client"


class FakeConn:
    def __init__(self, ack: str, frames: list[str]) -> None:
        self._ack = ack
        self._frames = frames
        self.sent: list[str] = []

    async def send(self, data: str) -> None:
        self.sent.append(data)

    async def recv(self) -> str:
        return self._ack

    def __aiter__(self) -> AsyncIterator[str]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[str]:
        for frame in self._frames:
            yield frame


class FakeConnect:
    def __init__(self, conn: FakeConn) -> None:
        self.conn = conn
        self.args: tuple[Any, ...] = ()
        self.kwargs: dict[str, Any] = {}

    def __call__(self, *args: Any, **kwargs: Any) -> FakeConnect:
        self.args, self.kwargs = args, kwargs
        return self

    async def __aenter__(self) -> FakeConn:
        return self.conn

    async def __aexit__(self, *exc: object) -> None:
        return None


def _event(topic: str, event_type: str = "x") -> str:
    return WSEnvelope(
        event_id="e1", event_type=event_type, emitted_at=datetime(2026, 1, 1, tzinfo=UTC), topic=topic
    ).model_dump_json()


def _client(ctx: ssl.SSLContext | None = None) -> WSClient:
    return WSClient(url=URL, service_token=TOKEN, hostname="host-a", task_id="task-1", ssl_context=ctx)


def _install(monkeypatch: pytest.MonkeyPatch, ack: str, frames: list[str] | None = None) -> FakeConnect:
    fake = FakeConnect(FakeConn(ack, frames or []))
    monkeypatch.setattr(ws_module.websockets, "connect", fake)
    return fake


ACK = WSAck().model_dump_json()


async def test_connect_kwargs_and_auth_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = ssl.create_default_context()
    fake = _install(monkeypatch, ACK)
    await _client(ctx)._run_once()
    assert fake.args == (URL,)
    assert fake.kwargs == {
        "ssl": ctx,
        "subprotocols": [SERVICE_TOKEN_SUBPROTOCOL],
        "additional_headers": [("X-ARM-Hostname", "host-a"), ("X-ARM-Task-Id", "task-1")],
        "ping_interval": 20.0,
        "ping_timeout": 20.0,
        "max_size": 2**20,
    }
    assert fake.conn.sent[0] == WSAuthRequest(token=TOKEN).model_dump_json()


async def test_error_ack_raises_with_code_and_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, WSError(code=4401, reason="bad token").model_dump_json())
    with pytest.raises(WSAuthFailed, match="code=4401 reason=bad token"):
        await _client()._run_once()


async def test_unexpected_first_frame_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, json.dumps({"op": "event"}))
    with pytest.raises(WSAuthFailed, match="unexpected first frame"):
        await _client()._run_once()


async def test_valid_ack_sets_connected_and_subscribes(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _install(monkeypatch, ACK)
    client = _client()

    async def h(env: WSEnvelope) -> None:  # pragma: no cover - never dispatched
        pass

    await client.subscribe("t.a", h)
    await client.subscribe("t.b", h)
    await client._run_once()
    assert client._conn is fake.conn
    assert client._connected.is_set()
    assert await client.wait_until_connected(timeout=0.1) is True
    assert fake.conn.sent[1:] == [
        WSSubscribeRequest(topic="t.a").model_dump_json(),
        WSSubscribeRequest(topic="t.b").model_dump_json(),
    ]


async def test_inbound_frame_handling(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    seen: list[str] = []

    async def good(env: WSEnvelope) -> None:
        seen.append(f"good:{env.event_type}")

    async def bad(env: WSEnvelope) -> None:
        seen.append("bad")
        raise RuntimeError("boom")

    frames = [
        "not json{",
        json.dumps({"op": "event", "topic": "t.good"}),
        _event("t.bad"),
        _event("t.good", "first"),
        _event("t.unknown"),
        WSError(code=7, reason="slow down").model_dump_json(),
        json.dumps({"op": "ack"}),
        _event("t.good", "last"),
    ]
    _install(monkeypatch, ACK, frames)
    client = _client()
    await client.subscribe("t.good", good)
    await client.subscribe("t.bad", bad)
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await client._run_once()

    assert seen == ["bad", "good:first", "good:last"]
    by_level = [(r.levelno, r.getMessage()) for r in caplog.records]
    assert (logging.WARNING, "ws non-json frame discarded") in by_level
    assert any(lv == logging.WARNING and m.startswith("ws envelope validation failed") for lv, m in by_level)
    assert (logging.WARNING, "ws error from backend: code=7 reason=slow down") in by_level
    assert any(lv == logging.ERROR and "ws handler raised on topic=t.bad: boom" in m for lv, m in by_level)


async def test_stopping_breaks_before_next_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    client = _client()

    async def stopper(env: WSEnvelope) -> None:
        seen.append(env.event_type)
        client._stopping.set()

    _install(monkeypatch, ACK, [_event("t.s", "one"), _event("t.s", "two")])
    await client.subscribe("t.s", stopper)
    await client._run_once()
    assert seen == ["one"]
