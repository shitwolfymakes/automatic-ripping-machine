"""SchemaStore: the in-memory current HandBrake schema, seeded from the newest stored row."""

from __future__ import annotations

from datetime import UTC, datetime

from arm_backend.handbrake_schema_store import SchemaStore
from arm_common import HandbrakeSchemaRecord

from tests._fakes import FakeSession
from tests._hb_schema import fixture_raw, fixture_schema


def _record(tag: str, fetched_at: datetime, raw: dict | None = None) -> HandbrakeSchemaRecord:
    return HandbrakeSchemaRecord(
        content_hash=f"hash-{tag}",
        handbrake_tag=tag,
        preset_version="1.0.0",
        image_ref="img",
        raw=raw if raw is not None else fixture_raw(),
        fetched_at=fetched_at,
    )


def test_empty_until_replaced() -> None:
    store = SchemaStore()
    assert store.current() is None
    store.replace(fixture_schema())
    assert store.current() is fixture_schema()


async def test_load_latest_picks_the_newest_row() -> None:
    db = FakeSession()
    db.rows["handbrake_schemas"] = [
        _record("old", datetime(2026, 1, 1, tzinfo=UTC), raw={"junk": True}),
        _record("new", datetime(2026, 6, 1, tzinfo=UTC)),
    ]
    store = SchemaStore()
    await store.load_latest(db)  # type: ignore[arg-type]
    assert store.current() is not None
    assert store.current().content_hash == fixture_schema().content_hash


async def test_load_latest_without_rows_leaves_the_store_empty() -> None:
    store = SchemaStore()
    await store.load_latest(FakeSession())  # type: ignore[arg-type]
    assert store.current() is None


async def test_load_latest_keeps_the_store_empty_when_the_row_will_not_load() -> None:
    db = FakeSession()
    db.rows["handbrake_schemas"] = [_record("bad", datetime(2026, 1, 1, tzinfo=UTC), raw={"junk": True})]
    store = SchemaStore()
    await store.load_latest(db)  # type: ignore[arg-type]
    assert store.current() is None
