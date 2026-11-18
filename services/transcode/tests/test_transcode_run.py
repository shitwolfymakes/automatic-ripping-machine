"""Characterisation tests for `arm_transcode.main.run` and its `_on_cancel` closure."""

from __future__ import annotations

import asyncio
import ssl
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

import arm_transcode.main as m
from arm_common import ContainerFormat, MediaType, TranscodeTool
from arm_common.schemas import HardwareCaps, TranscodePresetView, WSEnvelope
from arm_transcode.heartbeat import ProgressState


def _handbrake_preset(*, preset_ref: str | None, extra_args: str | None = None) -> TranscodePresetView:
    return TranscodePresetView(
        id="p1",
        name="AMD HEVC",
        media_type=MediaType.MOVIE,
        is_builtin=True,
        tool=TranscodeTool.HANDBRAKE,
        preset_ref=preset_ref,
        handbrake_settings=None,
        container=ContainerFormat.MKV,
        encoder="vaapi_h265",
        extra_args=extra_args,
        created_by_user_id=None,
        created_at=None,
        updated_at=None,
    )


class Harness:
    """Records every boundary call made by `run`."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []
        self.api_kwargs: dict[str, Any] = {}
        self.ws_kwargs: dict[str, Any] = {}
        self.pump_kwargs: dict[str, Any] = {}
        self.log_ctx_kwargs: dict[str, Any] = {}
        self.encoder_kwargs: dict[str, Any] = {}
        self.subscriptions: list[tuple[str, Callable[[WSEnvelope], Awaitable[None]]]] = []
        self.inside = False
        self.claim_inside: bool | None = None
        self.encoder_inside: bool | None = None
        self.register_kwargs: dict[str, Any] = {}
        self.fail_kwargs: list[tuple[Any, ...]] = []
        self.complete_kwargs: dict[str, Any] = {}
        self.size = 4242
        self.encoder_exc: BaseException | None = None
        self.register_exc: BaseException | None = None
        self.response = SimpleNamespace(
            task=SimpleNamespace(
                output_path="Movies/Film/film.mkv", source_track_id="trk1", session_application_id="sa1"
            ),
            source_track=SimpleNamespace(job_id="job1", duration_seconds=123),
            transcode_preset=_handbrake_preset(preset_ref="x"),
            raw_input_path="/raw/in.mkv",
            media_root="/media",
        )

    def names(self) -> list[str]:
        return [n for n, _ in self.calls]


@pytest.fixture
def h(monkeypatch: pytest.MonkeyPatch) -> Harness:
    hs = Harness()
    monkeypatch.setenv("ARM_TRANSCODE_TASK_ID", "t1")
    monkeypatch.setenv("ARM_BACKEND_URL", "https://backend:8443")
    monkeypatch.setenv("ARM_SERVICE_TOKEN", "tok")
    monkeypatch.setenv("HOSTNAME", "host1")

    monkeypatch.setattr(m, "configure_service_logging", lambda *a, **k: None)

    class FakeApi:
        def __init__(self, **kwargs: Any) -> None:
            hs.api_kwargs = kwargs

        async def register(self, **kwargs: Any) -> Any:
            hs.calls.append(("register", kwargs))
            hs.register_kwargs = kwargs
            if hs.register_exc is not None:
                raise hs.register_exc
            return hs.response

        async def claim(self, *args: Any) -> None:
            hs.claim_inside = hs.inside
            hs.calls.append(("claim", args))

        async def fail(self, *args: Any, **kwargs: Any) -> None:
            hs.calls.append(("fail", (args, kwargs)))
            hs.fail_kwargs.append((args, kwargs))

        async def complete(self, *args: Any, **kwargs: Any) -> None:
            hs.calls.append(("complete", (args, kwargs)))
            hs.complete_kwargs = {"args": args, **kwargs}

        async def close(self) -> None:
            hs.calls.append(("close", None))

    class FakeWS:
        def __init__(self, **kwargs: Any) -> None:
            hs.ws_kwargs = kwargs

        async def __aenter__(self) -> FakeWS:
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

        async def subscribe(self, topic: str, handler: Callable[[WSEnvelope], Awaitable[None]]) -> None:
            hs.calls.append(("subscribe", topic))
            hs.subscriptions.append((topic, handler))

        async def wait_until_connected(self, *, timeout: float) -> None:
            hs.calls.append(("wait_until_connected", timeout))

    class FakePump:
        def __init__(self, **kwargs: Any) -> None:
            hs.pump_kwargs = kwargs

        async def __aenter__(self) -> FakePump:
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

    @contextmanager
    def fake_log_context(**kwargs: Any) -> Iterator[None]:
        hs.log_ctx_kwargs = kwargs
        hs.inside = True
        try:
            yield
        finally:
            hs.inside = False

    async def fake_run_encoder(**kwargs: Any) -> int:
        hs.encoder_inside = hs.inside
        hs.encoder_kwargs = kwargs
        hs.calls.append(("encode", None))
        if hs.encoder_exc is not None:
            raise hs.encoder_exc
        return hs.size

    monkeypatch.setattr(m, "BackendClient", FakeApi)
    monkeypatch.setattr(m, "WSClient", FakeWS)
    monkeypatch.setattr(m, "HeartbeatPump", FakePump)
    monkeypatch.setattr(m, "with_log_context", fake_log_context)
    monkeypatch.setattr(m, "_run_encoder", fake_run_encoder)
    return hs


async def test_success(h: Harness) -> None:
    assert await m.run() == 0

    assert h.api_kwargs == {"base_url": "https://backend:8443", "service_token": "tok", "hostname": "host1"}
    ws = dict(h.ws_kwargs)
    ctx = ws.pop("ssl_context")
    assert isinstance(ctx, ssl.SSLContext)
    assert ws == {"url": "wss://backend:8443/ws", "service_token": "tok", "hostname": "host1", "task_id": "t1"}
    assert [(t) for t, _ in h.subscriptions] == ["transcoder.commands.t1"]
    assert h.names() == [
        "subscribe",
        "wait_until_connected",
        "register",
        "claim",
        "encode",
        "complete",
        "close",
    ]
    assert ("wait_until_connected", 10.0) in h.calls
    assert h.register_kwargs["task_id"] == "t1"
    assert isinstance(h.register_kwargs["hw_caps"], HardwareCaps)
    assert ("claim", ("t1",)) in h.calls
    assert h.log_ctx_kwargs == {"job_id": "job1", "track_id": "trk1", "session_application_id": "sa1"}
    assert h.claim_inside is True
    assert h.encoder_inside is True

    ek = h.encoder_kwargs
    preset = h.response.transcode_preset
    assert ek["tool"] == TranscodeTool.HANDBRAKE
    assert ek["preset"] is preset
    assert ek["raw_input"] == Path("/raw/in.mkv")
    assert ek["final_output"] == Path("/media") / "Movies/Film/film.mkv"
    assert ek["duration_seconds"] == 123
    assert isinstance(ek["state"], ProgressState)
    assert h.pump_kwargs["state"] is ek["state"]
    assert h.pump_kwargs["task_id"] == "t1"
    assert h.pump_kwargs["api"] is not None
    assert h.pump_kwargs["ws"] is not None
    assert isinstance(ek["cancel_event"], asyncio.Event)
    assert not ek["cancel_event"].is_set()

    assert h.complete_kwargs == {
        "args": ("t1",),
        "output_path": "Movies/Film/film.mkv",
        "size_bytes": 4242,
        "duration_seconds": 123,
    }
    assert "fail" not in h.names()
    assert h.names().count("close") == 1
    assert h.names()[-1] == "close"


async def test_no_preset_uses_tool_none(h: Harness) -> None:
    h.response.transcode_preset = None  # type: ignore[assignment]
    assert await m.run() == 0
    assert h.encoder_kwargs["tool"] == TranscodeTool.NONE
    assert h.encoder_kwargs["preset"] is None


async def test_no_output_path_falls_back_to_media_root(h: Harness) -> None:
    h.response.task.output_path = None  # type: ignore[assignment]
    assert await m.run() == 0
    assert h.encoder_kwargs["final_output"] == Path("/media")
    assert h.complete_kwargs["output_path"] == "."


async def test_cancel_requested_reports_cancelled_and_returns_zero(h: Harness) -> None:
    h.encoder_exc = m.CancelRequested()
    assert await m.run() == 0
    assert h.fail_kwargs == [(("t1",), {"last_error": "cancelled by user"})]
    assert "complete" not in h.names()
    assert h.names()[-1] == "close"


async def test_long_error_is_clipped_and_returns_one(h: Harness) -> None:
    message = "x" * (m._MAX_ERROR_CHARS + 50)
    h.encoder_exc = RuntimeError(message)
    assert await m.run() == 1
    ((args, kwargs),) = h.fail_kwargs
    assert args == ("t1",)
    assert kwargs["last_error"] == m._clip_error(message)
    assert kwargs["last_error"].startswith("…(truncated)…")
    assert "complete" not in h.names()
    assert h.names()[-1] == "close"


async def test_short_error_is_passed_unchanged(h: Harness) -> None:
    h.encoder_exc = RuntimeError("boom")
    assert await m.run() == 1
    assert h.fail_kwargs == [(("t1",), {"last_error": "boom"})]
    assert h.names()[-1] == "close"


async def test_cancel_handler_sets_event_only_for_task_cancel(h: Harness) -> None:
    await m.run()
    (_, handler) = h.subscriptions[0]
    event = h.encoder_kwargs["cancel_event"]

    def envelope(event_type: str) -> WSEnvelope:
        return WSEnvelope(
            event_id="e1",
            event_type=event_type,
            emitted_at=datetime.now(UTC),
            topic="transcoder.commands.t1",
        )

    await handler(envelope("something.else"))
    assert not event.is_set()
    await handler(envelope("task.cancel"))
    assert event.is_set()


def _cancel_envelope(event_type: str) -> WSEnvelope:
    return WSEnvelope(
        event_id="e1",
        event_type=event_type,
        emitted_at=datetime.now(UTC),
        topic="transcoder.commands.t1",
    )


async def test_cancel_listener_sets_event_on_task_cancel() -> None:
    event = asyncio.Event()
    await m._cancel_listener(event)(_cancel_envelope("task.cancel"))
    assert event.is_set()


async def test_cancel_listener_ignores_other_event_types() -> None:
    event = asyncio.Event()
    await m._cancel_listener(event)(_cancel_envelope("something.else"))
    assert not event.is_set()


async def test_register_failure_propagates_and_closes(h: Harness) -> None:
    h.register_exc = ValueError("no register")
    with pytest.raises(ValueError, match="no register"):
        await m.run()
    assert "claim" not in h.names()
    assert "encode" not in h.names()
    assert h.names()[-1] == "close"
    assert h.names().count("close") == 1


async def test_plain_http_backend_gives_ws_url(h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ARM_BACKEND_URL", "http://backend:8080")
    assert await m.run() == 0
    assert h.ws_kwargs["url"] == "ws://backend:8080/ws"


def test_backend_ssl_context_verifies_certificates() -> None:
    ctx = m._backend_ssl_context()
    assert isinstance(ctx, ssl.SSLContext)
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert ctx.check_hostname is True


class _CompleteRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def complete(self, task_id: str, **kwargs: Any) -> None:
        self.calls.append((task_id, kwargs))


async def test_report_complete_sends_path_relative_to_media_root() -> None:
    api = _CompleteRecorder()
    await m._report_complete(
        api=api,  # type: ignore[arg-type]
        task_id="t1",
        media_root="/media",
        final_output=Path("/media/Movies/a.mkv"),
        size=5,
        duration=7,
    )
    assert api.calls == [("t1", {"output_path": "Movies/a.mkv", "size_bytes": 5, "duration_seconds": 7})]


async def test_report_complete_output_equal_to_media_root_is_dot() -> None:
    api = _CompleteRecorder()
    await m._report_complete(
        api=api,  # type: ignore[arg-type]
        task_id="t1",
        media_root="/media",
        final_output=Path("/media"),
        size=5,
        duration=7,
    )
    assert api.calls[0][1]["output_path"] == "."
