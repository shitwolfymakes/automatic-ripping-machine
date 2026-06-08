"""Real-DB end-to-end harness.

Unlike the per-router tests (which hand-assemble a one-router `FastAPI()` and
override `get_session` with the in-memory `tests._fakes.FakeSession`), these
fixtures boot the *actual* `arm_backend.main:app` — lifespan, middleware,
seeders, every router — against a real SQLAlchemy engine backed by a
file-backed SQLite database.

This is what closes the structural coverage holes the fake-session approach
can never reach: `main.py` (app wiring + lifespan), `db.py` (engine/session
plumbing), `seeders.py`, and the real auth path that loads a user row.

SQLite stand-in for Postgres
----------------------------
The production models pin Postgres-only column types (`JSONB`, `ARRAY`).
Two steps make them work on SQLite without touching production code:

1. ``@compiles(..., "sqlite")`` shims so the DDL emitted by
   ``metadata.create_all`` is valid SQLite.
2. Swapping those column *types* to the generic ``JSON`` type in the live
   ``SQLModel.metadata`` before the ORM mapper compiles any statement, so
   bind/result processing round-trips lists and dicts on SQLite.

Migrations themselves (Postgres-flavoured Alembic revisions) are *not*
exercised here — `main._run_migrations` is replaced with a metadata
`create_all`. Migration fidelity is a separate concern from API coverage.
"""

from __future__ import annotations

import os

# Set before `arm_backend.config` instantiates its Settings singleton.
#
# This conftest is imported during collection *before* any test module, so
# its `setdefault` calls win the session-wide singleton. The values must
# therefore match the rest of the suite's convention or unrelated
# fake-session tests (which assume these exact values) start 401'ing:
#   - DATABASE_URL: a dummy Postgres URL. `db._build_engine` runs at import
#     and its urlparse round-trip can't handle `sqlite+aiosqlite://`; asyncpg
#     connects lazily so no DB is touched, and `app_client` swaps the engine
#     for a real SQLite one before the lifespan opens a connection.
#   - ARM_SERVICE_TOKEN: "tok-service" — the value the service-token tests
#     (e.g. test_transcoder_router) hard-code in their auth headers.
# Empty ARM_HOST_* + no docker socket => transcode dispatcher stays disabled.
os.environ.setdefault("DATABASE_URL", "postgresql://x:x@localhost/x")
os.environ.setdefault("ARM_SERVICE_TOKEN", "tok-service")

from collections.abc import AsyncIterator, Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import JSON  # noqa: E402
from sqlalchemy.dialects.postgresql import ARRAY, JSONB  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402
from sqlmodel import SQLModel  # noqa: E402

import arm_common.models  # noqa: E402,F401  (populate SQLModel.metadata)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type: object, _compiler: object, **_kw: object) -> str:
    return "JSON"


@compiles(ARRAY, "sqlite")
def _compile_array_sqlite(_type: object, _compiler: object, **_kw: object) -> str:
    return "JSON"


def _retype_pg_columns_to_json() -> list[tuple[object, object]]:
    """Replace `JSONB`/`ARRAY` column types with generic `JSON` in the live
    metadata so SQLite gets a working bind/result processor.

    `SQLModel.metadata` is process-global and shared with the fake-session
    per-router tests, which assert against the real Postgres types — so this
    returns the originals for the fixture to restore on teardown. Must run
    before the mapper compiles its first statement against this DB."""
    saved: list[tuple[object, object]] = []
    for table in SQLModel.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, (JSONB, ARRAY)):
                saved.append((column, column.type))
                column.type = JSON()
    return saved


def _restore_column_types(saved: list[tuple[object, object]]) -> None:
    for column, original in saved:
        column.type = original  # type: ignore[attr-defined]


@pytest.fixture(scope="session")
def _sqlite_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    db_path = tmp_path_factory.mktemp("e2e-db") / "arm-e2e.sqlite"
    return f"sqlite+aiosqlite:///{db_path}"


@pytest.fixture
def app_client(_sqlite_url: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[object]:
    """Boot the real app against a fresh SQLite DB and yield a `TestClient`.

    The DB file is unique per test (function-scoped `tmp_path`), so seeded
    state never leaks between tests.
    """
    from fastapi.testclient import TestClient

    import arm_backend.db as db_mod
    import arm_backend.main as main_mod
    import arm_backend.routers.auth as auth_router_mod
    import arm_backend.seeders as seeders_mod

    saved_types = _retype_pg_columns_to_json()

    # Argon2's default work factor is deliberately ~0.5 s/op; the seeded admin
    # hash + login verify + rehash + change-password add up to ~10 s/test.
    # The hash self-describes its params, so a cheap hasher round-trips with
    # the real verifier — this swaps cost, not the algorithm or code path.
    from argon2 import PasswordHasher

    cheap_hasher = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1)
    monkeypatch.setattr(auth_router_mod, "_hasher", cheap_hasher)
    monkeypatch.setattr(seeders_mod, "PasswordHasher", lambda: cheap_hasher)

    db_file = tmp_path / "arm.sqlite"
    url = f"sqlite+aiosqlite:///{db_file}"
    test_engine = create_async_engine(url, echo=False, future=True)
    test_sessionmaker = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)

    # Redirect every SessionLocal consumer at the real engine. main.py captured
    # `SessionLocal` by name at import, so both modules need patching.
    monkeypatch.setattr(db_mod, "engine", test_engine)
    monkeypatch.setattr(db_mod, "SessionLocal", test_sessionmaker)
    monkeypatch.setattr(main_mod, "SessionLocal", test_sessionmaker)

    # Force the docker-less lifespan path deterministically: the transcode
    # dispatcher needs a real docker socket, which the SQLite e2e tier can't
    # provide. Without this the lifespan would branch on whatever the host
    # happens to have, making main.py coverage environment-dependent.
    monkeypatch.setattr(main_mod, "_build_docker_client", lambda: None)

    # Deterministic GPU inventory: ARM_GPUS is unset under test, so the loader
    # would return [] anyway, but pin it so the `transcode.hw_unavailable` emit
    # branch is stable regardless of any stray env. CI has no GPU, so model that.
    monkeypatch.setattr(main_mod, "load_configured_gpus", lambda _raw: [])

    # Postgres Alembic revisions can't run on SQLite — create the schema from
    # model metadata instead. Same effect for the API surface under test. A
    # throwaway *sync* engine on the same file sidesteps event-loop juggling
    # (TestClient owns the async loop once it starts the lifespan).
    from sqlalchemy import create_engine

    sync_engine = create_engine(f"sqlite:///{db_file}")
    SQLModel.metadata.create_all(sync_engine)
    sync_engine.dispose()
    monkeypatch.setattr(main_mod, "_run_migrations", lambda: None)

    # Keep the log tailer off the real /logs path in CI sandboxes.
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr(main_mod.LogTailer, "__init__", _patched_log_tailer_init(str(log_dir)))

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        async with test_sessionmaker() as session:
            yield session

    main_mod.app.dependency_overrides[db_mod.get_session] = _override_get_session

    try:
        with TestClient(main_mod.app) as client:
            try:
                yield client
            finally:
                # Dispose the async engine on the TestClient's *own* event loop
                # while it's still alive (`client.portal` runs the app lifespan
                # loop that opened these aiosqlite connections). Otherwise the
                # pooled connections' background worker threads outlive the loop
                # and raise "Event loop is closed" at GC, which pytest surfaces
                # as a PytestUnhandledThreadExceptionWarning attributed — by
                # timing, misleadingly — to whatever test is running then.
                client.portal.call(test_engine.dispose)  # type: ignore[attr-defined,union-attr]
    finally:
        main_mod.app.dependency_overrides.clear()
        _restore_column_types(saved_types)


def _patched_log_tailer_init(log_dir: str) -> object:
    from arm_backend.log_tailer import LogTailer

    _orig = LogTailer.__init__

    def __init__(self: object, hub: object, log_dir_arg: str = log_dir) -> None:  # type: ignore[no-untyped-def]
        _orig(self, hub, log_dir)  # type: ignore[arg-type]

    return __init__


ADMIN_NEW_PASSWORD = "e2e-changed-pw"


@pytest.fixture
def admin_token(app_client: object) -> str:
    """Full first-login flow: seeded admin/admin → forced password change →
    re-login. Returns a JWT that clears the `password_must_change` 403 gate,
    so it can authenticate any UI route.

    Exercises the real `POST /api/auth/login` and `POST /api/auth/password`
    paths against the seeded user row.
    """
    first = app_client.post(  # type: ignore[attr-defined]
        "/api/auth/login",
        json={"username": "admin", "password": "admin"},
    )
    assert first.status_code == 200, first.text
    assert first.json()["password_must_change"] is True
    first_token = first.json()["access_token"]

    changed = app_client.post(  # type: ignore[attr-defined]
        "/api/auth/password",
        headers={"Authorization": f"Bearer {first_token}"},
        json={"current_password": "admin", "new_password": ADMIN_NEW_PASSWORD},
    )
    assert changed.status_code == 200, changed.text

    relogin = app_client.post(  # type: ignore[attr-defined]
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_NEW_PASSWORD},
    )
    assert relogin.status_code == 200, relogin.text
    assert relogin.json()["password_must_change"] is False
    return str(relogin.json()["access_token"])
