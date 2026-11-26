"""HandbrakeSchemaRunner: runs the base transcode image with --dump-schema and stores the result.

A fake docker client scripts the container's exit code, stdout and `wait` behaviour, like
test_gpu_probe_runner.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from sqlalchemy.exc import IntegrityError

from arm_backend import handbrake_schema_runner as runner_mod
from arm_backend.config import Settings
from arm_backend.handbrake_schema_runner import (
    DUMP_COMMAND,
    DUMP_FAILURE_ERROR,
    DUMP_TIMEOUT_S,
    HandbrakeSchemaRunner,
    parse_dump_output,
)
from arm_backend.handbrake_schema_store import SchemaStore
from arm_backend.transcode_dispatcher import TranscodeDispatcher
from arm_common import HandbrakeSchemaRecord

from tests._fakes import FakeSession
from tests._hb_schema import fixture_raw, fixture_schema
from tests.test_gpu_probe_runner import _Container, _db_factory, _Docker, _Hub, _settings


def _dump(raw: dict[str, Any] | None = None) -> bytes:
    return b"entrypoint noise\n" + json.dumps(raw or fixture_raw()).encode() + b"\n\n"


def _build(
    container: _Container | None = None, *, docker: bool = True, settings: Settings | None = None
) -> tuple[HandbrakeSchemaRunner, FakeSession, _Docker | None, SchemaStore, _Container]:
    db = FakeSession()
    settings = settings or _settings()
    box = container or _Container(stdout=_dump())
    fake_docker = _Docker(box) if docker else None
    dispatcher = TranscodeDispatcher(
        settings=settings,
        db_factory=_db_factory(db),
        docker_client=fake_docker,
        hub=_Hub(),  # type: ignore[arg-type]
    )
    dispatcher.images.variant_available = lambda _image: False  # type: ignore[method-assign]
    store = SchemaStore()
    runner = HandbrakeSchemaRunner(settings, _db_factory(db), dispatcher, store)  # type: ignore[arg-type]
    return runner, db, fake_docker, store, box


def _rows(db: FakeSession) -> list[HandbrakeSchemaRecord]:
    return db.rows.get("handbrake_schemas", [])


# --- parse_dump_output ---------------------------------------------------------


def test_parse_takes_the_last_json_line() -> None:
    assert parse_dump_output(0, _dump({"a": 1})) == {"a": 1}
    assert parse_dump_output(0, '{"a": 1}') == {"a": 1}


def test_parse_rejects_failures_and_non_objects() -> None:
    assert parse_dump_output(1, _dump()) is None
    assert parse_dump_output(0, b"") is None
    assert parse_dump_output(0, b"not json") is None
    assert parse_dump_output(0, b"[1, 2]") is None


# --- refresh -------------------------------------------------------------------


async def test_success_stores_one_row_and_fills_the_store() -> None:
    runner, db, docker, store, container = _build()
    assert await runner.refresh() is None

    assert len(_rows(db)) == 1
    row = _rows(db)[0]
    assert row.content_hash == fixture_schema().content_hash
    assert row.handbrake_tag == fixture_schema().handbrake_tag
    assert row.preset_version == "{}.{}.{}".format(*fixture_schema().preset_version)
    assert row.image_ref == "arm-transcode:latest"
    assert row.raw == fixture_raw()
    assert db.committed == 1
    assert store.current() is not None and store.current().content_hash == row.content_hash

    assert docker is not None
    kwargs = docker.containers.calls[0]
    assert kwargs["command"] == DUMP_COMMAND == ["python", "-m", "arm_transcode.main", "--dump-schema"]
    assert kwargs["image"] == "arm-transcode:latest"
    assert kwargs["auto_remove"] is False
    assert "devices" not in kwargs and "device_requests" not in kwargs
    assert container.wait_timeouts == [DUMP_TIMEOUT_S]
    assert container.removed == [True]


async def test_the_same_hash_twice_stores_one_row_but_resets_the_store() -> None:
    runner, db, _docker, store, _container = _build()
    assert await runner.refresh() is None
    store.replace(None)  # type: ignore[arg-type]
    assert await runner.refresh() is None
    assert len(_rows(db)) == 1
    assert store.current() is not None


async def test_a_concurrent_insert_of_the_same_hash_is_treated_as_stored() -> None:
    """Overlapping refreshes: the unique content_hash rejects the loser's insert; it rolls back and loads."""
    runner, db, _docker, store, _container = _build()
    db.commit_raises = IntegrityError("INSERT", {}, Exception("duplicate content_hash"))
    assert await runner.refresh() is None
    assert db.call_log[-2:] == ["commit", "rollback"]
    assert store.current() is not None and store.current().content_hash == fixture_schema().content_hash


async def test_a_new_hash_adds_a_second_row() -> None:
    runner, db, docker, store, _container = _build()
    assert await runner.refresh() is None
    assert docker is not None
    newer = {**fixture_raw(), "handbrake_tag": "9.9.9"}
    docker.containers.container.stdout = _dump(newer)
    assert await runner.refresh() is None
    assert len(_rows(db)) == 2
    assert store.current().handbrake_tag == "9.9.9"  # type: ignore[union-attr]


async def test_nonzero_exit_reports_the_stale_image_error() -> None:
    runner, db, _docker, store, container = _build(_Container(status=1, stdout=b"oops"))
    assert await runner.refresh() == DUMP_FAILURE_ERROR.format(code=1)
    assert _rows(db) == [] and store.current() is None
    assert container.removed == [True]


async def test_unparseable_stdout_reports_the_same_error() -> None:
    runner, db, _docker, store, _c = _build(_Container(status=0, stdout=b"not json"))
    assert await runner.refresh() == DUMP_FAILURE_ERROR.format(code=0)
    assert _rows(db) == [] and store.current() is None


async def test_a_dump_that_cannot_be_loaded_is_reported_and_not_stored() -> None:
    runner, db, _docker, store, _c = _build(_Container(stdout=_dump({"junk": 1})))
    error = await runner.refresh()
    assert error is not None and error.startswith("schema dump could not be loaded")
    assert _rows(db) == [] and store.current() is None


async def test_no_docker_client_leaves_the_store_as_it_was() -> None:
    runner, db, _docker, store, _c = _build(docker=False)
    store.replace(fixture_schema())
    assert await runner.refresh() == "no docker client for transcodes"
    assert store.current() is fixture_schema()
    assert _rows(db) == []


async def test_a_container_that_fails_to_start_is_reported() -> None:
    runner, _db, docker, store, _c = _build()
    assert docker is not None
    docker.containers.run_exc = RuntimeError("daemon down")
    assert await runner.refresh() == "schema dump container could not start: daemon down"
    assert store.current() is None


async def test_a_timeout_is_reported_and_the_container_removed() -> None:
    container = _Container(wait_exc=TimeoutError("read timed out"))
    runner, _db, _docker, _store, _c = _build(container)
    assert await runner.refresh() == f"schema dump timed out after {DUMP_TIMEOUT_S} s"
    assert container.removed == [True]


async def test_another_wait_failure_is_reported() -> None:
    container = _Container(wait_exc=RuntimeError("socket closed"))
    runner, _db, _docker, _store, _c = _build(container)
    assert await runner.refresh() == "schema dump failed while waiting for the container: socket closed"


async def test_a_missing_status_code_counts_as_a_failure() -> None:
    runner, _db, _docker, _store, _c = _build(_Container(status=None, stdout=_dump()))
    assert await runner.refresh() == DUMP_FAILURE_ERROR.format(code=-1)


async def test_a_failing_container_removal_is_only_logged() -> None:
    container = _Container(stdout=_dump())
    container.remove_exc = RuntimeError("gone")
    runner, _db, _docker, store, _c = _build(container)
    assert await runner.refresh() is None
    assert store.current() is not None


# --- triggers ------------------------------------------------------------------


async def test_boot_run_refreshes_in_the_background_and_never_raises() -> None:
    runner, db, _docker, store, _c = _build()
    await runner.start_boot_run()
    assert store.current() is not None and len(_rows(db)) == 1

    runner2, _db2, docker2, store2, _c2 = _build()
    assert docker2 is not None
    docker2.containers.run_exc = RuntimeError("x")
    await runner2.start_boot_run()
    assert store2.current() is None


async def test_boot_run_survives_an_unexpected_exception(monkeypatch: Any) -> None:
    runner, _db, _docker, store, _c = _build()

    async def boom() -> str | None:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(runner, "refresh", boom)
    await runner.start_boot_run()
    assert store.current() is None


async def test_request_refresh_skips_a_matching_hash() -> None:
    runner, _db, docker, store, _c = _build()
    store.replace(fixture_schema())
    runner.request_refresh_if_hash_differs(fixture_schema().content_hash)
    assert runner.pending_tasks() == []
    assert docker is not None and docker.containers.calls == []


async def test_request_refresh_runs_once_for_a_different_hash() -> None:
    runner, _db, docker, store, _c = _build()
    store.replace(fixture_schema())
    runner.request_refresh_if_hash_differs("other")
    runner.request_refresh_if_hash_differs("other")
    tasks = runner.pending_tasks()
    assert len(tasks) == 1
    await asyncio.gather(*tasks)
    assert runner.pending_tasks() == []
    assert docker is not None and len(docker.containers.calls) == 1


async def test_shutdown_cancels_pending_runs() -> None:
    runner, _db, _docker, _store, container = _build()
    gate = asyncio.Event()

    async def slow() -> str | None:
        await gate.wait()
        return None

    runner.refresh = slow  # type: ignore[method-assign]
    task = runner.start_boot_run()
    await runner.shutdown(grace_s=1.0)
    assert task.cancelled()
    assert runner.pending_tasks() == []
    assert container.removed == []


async def test_shutdown_with_nothing_pending_returns() -> None:
    runner, *_ = _build()
    await runner.shutdown()
    assert runner_mod.SHUTDOWN_GRACE_S > 0
