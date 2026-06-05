"""WSClient handshake, subscribe replay, publish."""

from __future__ import annotations

import asyncio
import json

import pytest
import websockets
from websockets.asyncio.server import ServerConnection

import arm_ripper.ws_client as ws_module
from arm_common.schemas import WSAck, WSEnvelope, WSError
from arm_ripper.ws_client import WSClient


@pytest.fixture
def fast_reconnect(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ws_module, "RECONNECT_DELAYS", (0.05, 0.05, 0.05))
    monkeypatch.setattr(ws_module, "AUTH_ACK_TIMEOUT_SECONDS", 1.0)


class StubBackend:
    """Minimal WS server emulating the backend's auth/sub/publish loop."""

    def __init__(self, *, accept: bool = True) -> None:
        self.accept = accept
        self.received_publishes: list[dict[str, object]] = []
        self.received_subscribes: list[str] = []
        self.received_auth_tokens: list[str] = []
        self.connections: list[ServerConnection] = []
        self._server: websockets.asyncio.server.Server | None = None
        self.port: int = 0

    async def __aenter__(self) -> StubBackend:
        self._server = await websockets.serve(self._handle, host="127.0.0.1", port=0)
        sock = next(iter(self._server.sockets))
        self.port = sock.getsockname()[1]
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, conn: ServerConnection) -> None:
        self.connections.append(conn)
        try:
            first = await conn.recv()
            msg = json.loads(first)
            if msg.get("op") != "auth":
                await conn.send(WSError(code=4400, reason="bad first message").model_dump_json())
                return
            self.received_auth_tokens.append(msg.get("token", ""))
            if not self.accept:
                await conn.send(WSError(code=4401, reason="rejected").model_dump_json())
                return
            await conn.send(WSAck().model_dump_json())

            async for raw in conn:
                m = json.loads(raw)
                op = m.get("op")
                if op == "subscribe":
                    self.received_subscribes.append(m["topic"])
                    await conn.send(WSAck(topic=m["topic"]).model_dump_json())
                elif op == "publish":
                    self.received_publishes.append(m)
        except websockets.ConnectionClosed:
            return

    async def emit(self, envelope: WSEnvelope) -> None:
        # Push to the most recently connected client.
        if not self.connections:
            return
        conn = self.connections[-1]
        try:
            await conn.send(envelope.model_dump_json())
        except websockets.ConnectionClosed:
            pass


async def test_auth_then_subscribe_then_publish(fast_reconnect: None) -> None:
    async with StubBackend() as backend:
        url = f"ws://127.0.0.1:{backend.port}/ws"
        async with WSClient(url, "tok-abc", "arm-ripper-A") as client:
            await client.wait_until_connected(timeout=2.0)

            received: list[WSEnvelope] = []

            async def handler(env: WSEnvelope) -> None:
                received.append(env)

            await client.subscribe("ripper.commands.drv_A", handler)
            await asyncio.sleep(0.1)
            assert backend.received_subscribes == ["ripper.commands.drv_A"]

            await client.publish(
                "ripper.progress.job_X",
                "ripper.progress",
                {"track_id": "trk_1", "progress_pct": 42.0},
            )
            await asyncio.sleep(0.1)
            assert len(backend.received_publishes) == 1
            assert backend.received_publishes[0]["topic"] == "ripper.progress.job_X"

            from datetime import datetime, timezone

            envelope = WSEnvelope(
                event_id="evt_1",
                event_type="identify.resolved",
                emitted_at=datetime.now(timezone.utc),
                topic="ripper.commands.drv_A",
                job_id="job_X",
                payload={"job_id": "job_X"},
            )
            await backend.emit(envelope)
            await asyncio.sleep(0.1)
            assert len(received) == 1
            assert received[0].event_type == "identify.resolved"

        assert backend.received_auth_tokens == ["tok-abc"]


async def test_subscriptions_replayed_on_reconnect(fast_reconnect: None) -> None:
    async with StubBackend() as backend:
        url = f"ws://127.0.0.1:{backend.port}/ws"
        async with WSClient(url, "tok-abc", "arm-ripper-A") as client:
            await client.wait_until_connected(timeout=2.0)

            async def handler(env: WSEnvelope) -> None:
                pass

            await client.subscribe("ripper.commands.drv_A", handler)
            await asyncio.sleep(0.1)
            assert backend.received_subscribes == ["ripper.commands.drv_A"]

            # Force-disconnect the server side; client should reconnect and replay.
            for conn in list(backend.connections):
                await conn.close()
            await asyncio.sleep(0.5)

            assert backend.received_subscribes == [
                "ripper.commands.drv_A",
                "ripper.commands.drv_A",
            ]


async def test_publish_when_disconnected_silently_drops(fast_reconnect: None) -> None:
    """Smoke-tests the fire-and-forget guarantee for ripper.progress.*."""
    client = WSClient("ws://127.0.0.1:1/ws", "tok", "arm-ripper-A")
    # Not entered; no connection. Should not raise.
    await client.publish("ripper.progress.job_x", "ripper.progress", {"pct": 1})
