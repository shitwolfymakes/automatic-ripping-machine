"""A transcoder that never checks in must not strand a container.

The spawn used to leave the first container running while the task stayed
queued, so the next tick's respawn collided with its own container name (409)
and burned the task's attempts with a misleading "failed before spawn".
"""

from __future__ import annotations

from unittest.mock import MagicMock

import docker.errors
import pytest

from arm_backend import transcode_dispatcher as tdmod
from arm_common import TranscodeTaskStatus
from tests._staged_sources import staged_by_default
from tests.test_transcode_dispatcher_full import _disp
from tests.test_transcode_dispatcher_probe import _one_encode_task_db

_NAME = "arm-transcode-" + "txt_1"[-12:]
_TLS_LOG = (
    b"starting\n"
    b"ws connection error: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
    b"unable to get local issuer certificate\n"
) * 2


@pytest.fixture(autouse=True)
def _staged_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    staged_by_default(monkeypatch)


def _api_error(status: int, message: str) -> docker.errors.APIError:
    response = MagicMock()
    response.status_code = status
    return docker.errors.APIError(message, response=response, explanation=message)


def _leftover(task_id: str = "txt_1", logs: bytes = b"") -> MagicMock:
    container = MagicMock()
    container.labels = {tdmod._DOCKER_LABEL_KEY: task_id}
    container.logs.return_value = logs
    return container


def _in_use() -> docker.errors.APIError:
    return _api_error(409, f'Conflict. The container name "/{_NAME}" is already in use by container "abc"')


async def test_waiting_for_checkin_does_not_respawn() -> None:
    db = _one_encode_task_db()
    d = _disp(db, MAX_PARALLEL_TRANSCODES=2)
    d._docker.containers.run.return_value = MagicMock()
    assert await d.spawn_pending(db) == 1
    assert await d.spawn_pending(db) == 0
    assert d._docker.containers.run.call_count == 1
    assert db.rows["transcode_tasks"][0].attempts == 0


async def test_checkin_timeout_removes_the_container_and_counts_an_attempt(monkeypatch) -> None:
    db = _one_encode_task_db()
    d = _disp(db, MAX_PARALLEL_TRANSCODES=2, ARM_TRANSCODE_CHECKIN_TIMEOUT_SECONDS=60)
    d._docker.containers.run.return_value = MagicMock()
    await d.spawn_pending(db)
    leftover = _leftover(logs=_TLS_LOG)
    d._docker.containers.get.return_value = leftover
    now = tdmod.time.monotonic()
    monkeypatch.setattr(tdmod.time, "monotonic", lambda: now + 61)

    await d.spawn_pending(db)

    d._docker.containers.get.assert_called_with(_NAME)
    leftover.stop.assert_called_once()
    leftover.remove.assert_called_once_with(force=True)
    task = db.rows["transcode_tasks"][0]
    assert task.status == TranscodeTaskStatus.QUEUED
    assert task.attempts == 1
    assert task.last_error is not None
    assert task.last_error.startswith("transcoder did not check in within 60 s")
    assert "CERTIFICATE_VERIFY_FAILED" in task.last_error
    # The next tick spawns a fresh container instead of 409ing on the old one.
    d._docker.containers.run.reset_mock()
    await d.spawn_pending(db)
    assert d._docker.containers.run.call_count == 1


async def test_checkin_timeout_on_the_last_attempt_fails_the_task_honestly(monkeypatch, caplog) -> None:
    db = _one_encode_task_db(attempts=2)
    d = _disp(db, MAX_PARALLEL_TRANSCODES=2, ARM_TRANSCODE_CHECKIN_TIMEOUT_SECONDS=60, ARM_TRANSCODE_MAX_ATTEMPTS=3)
    d._docker.containers.run.return_value = MagicMock()
    await d.spawn_pending(db)
    d._docker.containers.get.return_value = _leftover(logs=_TLS_LOG)
    now = tdmod.time.monotonic()
    monkeypatch.setattr(tdmod.time, "monotonic", lambda: now + 61)

    with caplog.at_level("DEBUG", logger="arm_backend.transcode_dispatcher"):
        await d.spawn_pending(db)

    task = db.rows["transcode_tasks"][0]
    assert task.status == TranscodeTaskStatus.FAILED
    assert "did not check in within 60 s" in task.last_error
    assert "attempts=3" in task.last_error
    assert "before spawn" not in caplog.text
    assert "after spawn" in caplog.text


async def test_a_name_conflict_with_our_own_leftover_is_removed_and_recreated() -> None:
    db = _one_encode_task_db()
    d = _disp(db, MAX_PARALLEL_TRANSCODES=2)
    fresh = MagicMock()
    d._docker.containers.run.side_effect = [_in_use(), fresh]
    leftover = _leftover()
    d._docker.containers.get.return_value = leftover

    assert await d.spawn_pending(db) == 1

    leftover.remove.assert_called_once_with(force=True)
    assert d._docker.containers.run.call_count == 2
    assert db.rows["transcode_tasks"][0].attempts == 0


async def test_a_name_conflict_with_someone_elses_container_is_not_removed() -> None:
    db = _one_encode_task_db()
    d = _disp(db, MAX_PARALLEL_TRANSCODES=2)
    d._docker.containers.run.side_effect = _in_use()
    stranger = _leftover(task_id="txt_other")
    d._docker.containers.get.return_value = stranger

    assert await d.spawn_pending(db) == 0

    stranger.remove.assert_not_called()
    assert db.rows["transcode_tasks"][0].attempts == 1


async def test_a_start_error_removes_the_created_container() -> None:
    db = _one_encode_task_db()
    d = _disp(db, MAX_PARALLEL_TRANSCODES=2)
    d._docker.containers.run.side_effect = _api_error(500, "OCI runtime create failed")
    created = _leftover()
    d._docker.containers.get.return_value = created

    assert await d.spawn_pending(db) == 0

    created.remove.assert_called_once_with(force=True)
    assert db.rows["transcode_tasks"][0].attempts == 1
