"""Backend-spawned HandBrake schema dump.

The runner starts one short-lived container of the base (no GPU) transcode image in
`python -m arm_transcode.main --dump-schema` mode. The worker prints the schema baked into the image as one
JSON line and exits 0; the runner stores a dump with a new `content_hash` as a `handbrake_schemas` row and
swaps the loaded schema into the `SchemaStore`.

Failure is reported, never raised: a non-zero exit or output that is not the expected JSON (most often an
image that predates `--dump-schema`) tells the operator to rebuild or pull the image. With no docker client
there is nothing to run and the store is left as it was.

Triggers: the boot run (`start_boot_run`), `POST /api/handbrake-schema/refresh` (`refresh`) and a transcoder
registering with a schema hash that differs from the loaded one (`request_refresh_if_hash_differs`).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import col, select

from arm_backend.config import Settings
from arm_backend.gpu_probe_runner import decode_output, is_timeout
from arm_backend.handbrake_schema_store import SchemaStore
from arm_backend.transcode_container_spec import container_identity_env
from arm_backend.transcode_dispatcher import TranscodeDispatcher
from arm_backend.transcode_images import image_for
from arm_common import HandbrakeSchemaRecord
from arm_common.handbrake_schema.loader import load_schema
from arm_common.handbrake_schema.types import HandbrakeSchema

logger = logging.getLogger("arm_backend.handbrake_schema_runner")

DUMP_TIMEOUT_S = 60
DUMP_COMMAND = ["python", "-m", "arm_transcode.main", "--dump-schema"]
DUMP_FAILURE_ERROR = (
    "schema dump failed (exit {code}); the transcode image may predate --dump-schema: rebuild or pull it"
)
NO_DOCKER_ERROR = "no docker client for transcodes"
SHUTDOWN_GRACE_S = 5.0

# (exit code, stdout) of a dump container that ran to completion, or an error text when it did not.
_Run = tuple[int, bytes | str] | str


def parse_dump_output(status_code: int, stdout: bytes | str) -> dict[str, Any] | None:
    """The raw schema object, or None when the dump did not succeed. Only the LAST non-empty stdout line is
    parsed (the entrypoint may log before the worker runs)."""
    lines = [line.strip() for line in decode_output(stdout).splitlines() if line.strip()]
    if status_code != 0 or not lines:
        return None
    try:
        raw = json.loads(lines[-1])
    except ValueError:
        return None
    return raw if isinstance(raw, dict) else None


def _version_text(schema: HandbrakeSchema) -> str:
    return ".".join(str(part) for part in schema.preset_version)


class HandbrakeSchemaRunner:
    def __init__(
        self,
        settings: Settings,
        db_factory: async_sessionmaker[AsyncSession],
        dispatcher: TranscodeDispatcher,
        store: SchemaStore,
    ) -> None:
        self._settings = settings
        self._db_factory = db_factory
        self._dispatcher = dispatcher
        self._store = store
        self._tasks: set[asyncio.Task[None]] = set()

    # --- triggers ----------------------------------------------------------

    def start_boot_run(self) -> asyncio.Task[None]:
        return self._spawn(self._refresh_quietly())

    def request_refresh_if_hash_differs(self, schema_hash: str) -> None:
        """Fire-and-forget refresh for a transcoder that reported a different schema. One refresh at a time."""
        current = self._store.current()
        if (current is not None and current.content_hash == schema_hash) or self._tasks:
            return
        self._spawn(self._refresh_quietly())

    def pending_tasks(self) -> list[asyncio.Task[None]]:
        return list(self._tasks)

    async def shutdown(self, grace_s: float = SHUTDOWN_GRACE_S) -> None:
        """Cancel running refreshes, waiting briefly so each removes its container."""
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=grace_s)

    def _spawn(self, coro: Any) -> asyncio.Task[None]:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _refresh_quietly(self) -> None:
        try:
            error = await self.refresh()
        except Exception as exc:  # noqa: BLE001 - a background refresh must never crash its task
            logger.exception("handbrake schema: refresh failed unexpectedly: %s", exc)
            return
        if error is not None:
            logger.warning("handbrake schema: refresh failed: %s", error)

    # --- one refresh -------------------------------------------------------

    async def refresh(self) -> str | None:
        """Dump the schema from the base transcode image and load it. Returns the error, or None on success."""
        docker = self._dispatcher.docker_client
        if docker is None:
            return NO_DOCKER_ERROR
        image = await self._pick_image()
        ran = await self._run_container(docker, image)
        if isinstance(ran, str):
            return ran
        status_code, stdout = ran
        raw = parse_dump_output(status_code, stdout)
        if raw is None:
            return DUMP_FAILURE_ERROR.format(code=status_code)
        try:
            schema = load_schema(raw)
        except Exception as exc:  # noqa: BLE001 - a malformed dump is reported, not raised
            return f"schema dump could not be loaded: {exc}"
        await self._store_row(raw, schema, image)
        self._store.replace(schema)
        return None

    async def _pick_image(self) -> str:
        # variant_available is never called for the base image, but image_for takes it regardless.
        return await asyncio.to_thread(
            image_for, self._settings, None, exists=self._dispatcher.images.variant_available
        )

    def _run_kwargs(self, image: str) -> dict[str, Any]:
        env = {"ARM_LOG_LEVEL": self._settings.ARM_LOG_LEVEL}
        env.update(container_identity_env(self._settings, None))
        return {
            "image": image,
            "command": list(DUMP_COMMAND),
            "environment": env,
            "network": None,
            "detach": True,
            # Kept until `logs` is read after `wait`; removed in `finally`.
            "auto_remove": False,
        }

    async def _run_container(self, docker: Any, image: str) -> _Run:
        kwargs = self._run_kwargs(image)
        logger.info("handbrake schema: dumping the schema from %s", image)
        try:
            container = await asyncio.to_thread(lambda: docker.containers.run(**kwargs))
        except Exception as exc:  # noqa: BLE001 - reported to the caller
            return f"schema dump container could not start: {exc}"
        try:
            return await self._wait_and_read(container)
        finally:
            try:
                await asyncio.to_thread(container.remove, force=True)
            except Exception as exc:  # noqa: BLE001 - best-effort cleanup
                logger.warning("handbrake schema: could not remove the dump container: %s", exc)

    async def _wait_and_read(self, container: Any) -> _Run:
        try:
            result = await asyncio.to_thread(container.wait, timeout=DUMP_TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001 - reported to the caller
            if is_timeout(exc):
                return f"schema dump timed out after {DUMP_TIMEOUT_S} s"
            return f"schema dump failed while waiting for the container: {exc}"
        raw_code = result.get("StatusCode")
        status_code = raw_code if isinstance(raw_code, int) else -1
        stdout = await asyncio.to_thread(container.logs, stdout=True, stderr=False)
        return status_code, stdout

    async def _store_row(self, raw: dict[str, Any], schema: HandbrakeSchema, image: str) -> None:
        """Insert the dump unless a row with this hash exists (its `fetched_at` is left as it was).

        An overlapping refresh can insert the same hash between the check and the commit; the unique
        `content_hash` then rejects this insert, which is rolled back and treated as already stored.
        """
        async with self._db_factory() as db:
            stmt = select(HandbrakeSchemaRecord).where(col(HandbrakeSchemaRecord.content_hash) == schema.content_hash)
            if (await db.execute(stmt)).scalars().first() is not None:
                return
            db.add(
                HandbrakeSchemaRecord(
                    content_hash=schema.content_hash,
                    handbrake_tag=schema.handbrake_tag,
                    preset_version=_version_text(schema),
                    image_ref=image,
                    raw=raw,
                    fetched_at=datetime.now(UTC),
                )
            )
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
