"""The Backend's in-memory HandBrake schema.

The schema lives in the `handbrake_schemas` table (newest row is current) and is held loaded here, so
validation, claim and register read it without touching the database. `replace` swaps one reference, so a
reader never sees a half-built schema.
"""

from __future__ import annotations

import logging

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from arm_common import HandbrakeSchemaRecord
from arm_common.handbrake_schema.loader import load_schema
from arm_common.handbrake_schema.types import HandbrakeSchema

logger = logging.getLogger("arm_backend.handbrake_schema_store")


class SchemaStore:
    def __init__(self) -> None:
        self._schema: HandbrakeSchema | None = None

    def current(self) -> HandbrakeSchema | None:
        return self._schema

    def replace(self, schema: HandbrakeSchema) -> None:
        self._schema = schema

    async def load_latest(self, db: AsyncSession) -> None:
        """Load the newest stored dump, if any. A row that no longer loads leaves the store empty (the
        boot run fetches a fresh one)."""
        stmt = select(HandbrakeSchemaRecord).order_by(col(HandbrakeSchemaRecord.fetched_at).desc())
        record = (await db.execute(stmt)).scalars().first()
        if record is None:
            return
        try:
            self.replace(load_schema(record.raw))
        except Exception as exc:  # noqa: BLE001 - a stale stored dump must not stop the backend booting
            logger.warning("handbrake schema: stored dump %s could not be loaded: %s", record.id, exc)


def get_schema_store(request: Request) -> SchemaStore:
    store: SchemaStore = request.app.state.handbrake_schema_store
    return store
