"""Phase 7 WS principal + authz extensions for the transcoder kind.

Covers:
- `resolve_principal` returns `kind="transcoder"` when the auth handshake
  passes a service token AND `task_id_hint` is set (sourced from
  `X-ARM-Task-Id` at the handshake).
- `can_subscribe` allows a transcoder to subscribe `transcoder.commands.{task_id}`
  but no other topic.
- `can_publish` allows a transcoder to publish on `transcode.progress.{task_id}`
  iff the underlying TranscodeTask is `claimed_by` the same hostname AND in
  `IN_PROGRESS`. Other progress topics, other tasks, or stale claim → 403.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok")

from arm_backend.config import settings  # noqa: E402
from arm_backend.ws.authz import can_publish, can_subscribe  # noqa: E402
from arm_backend.ws.principal import (  # noqa: E402
    AuthError,
    ServicePrincipal,
    UIPrincipal,
    resolve_principal,
)
from arm_common import (  # noqa: E402
    TranscodeTask,
    TranscodeTaskStatus,
)


class _FakeResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class _FakeSession:
    def __init__(self, tasks: dict[str, TranscodeTask]) -> None:
        self._tasks = tasks

    async def execute(self, stmt: Any) -> _FakeResult:
        compiled = stmt.compile(compile_kwargs={"literal_binds": True})
        sql = str(compiled)
        if "FROM transcode_tasks" in sql:
            import re

            m = re.search(r"\.id = '([^']+)'", sql)
            return _FakeResult(self._tasks.get(m.group(1)) if m else None)
        return _FakeResult(None)


_HOSTNAME = "arm-transcode-abc123"


@pytest.fixture
def session() -> Any:
    return _FakeSession(
        tasks={
            "txt_live": TranscodeTask(
                id="txt_live",
                session_application_id="sap_1",
                source_track_id="trk_1",
                status=TranscodeTaskStatus.IN_PROGRESS,
                claimed_by=_HOSTNAME,
                attempts=1,
                progress_pct=50,
            ),
            "txt_other": TranscodeTask(
                id="txt_other",
                session_application_id="sap_1",
                source_track_id="trk_2",
                status=TranscodeTaskStatus.IN_PROGRESS,
                claimed_by="someone-else",
                attempts=1,
                progress_pct=10,
            ),
            "txt_stale": TranscodeTask(
                id="txt_stale",
                session_application_id="sap_1",
                source_track_id="trk_3",
                status=TranscodeTaskStatus.QUEUED,
                claimed_by=None,
                attempts=0,
                progress_pct=0,
            ),
        }
    )


# ---- resolve_principal -------------------------------------------------------


def test_service_token_with_task_id_hint_yields_transcoder() -> None:
    p = resolve_principal(settings.ARM_SERVICE_TOKEN, _HOSTNAME, task_id_hint="txt_live")
    assert isinstance(p, ServicePrincipal)
    assert p.kind == "transcoder"
    assert p.hostname == _HOSTNAME
    assert p.task_id == "txt_live"


def test_service_token_without_task_id_hint_yields_ripper() -> None:
    p = resolve_principal(settings.ARM_SERVICE_TOKEN, "arm-ripper-sr0")
    assert isinstance(p, ServicePrincipal)
    assert p.kind == "ripper"
    assert p.task_id is None


def test_service_token_without_hostname_raises() -> None:
    with pytest.raises(AuthError, match="hostname"):
        resolve_principal(settings.ARM_SERVICE_TOKEN, None, task_id_hint="txt_live")


# ---- can_subscribe -----------------------------------------------------------


async def test_transcoder_can_subscribe_own_command_topic(session: Any) -> None:
    p = ServicePrincipal(kind="transcoder", hostname=_HOSTNAME, task_id="txt_live")
    assert await can_subscribe(p, "transcoder.commands.txt_live", session) is True


async def test_transcoder_cannot_subscribe_other_command_topic(session: Any) -> None:
    p = ServicePrincipal(kind="transcoder", hostname=_HOSTNAME, task_id="txt_live")
    assert await can_subscribe(p, "transcoder.commands.txt_other", session) is False


async def test_transcoder_cannot_subscribe_to_ui_topics(session: Any) -> None:
    p = ServicePrincipal(kind="transcoder", hostname=_HOSTNAME, task_id="txt_live")
    for topic in ("transcode.events", "ripper.events", "system.events", "transcode.progress.txt_live"):
        assert await can_subscribe(p, topic, session) is False


# ---- can_publish -------------------------------------------------------------


async def test_transcoder_can_publish_own_progress_when_in_progress(session: Any) -> None:
    p = ServicePrincipal(kind="transcoder", hostname=_HOSTNAME, task_id="txt_live")
    assert await can_publish(p, "transcode.progress.txt_live", session) is True


async def test_transcoder_cannot_publish_other_tasks_progress(session: Any) -> None:
    p = ServicePrincipal(kind="transcoder", hostname=_HOSTNAME, task_id="txt_live")
    assert await can_publish(p, "transcode.progress.txt_other", session) is False


async def test_transcoder_cannot_publish_when_claimed_by_other_host(session: Any) -> None:
    p = ServicePrincipal(kind="transcoder", hostname="some-other-host", task_id="txt_live")
    assert await can_publish(p, "transcode.progress.txt_live", session) is False


async def test_transcoder_cannot_publish_when_task_not_in_progress(session: Any) -> None:
    p = ServicePrincipal(kind="transcoder", hostname=_HOSTNAME, task_id="txt_stale")
    assert await can_publish(p, "transcode.progress.txt_stale", session) is False


async def test_transcoder_cannot_publish_to_typed_events(session: Any) -> None:
    p = ServicePrincipal(kind="transcoder", hostname=_HOSTNAME, task_id="txt_live")
    assert await can_publish(p, "transcode.events", session) is False
    assert await can_publish(p, "ripper.events", session) is False


async def test_ui_cannot_publish_to_transcode_progress(session: Any) -> None:
    ui = UIPrincipal(user_id="u_1", username="admin")
    assert await can_publish(ui, "transcode.progress.txt_live", session) is False
