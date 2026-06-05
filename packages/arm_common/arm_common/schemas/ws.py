"""WebSocket message schemas.

Inbound (client → server) messages share an `op` discriminator so the
backend can `model_validate` a parsed JSON frame in one call. Outbound
fan-out frames use `WSEnvelope`. Errors use `WSError` (also flows
client-bound only).

The `publish` op extends what 03-protocol.md documents — see the
implementation note in that doc. The wire-side guarantee is that
clients never set `event_id` themselves; the server builds the
envelope on every emit.
"""

from datetime import datetime
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


class WSAuthRequest(BaseModel):
    op: Literal["auth"] = "auth"
    token: str


class WSSubscribeRequest(BaseModel):
    op: Literal["subscribe"] = "subscribe"
    topic: str


class WSUnsubscribeRequest(BaseModel):
    op: Literal["unsubscribe"] = "unsubscribe"
    topic: str


class WSPublishRequest(BaseModel):
    op: Literal["publish"] = "publish"
    topic: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


WSInboundMessage = Annotated[
    Union[WSAuthRequest, WSSubscribeRequest, WSUnsubscribeRequest, WSPublishRequest],
    Field(discriminator="op"),
]


class WSAck(BaseModel):
    op: Literal["ack"] = "ack"
    topic: str = ""


class WSError(BaseModel):
    op: Literal["error"] = "error"
    code: int
    reason: str


class WSEnvelope(BaseModel):
    """Outbound fan-out frame.

    Mirrors the 03-protocol.md event envelope plus a `topic` so a single
    multiplexed connection can demux events client-side.
    """

    op: Literal["event"] = "event"
    event_id: str
    event_type: str
    emitted_at: datetime
    topic: str
    job_id: str | None = None
    track_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
