"""Full /ws handshake + serve-loop coverage via TestClient.websocket_connect.

The ws unit helpers (origin predicate, authz, principal resolver, hub) are
covered by test_ws_*.py; this drives the endpoint itself: origin gate, the
auth handshake (success + every failure), and the dispatch loop
(subscribe/unsubscribe/publish, re-auth, bad shape) for ripper, transcoder,
and UI principals.
"""

from __future__ import annotations

import os
import secrets
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from starlette.websockets import WebSocketDisconnect  # noqa: E402

import pytest  # noqa: E402

from arm_backend.config import settings  # noqa: E402
from arm_backend.jwt_utils import issue_access_token  # noqa: E402
from arm_backend.ws import router as ws_router  # noqa: E402
from arm_common import (  # noqa: E402
    Drive,
    DriveStatus,
    Job,
    JobStatus,
    TranscodeTaskStatus,
    User,
)
from arm_common.models import TranscodeTask  # noqa: E402

from tests._fakes import FakeSession  # noqa: E402

_SIGNING_KEY = secrets.token_bytes(32)


class _Hub:
    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.emitted: list[dict[str, Any]] = []
        self.disconnected = 0

    async def subscribe(self, _ws: Any, topic: str) -> None:
        self.subscribed.append(topic)

    async def unsubscribe(self, _ws: Any, topic: str) -> None:
        self.unsubscribed.append(topic)

    async def emit(
        self,
        topic: str,
        event_type: str,
        payload: Any,
        *,
        persist: bool = True,
        job_id: str | None = None,
        track_id: str | None = None,
        session: Any = None,
    ) -> None:
        self.emitted.append(
            {
                "topic": topic,
                "event_type": event_type,
                "persist": persist,
                "job_id": job_id,
                "track_id": track_id,
                "has_session": session is not None,
            }
        )

    async def disconnect(self, _ws: Any) -> None:
        self.disconnected += 1


class _SessionCtx:
    def __init__(self, db: FakeSession) -> None:
        self._db = db

    async def __aenter__(self) -> FakeSession:
        return self._db

    async def __aexit__(self, *_exc: Any) -> bool:
        return False


@pytest.fixture(autouse=True)
def _restore_origins() -> Any:
    saved = settings.ARM_ALLOWED_ORIGINS
    yield
    settings.ARM_ALLOWED_ORIGINS = saved


def _make_app(db: FakeSession, hub: _Hub, monkeypatch: pytest.MonkeyPatch) -> FastAPI:
    app = FastAPI()
    app.state.ws_hub = hub
    app.state.signing_key = _SIGNING_KEY
    app.include_router(ws_router.router)
    monkeypatch.setattr(ws_router, "SessionLocal", lambda: _SessionCtx(db))
    return app


def _ripper_drive(drive_id: str = "drv_x", hostname: str = "ripper-host") -> Drive:
    return Drive(id=drive_id, hostname=hostname, device_path="/dev/sr0", status=DriveStatus.ONLINE)


def _job(job_id: str = "job_x", drive_id: str = "drv_x") -> Job:
    return Job(
        id=job_id,
        drive_id=drive_id,
        disc_type=__import__("arm_common", fromlist=["DiscType"]).DiscType.DVD,
        title="X",
        year=2000,
        status=JobStatus.RIPPING,
        metadata_json={},
        resumed_from_crash=False,
    )


# --- origin gate -------------------------------------------------------------


def test_origin_not_allowed_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    settings.ARM_ALLOWED_ORIGINS = []
    app = _make_app(FakeSession(), _Hub(), monkeypatch)
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws", headers={"origin": "https://evil.example"}) as ws:
                ws.receive_json()


# --- auth handshake failures -------------------------------------------------


def test_auth_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ws_router, "AUTH_TIMEOUT_SECONDS", 0.05)
    app = _make_app(FakeSession(), _Hub(), monkeypatch)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            err = ws.receive_json()
            assert err["op"] == "error"
            assert err["code"] == ws_router.CLOSE_UNAUTHORIZED
            assert "timeout" in err["reason"]


def test_auth_non_json_first_message(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _make_app(FakeSession(), _Hub(), monkeypatch)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_text("not json at all")
            err = ws.receive_json()
            assert err["code"] == ws_router.CLOSE_BAD_MESSAGE


def test_auth_invalid_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _make_app(FakeSession(), _Hub(), monkeypatch)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"op": "totally-bogus"})
            err = ws.receive_json()
            assert err["code"] == ws_router.CLOSE_BAD_MESSAGE
            assert "invalid message shape" in err["reason"]


def test_auth_first_message_not_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _make_app(FakeSession(), _Hub(), monkeypatch)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"op": "subscribe", "topic": "ripper.events"})
            err = ws.receive_json()
            assert err["code"] == ws_router.CLOSE_UNAUTHORIZED
            assert "must be auth" in err["reason"]


def test_auth_bad_token_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _make_app(FakeSession(), _Hub(), monkeypatch)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"op": "auth", "token": "garbage"})
            err = ws.receive_json()
            assert err["code"] == ws_router.CLOSE_UNAUTHORIZED


# --- ripper principal: full loop ---------------------------------------------


def test_ripper_subscribe_publish_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeSession()
    db.rows["drives"] = [_ripper_drive()]
    db.rows["jobs"] = [_job()]
    hub = _Hub()
    app = _make_app(db, hub, monkeypatch)
    with TestClient(app) as client:
        with client.websocket_connect(
            "/ws",
            subprotocols=[ws_router.SERVICE_TOKEN_SUBPROTOCOL],
            headers={"x-arm-hostname": "ripper-host"},
        ) as ws:
            ws.send_json({"op": "auth", "token": "tok-service"})
            assert ws.receive_json()["op"] == "ack"

            # subscribe allowed (drive owned by this hostname)
            ws.send_json({"op": "subscribe", "topic": "ripper.commands.drv_x"})
            assert ws.receive_json() == {"op": "ack", "topic": "ripper.commands.drv_x"}

            # subscribe forbidden (unknown drive scope)
            ws.send_json({"op": "subscribe", "topic": "ripper.commands.drv_other"})
            assert ws.receive_json()["code"] == ws_router.CLOSE_FORBIDDEN

            # unsubscribe always acks
            ws.send_json({"op": "unsubscribe", "topic": "ripper.commands.drv_x"})
            assert ws.receive_json() == {"op": "ack", "topic": "ripper.commands.drv_x"}

            # publish allowed → progress topic (fire-and-forget, not persisted)
            ws.send_json(
                {"op": "publish", "topic": "ripper.progress.job_x", "event_type": "rip.progress", "payload": {"pct": 5}}
            )
            # publish forbidden topic
            ws.send_json({"op": "publish", "topic": "ripper.progress.job_other", "event_type": "x", "payload": {}})
            err = ws.receive_json()
            assert err["code"] == ws_router.CLOSE_FORBIDDEN

            # re-auth rejected
            ws.send_json({"op": "auth", "token": "tok-service"})
            assert "already authenticated" in ws.receive_json()["reason"]

            # malformed message in loop
            ws.send_json({"op": "nope"})
            assert ws.receive_json()["code"] == ws_router.CLOSE_BAD_MESSAGE

    emitted = [e for e in hub.emitted if e["topic"] == "ripper.progress.job_x"]
    assert len(emitted) == 1
    assert emitted[0]["persist"] is False
    assert emitted[0]["job_id"] == "job_x"
    assert emitted[0]["has_session"] is False
    assert hub.disconnected == 1


# --- transcoder principal: progress publish w/ track_id from payload ---------


def test_transcoder_publish_uses_payload_track_id(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeSession()
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_1",
            session_application_id="sap_1",
            source_track_id="trk_1",
            status=TranscodeTaskStatus.IN_PROGRESS,
            claimed_by="tc-host",
            progress_pct=0,
            attempts=0,
        )
    ]
    hub = _Hub()
    app = _make_app(db, hub, monkeypatch)
    with TestClient(app) as client:
        with client.websocket_connect(
            "/ws",
            subprotocols=[ws_router.SERVICE_TOKEN_SUBPROTOCOL],
            headers={"x-arm-hostname": "tc-host", "x-arm-task-id": "txt_1"},
        ) as ws:
            ws.send_json({"op": "auth", "token": "tok-service"})
            assert ws.receive_json()["op"] == "ack"
            ws.send_json(
                {
                    "op": "publish",
                    "topic": "transcode.progress.txt_1",
                    "event_type": "transcode.progress",
                    "payload": {"track_id": "trk_explicit", "pct": 40},
                }
            )
            ws.send_json({"op": "unsubscribe", "topic": "transcode.progress.txt_1"})
            ws.receive_json()  # unsubscribe ack — proves the publish was processed
    prog = [e for e in hub.emitted if e["topic"] == "transcode.progress.txt_1"]
    assert prog and prog[0]["track_id"] == "trk_explicit"


def test_transcoder_publish_falls_back_to_topic_task_id(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeSession()
    db.rows["transcode_tasks"] = [
        TranscodeTask(
            id="txt_2",
            session_application_id="sap_2",
            source_track_id="trk_2",
            status=TranscodeTaskStatus.IN_PROGRESS,
            claimed_by="tc-host",
            progress_pct=0,
            attempts=0,
        )
    ]
    hub = _Hub()
    app = _make_app(db, hub, monkeypatch)
    with TestClient(app) as client:
        with client.websocket_connect(
            "/ws",
            subprotocols=[ws_router.SERVICE_TOKEN_SUBPROTOCOL],
            headers={"x-arm-hostname": "tc-host", "x-arm-task-id": "txt_2"},
        ) as ws:
            ws.send_json({"op": "auth", "token": "tok-service"})
            assert ws.receive_json()["op"] == "ack"
            ws.send_json(
                {
                    "op": "publish",
                    "topic": "transcode.progress.txt_2",
                    "event_type": "transcode.progress",
                    "payload": {"pct": 70},
                }
            )
            ws.send_json({"op": "unsubscribe", "topic": "x.y"})
            ws.receive_json()
    prog = [e for e in hub.emitted if e["topic"] == "transcode.progress.txt_2"]
    assert prog and prog[0]["track_id"] == "txt_2"


# --- UI principal (JWT) ------------------------------------------------------


def test_ui_jwt_principal_subscribe(monkeypatch: pytest.MonkeyPatch) -> None:
    db = FakeSession()
    db.rows["users"] = [User(id="usr_1", username="admin", password_hash="x", password_must_change=False)]
    hub = _Hub()
    app = _make_app(db, hub, monkeypatch)
    token, _ = issue_access_token("usr_1", "admin", _SIGNING_KEY)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"op": "auth", "token": token})
            assert ws.receive_json()["op"] == "ack"
            ws.send_json({"op": "subscribe", "topic": "ripper.events"})
            assert ws.receive_json() == {"op": "ack", "topic": "ripper.events"}
    assert "ripper.events" in hub.subscribed
