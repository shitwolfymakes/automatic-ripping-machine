"""Characterization tests for `WSClient._run_once` / `_connect_loop` against a faked websocket connection."""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
from collections.abc import AsyncIterator, Awaitable
from datetime import UTC, datetime
from typing import Any

import pytest

from arm_common.schemas import WSAck, WSAuthRequest, WSEnvelope, WSError, WSSubscribeRequest
from arm_ripper import ws_client as ws_module
from arm_ripper.ws_client import RECONNECT_DELAYS, SERVICE_TOKEN_SUBPROTOCOL, WSAuthFailed, WSClient

URL = "wss://backend.test/ws"
TOKEN = "tok-123"
LOGGER = "arm_ripper.ws_client"
ACK = WSAck().model_dump_json()


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
    return WSClient(url=URL, service_token=TOKEN, hostname="host-a", ssl_context=ctx)


def _install(monkeypatch: pytest.MonkeyPatch, ack: str, frames: list[str] | None = None) -> FakeConnect:
    fake = FakeConnect(FakeConn(ack, frames or []))
    monkeypatch.setattr(ws_module.websockets, "connect", fake)
    return fake


async def test_connect_kwargs_and_auth_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = ssl.create_default_context()
    fake = _install(monkeypatch, ACK)
    await _client(ctx)._run_once()
    assert fake.args == (URL,)
    assert fake.kwargs == {
        "ssl": ctx,
        "subprotocols": [SERVICE_TOKEN_SUBPROTOCOL],
        "additional_headers": [("X-ARM-Hostname", "host-a")],
        "ping_interval": 20.0,
        "ping_timeout": 20.0,
        "max_size": 2**20,
    }
    assert SERVICE_TOKEN_SUBPROTOCOL == "arm-service-token"
    assert fake.conn.sent[0] == WSAuthRequest(token=TOKEN).model_dump_json()


async def test_error_ack_raises_with_code_and_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, WSError(code=4401, reason="bad token").model_dump_json())
    with pytest.raises(WSAuthFailed) as info:
        await _client()._run_once()
    assert str(info.value) == "backend rejected auth: code=4401 reason=bad token"


async def test_unexpected_first_frame_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, json.dumps({"op": "event"}))
    with pytest.raises(WSAuthFailed) as info:
        await _client()._run_once()
    assert str(info.value) == "unexpected first frame: {'op': 'event'}"


async def test_valid_ack_sets_connected_logs_and_subscribes(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    fake = _install(monkeypatch, ACK)
    client = _client()

    async def h(env: WSEnvelope) -> None:  # pragma: no cover - never dispatched
        pass

    await client.subscribe("t.b", h)
    await client.subscribe("t.a", h)
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await client._run_once()
    assert client._conn is fake.conn
    assert client._connected.is_set()
    assert (logging.INFO, f"ws connected url={URL}") in [(r.levelno, r.getMessage()) for r in caplog.records]
    assert fake.conn.sent[1:] == [
        WSSubscribeRequest(topic="t.b").model_dump_json(),
        WSSubscribeRequest(topic="t.a").model_dump_json(),
    ]


async def test_inbound_frame_handling(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    seen: list[WSEnvelope | str] = []

    async def good(env: WSEnvelope) -> None:
        seen.append(env)

    async def bad(env: WSEnvelope) -> None:
        seen.append("bad")
        raise RuntimeError("boom")

    first = _event("t.good", "first")
    frames = [
        "not json{",
        json.dumps({"op": "event", "topic": "t.good"}),
        _event("t.bad"),
        first,
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

    assert seen[0] == "bad"
    assert seen[1] == WSEnvelope.model_validate_json(first)
    assert [e.event_type for e in seen[1:] if isinstance(e, WSEnvelope)] == ["first", "last"]
    assert len(seen) == 3
    by_level = [(r.levelno, r.getMessage()) for r in caplog.records if r.name == LOGGER]
    assert (logging.WARNING, "ws non-json frame discarded") in by_level
    assert sum(1 for lv, m in by_level if lv == logging.WARNING and m.startswith("ws envelope validation failed:")) == 1
    assert (logging.WARNING, "ws error from backend: code=7 reason=slow down") in by_level
    assert (logging.ERROR, "ws handler raised on topic=t.bad: boom") in by_level
    # ack frames are ignored silently; the INFO line is the only other record.
    assert len(by_level) == 5


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


class LoopHarness:
    """Scripted `_run_once` outcomes plus a fake `asyncio.wait_for` that records delays and never sleeps."""

    def __init__(self, client: WSClient, outcomes: list[BaseException | None]) -> None:
        self.client = client
        self.outcomes = outcomes
        self.calls = 0
        self.delays: list[float | None] = []
        self.signalled = False

    async def run_once(self) -> None:
        outcome = self.outcomes[self.calls] if self.calls < len(self.outcomes) else None
        self.calls += 1
        self.client._conn = object()  # type: ignore[assignment]
        self.client._connected.set()
        if self.calls >= len(self.outcomes):
            self.client._stopping.set()
        if outcome is not None:
            raise outcome

    async def wait_for(self, aw: Awaitable[Any], timeout: float | None = None) -> None:
        self.delays.append(timeout)
        aw.close()  # type: ignore[attr-defined]
        if self.signalled:
            return
        raise TimeoutError


def _harness(
    monkeypatch: pytest.MonkeyPatch, outcomes: list[BaseException | None], *, signalled: bool = False
) -> LoopHarness:
    client = _client()
    h = LoopHarness(client, outcomes)
    h.signalled = signalled
    monkeypatch.setattr(client, "_run_once", h.run_once)
    monkeypatch.setattr(ws_module.asyncio, "wait_for", h.wait_for)
    return h


async def test_connect_loop_logs_error_clears_state_and_follows_schedule(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Seven failures; the last one sets _stopping, so no seventh wait is requested.
    h = _harness(monkeypatch, [RuntimeError("down")] * 7)
    with caplog.at_level(logging.DEBUG, logger=LOGGER):
        await h.client._connect_loop()
    assert RECONNECT_DELAYS == (1.0, 2.0, 4.0, 8.0, 30.0)
    assert h.delays == [1.0, 2.0, 4.0, 8.0, 30.0, 30.0]
    assert h.calls == 7
    assert (logging.WARNING, "ws connection error: down") in [(r.levelno, r.getMessage()) for r in caplog.records]
    assert h.client._conn is None
    assert not h.client._connected.is_set()


async def test_connect_loop_propagates_cancellation(monkeypatch: pytest.MonkeyPatch) -> None:
    h = _harness(monkeypatch, [asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError):
        await h.client._connect_loop()
    assert h.delays == []
    assert h.client._conn is None
    assert not h.client._connected.is_set()


async def test_connect_loop_clean_return_resets_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    h = _harness(monkeypatch, [RuntimeError("a"), RuntimeError("b"), None, RuntimeError("c"), RuntimeError("d")])
    await h.client._connect_loop()
    assert h.delays == [1.0, 2.0, 1.0, 2.0]


async def test_connect_loop_returns_when_stopped_during_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    h = _harness(monkeypatch, [RuntimeError("a"), RuntimeError("b"), RuntimeError("c")], signalled=True)
    await h.client._connect_loop()
    assert h.calls == 1
    assert h.delays == [1.0]


async def test_connect_loop_returns_without_waiting_when_stopped_after_run(monkeypatch: pytest.MonkeyPatch) -> None:
    h = _harness(monkeypatch, [None])
    await h.client._connect_loop()
    assert h.calls == 1
    assert h.delays == []


async def test_connect_loop_does_not_run_when_already_stopping(monkeypatch: pytest.MonkeyPatch) -> None:
    h = _harness(monkeypatch, [None])
    h.client._stopping.set()
    await h.client._connect_loop()
    assert h.calls == 0
    assert h.delays == []
