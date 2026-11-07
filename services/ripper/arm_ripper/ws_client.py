"""Long-lived WS connection from ripper to backend.

Reconnects with exponential backoff (1, 2, 4, 8, 30s cap, infinite
retries). On every (re)connect: re-runs the auth handshake and replays
all recorded subscriptions. Inbound messages are demuxed by topic to
per-subscription async handlers.

`publish` is best-effort: drops silently when disconnected, since
`ripper.progress.*` is fire-and-forget telemetry per
03-protocol.md § Why WS for progress.
"""

from __future__ import annotations

import asyncio
import json
import logging
import ssl
from collections.abc import Awaitable, Callable
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from arm_common.schemas import (
    WSAck,
    WSAuthRequest,
    WSEnvelope,
    WSError,
    WSPublishRequest,
    WSSubscribeRequest,
)

logger = logging.getLogger("arm_ripper.ws_client")

RECONNECT_DELAYS = (1.0, 2.0, 4.0, 8.0, 30.0)
AUTH_ACK_TIMEOUT_SECONDS = 5.0
SERVICE_TOKEN_SUBPROTOCOL = "arm-service-token"

EnvelopeHandler = Callable[[WSEnvelope], Awaitable[None]]


class WSClient:
    def __init__(
        self,
        url: str,
        service_token: str,
        hostname: str,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        self._url = url
        self._token = service_token
        self._hostname = hostname
        self._ssl = ssl_context
        self._handlers: dict[str, EnvelopeHandler] = {}
        self._conn: ClientConnection | None = None
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        self._connected = asyncio.Event()

    async def __aenter__(self) -> WSClient:
        self._task = asyncio.create_task(self._connect_loop(), name="ws-client-loop")
        return self

    async def __aexit__(self, *exc: object) -> None:
        self._stopping.set()
        if self._conn is not None:
            try:
                await self._conn.close()
            except Exception:  # noqa: BLE001
                pass
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()

    async def subscribe(self, topic: str, handler: EnvelopeHandler) -> None:
        """Record a subscription and (if connected) send the subscribe op now.

        Replayed automatically on every reconnect.
        """
        self._handlers[topic] = handler
        if self._conn is not None:
            try:
                await self._conn.send(WSSubscribeRequest(topic=topic).model_dump_json())
            except Exception as exc:  # noqa: BLE001
                logger.warning("ws subscribe send failed (%s); will retry on reconnect", exc)

    async def publish(self, topic: str, event_type: str, payload: dict[str, Any]) -> None:
        """Best-effort publish; drops silently if not connected."""
        conn = self._conn
        if conn is None:
            return
        msg = WSPublishRequest(topic=topic, event_type=event_type, payload=payload)
        try:
            await conn.send(msg.model_dump_json())
        except Exception as exc:  # noqa: BLE001
            logger.debug("ws publish dropped (%s)", exc)

    async def wait_until_connected(self, timeout: float | None = None) -> bool:
        try:
            await asyncio.wait_for(self._connected.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def _connect_loop(self) -> None:
        delay_idx = 0
        while not self._stopping.is_set():
            try:
                await self._run_once()
                delay_idx = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("ws connection error: %s", exc)
            finally:
                self._conn = None
                self._connected.clear()

            if self._stopping.is_set():
                return
            delay = RECONNECT_DELAYS[min(delay_idx, len(RECONNECT_DELAYS) - 1)]
            delay_idx += 1
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=delay)
                return  # stopping signalled
            except asyncio.TimeoutError:
                pass

    async def _run_once(self) -> None:
        async with websockets.connect(
            self._url,
            ssl=self._ssl,
            subprotocols=[SERVICE_TOKEN_SUBPROTOCOL],  # type: ignore[list-item]
            additional_headers=[("X-ARM-Hostname", self._hostname)],
            ping_interval=20.0,
            ping_timeout=20.0,
            max_size=2**20,
        ) as conn:
            await self._authenticate(conn)
            logger.info("ws connected url=%s", self._url)

            self._conn = conn
            self._connected.set()

            for topic in self._handlers:
                await conn.send(WSSubscribeRequest(topic=topic).model_dump_json())

            async for raw in conn:
                if self._stopping.is_set():
                    break
                await self._handle_frame(raw)

    async def _authenticate(self, conn: ClientConnection) -> None:
        """Send the service token and await the ack; raise WSAuthFailed on a rejection or other first frame."""
        await conn.send(WSAuthRequest(token=self._token).model_dump_json())
        ack_raw = await asyncio.wait_for(conn.recv(), timeout=AUTH_ACK_TIMEOUT_SECONDS)
        ack = json.loads(ack_raw)
        if ack.get("op") == "error":
            err = WSError.model_validate(ack)
            raise WSAuthFailed(f"backend rejected auth: code={err.code} reason={err.reason}")
        if ack.get("op") != "ack":
            raise WSAuthFailed(f"unexpected first frame: {ack!r}")
        WSAck.model_validate(ack)

    async def _handle_frame(self, raw: str | bytes) -> None:
        """Decode one inbound frame: dispatch an event to its topic handler, log a backend error, ignore the rest."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("ws non-json frame discarded")
            return

        op = msg.get("op")
        if op == "event":
            await self._dispatch_event(msg)
        elif op == "error":
            err = WSError.model_validate(msg)
            logger.warning("ws error from backend: code=%s reason=%s", err.code, err.reason)
        # ack frames are subscribe acks; harmless to ignore here.

    async def _dispatch_event(self, msg: Any) -> None:
        """Validate an event frame and run its topic handler.

        Bad envelopes and raising handlers are logged, not raised.
        """
        try:
            env = WSEnvelope.model_validate(msg)
        except Exception as exc:  # noqa: BLE001
            logger.warning("ws envelope validation failed: %s", exc)
            return
        handler = self._handlers.get(env.topic)
        if handler is not None:
            try:
                await handler(env)
            except Exception as exc:  # noqa: BLE001
                logger.exception("ws handler raised on topic=%s: %s", env.topic, exc)


class WSAuthFailed(Exception):
    pass
