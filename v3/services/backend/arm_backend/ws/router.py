"""FastAPI WS route — /ws.

Wire shape:
    1. Origin allowlist (skipped for service-token subprotocol or origin-less connects).
    2. Accept upgrade.
    3. 5s window for the first message; must be {op:auth, token:...}.
    4. resolve_principal(); reject (4401) on failure.
    5. Send {op:ack, topic:""} as the auth ack.
    6. Loop: subscribe / unsubscribe / publish, gated by authz.
    7. On disconnect: hub.disconnect(ws).
"""

import asyncio
import logging

from fastapi import APIRouter, Header, WebSocket, WebSocketDisconnect, status
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from arm_backend.config import settings
from arm_backend.db import SessionLocal
from arm_backend.ws.authz import can_publish, can_subscribe
from arm_backend.ws.hub import WSHub
from arm_backend.ws.principal import (
    AuthError,
    Principal,
    ServicePrincipal,
    resolve_principal,
)
from arm_common.schemas import (
    WSAck,
    WSAuthRequest,
    WSError,
    WSInboundMessage,
    WSPublishRequest,
    WSSubscribeRequest,
    WSUnsubscribeRequest,
)

logger = logging.getLogger("arm_backend.ws.router")

router = APIRouter()

_inbound_adapter: TypeAdapter[WSInboundMessage] = TypeAdapter(WSInboundMessage)

AUTH_TIMEOUT_SECONDS = 5.0
SERVICE_TOKEN_SUBPROTOCOL = "arm-service-token"

# WS application-level close codes (4xxx range is reserved for app use per RFC 6455).
CLOSE_BAD_MESSAGE = 4400
CLOSE_UNAUTHORIZED = 4401
CLOSE_FORBIDDEN = 4403


def _origin_allowed(origin: str | None, subprotocols: list[str]) -> bool:
    if SERVICE_TOKEN_SUBPROTOCOL in subprotocols:
        return True
    if not origin:
        return True
    if not settings.ARM_ALLOWED_ORIGINS:
        return False
    return origin in settings.ARM_ALLOWED_ORIGINS


@router.websocket("/ws")
async def ws_endpoint(
    websocket: WebSocket,
    origin: str | None = Header(default=None),
    sec_websocket_protocol: str | None = Header(default=None),
    x_arm_hostname: str | None = Header(default=None),
) -> None:
    subprotocols = [p.strip() for p in (sec_websocket_protocol or "").split(",") if p.strip()]

    if not _origin_allowed(origin, subprotocols):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="origin not allowed")
        return

    accept_subprotocol = SERVICE_TOKEN_SUBPROTOCOL if SERVICE_TOKEN_SUBPROTOCOL in subprotocols else None
    await websocket.accept(subprotocol=accept_subprotocol)

    hub: WSHub = websocket.app.state.ws_hub

    try:
        principal = await _do_auth(websocket, x_arm_hostname)
    except _AuthFailure as e:
        await _send_error(websocket, e.code, e.reason)
        await websocket.close(code=e.code, reason=e.reason)
        return

    await websocket.send_json(WSAck().model_dump())
    logger.info("ws auth ok principal=%s", principal)

    try:
        await _serve_loop(websocket, hub, principal)
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(websocket)


class _AuthFailure(Exception):
    def __init__(self, code: int, reason: str) -> None:
        self.code = code
        self.reason = reason


async def _do_auth(websocket: WebSocket, x_arm_hostname: str | None) -> Principal:
    try:
        raw = await asyncio.wait_for(websocket.receive_json(), timeout=AUTH_TIMEOUT_SECONDS)
    except asyncio.TimeoutError as e:
        raise _AuthFailure(CLOSE_UNAUTHORIZED, "auth timeout") from e
    except Exception as e:
        raise _AuthFailure(CLOSE_BAD_MESSAGE, "auth message must be JSON") from e

    try:
        msg = _inbound_adapter.validate_python(raw)
    except ValidationError as e:
        raise _AuthFailure(CLOSE_BAD_MESSAGE, "invalid message shape") from e

    if not isinstance(msg, WSAuthRequest):
        raise _AuthFailure(CLOSE_UNAUTHORIZED, "first message must be auth")

    try:
        return resolve_principal(msg.token, x_arm_hostname)
    except AuthError as e:
        raise _AuthFailure(CLOSE_UNAUTHORIZED, str(e)) from e


async def _serve_loop(websocket: WebSocket, hub: WSHub, principal: Principal) -> None:
    while True:
        raw = await websocket.receive_json()
        try:
            msg = _inbound_adapter.validate_python(raw)
        except ValidationError:
            await _send_error(websocket, CLOSE_BAD_MESSAGE, "invalid message shape")
            continue

        async with SessionLocal() as session:
            await _dispatch(websocket, hub, principal, msg, session)


async def _dispatch(
    websocket: WebSocket,
    hub: WSHub,
    principal: Principal,
    msg: WSInboundMessage,
    session: AsyncSession,
) -> None:
    if isinstance(msg, WSAuthRequest):
        # Re-auth not supported; ignore loud.
        await _send_error(websocket, CLOSE_BAD_MESSAGE, "already authenticated")
        return

    if isinstance(msg, WSSubscribeRequest):
        if not await can_subscribe(principal, msg.topic, session):
            await _send_error(websocket, CLOSE_FORBIDDEN, f"cannot subscribe to {msg.topic}")
            return
        await hub.subscribe(websocket, msg.topic)
        await websocket.send_json(WSAck(topic=msg.topic).model_dump())
        return

    if isinstance(msg, WSUnsubscribeRequest):
        await hub.unsubscribe(websocket, msg.topic)
        await websocket.send_json(WSAck(topic=msg.topic).model_dump())
        return

    if isinstance(msg, WSPublishRequest):
        if not await can_publish(principal, msg.topic, session):
            await _send_error(websocket, CLOSE_FORBIDDEN, f"cannot publish to {msg.topic}")
            return
        # Service-published progress is fire-and-forget — never persisted, never blocks the publisher.
        is_progress = msg.topic.startswith("ripper.progress.") or msg.topic.startswith("transcode.progress.")
        job_id = _extract_id(msg.topic, "ripper.progress.")
        await hub.emit(
            topic=msg.topic,
            event_type=msg.event_type,
            payload=msg.payload,
            persist=not is_progress,
            job_id=job_id,
            track_id=msg.payload.get("track_id") if isinstance(msg.payload, dict) else None,
            session=session if not is_progress else None,
        )
        if not is_progress:
            await session.commit()
        return


def _extract_id(topic: str, prefix: str) -> str | None:
    if topic.startswith(prefix):
        return topic[len(prefix) :] or None
    return None


async def _send_error(websocket: WebSocket, code: int, reason: str) -> None:
    err = WSError(code=code, reason=reason)
    try:
        await websocket.send_json(err.model_dump())
    except Exception:
        pass


# The principal type is referenced for static checkers; ServicePrincipal stays a runtime helper.
_ = ServicePrincipal
