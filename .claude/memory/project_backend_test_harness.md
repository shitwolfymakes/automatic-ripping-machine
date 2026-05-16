---
name: project_backend_test_harness
description: How v3 backend tests are structured — fake-session vs real-DB e2e harness, and the env/argon2/collision gotchas
metadata:
  type: project
---

The v3 backend has **two** test tiers under `v3/services/backend/tests/`:

1. **Fake-session per-router tests** (`test_*_router.py`, ~0.3s each): build a
   one-router `FastAPI()`, override `get_session` with `tests._fakes.FakeSession`
   (an in-memory AST-matching fake `AsyncSession`). Use this for exhaustive
   router branch coverage — it's the fast path and the bulk of the suite.
2. **Real-DB e2e harness** (`tests/e2e/`, ~3s/test): `conftest.py`'s `app_client`
   fixture boots the *actual* `arm_backend.main:app` (full lifespan, seeders,
   every router) against file-backed SQLite. Use this only for paths the
   fake-session approach structurally can't reach: `main.py` wiring/lifespan,
   `db.py`, `seeders.py`, real `require_jwt` user loading.

Goal: drive backend coverage toward 100%. Coverage is measured in CI
(`coverage run -m pytest` + `coverage report`) but **not gated** yet — no
`fail_under` in `v3/pyproject.toml` `[tool.coverage]`; ratchet it up later.

**Non-obvious gotchas (cost real debugging time):**

- `e2e/conftest.py` is imported during collection **before any test module**,
  so its module-level `os.environ.setdefault` wins the `arm_backend.config`
  Settings singleton session-wide. Its values **must match the rest of the
  suite's convention** (`ARM_SERVICE_TOKEN="tok-service"`, dummy Postgres
  `DATABASE_URL`) or unrelated fake-session tests start 401'ing.
- Models pin Postgres-only `JSONB`/`ARRAY`. The harness swaps them to generic
  `JSON` in the shared `SQLModel.metadata` and **snapshots+restores** them per
  fixture, because that metadata is process-global and the fake-session tests
  assert against the real Postgres types.
- `db._build_engine` runs at import and its urlparse round-trip **can't parse a
  `sqlite+aiosqlite://` URL** — keep the import-time `DATABASE_URL` a dummy
  Postgres URL and swap `db.engine`/`SessionLocal` (+ `main.SessionLocal`,
  captured by name) inside the fixture.
- Argon2 default cost is ~0.5s/op; the harness patches a low-cost hasher into
  `routers.auth._hasher` and `seeders.PasswordHasher` (80s→23s). Self-describing
  hash params mean the cheap hasher still round-trips the real verifier.
- Seeded admin is `password_must_change=True`; the `admin_token` fixture runs
  the real login→change-password→re-login flow to clear the per-route 403 gate.

**Pre-existing infra blocker (not from the harness):** duplicate
`test_dispatcher.py` basename in `services/backend/tests/` and
`services/ripper/tests/` aborts a whole-suite `pytest` collection under
default prepend import mode (`import file mismatch`). Backend-only runs are
green; the v3 `test-python` CI job is affected independent of coverage work.
See [[feedback_db_enums_as_varchar]] for why models avoid PG enums (helps
SQLite create_all).
