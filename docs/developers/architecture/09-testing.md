# Testing philosophy

As-built testing architecture for v3, as of 2026-05-16.

This is the single source of truth for testing across v3. It records the
principles, what was actually built for the Backend, and what is planned
but not yet built (the ripper/transcode contract tier and the Big Buck
Bunny integration rig — see [Planned tiers](#planned-tiers-not-yet-built)).
The original design intent lived in
[05-cross-cutting.md](05-cross-cutting.md); that section was retired in
favour of this document once the Backend tiers diverged from it.

## Principles

1. **Tests run with one command, zero infrastructure.** `uv run pytest`
   from the repo root — no Docker, no Postgres, no drives, no network. A
   contributor clones, syncs, and runs the suite in seconds. CI does
   exactly the same thing. The moment the suite needs a sidecar to pass,
   it stops being run.
2. **Coverage is a floor for confidence, not a vanity number.** The
   Backend holds **100% statement coverage**; branch coverage is measured.
   The point isn't the percentage — it's that every line has at least one
   test asserting *something* about it, so a regression has nowhere to
   hide silently. Lines that genuinely can't be exercised in-process are
   excluded *explicitly and with a written reason*, never by lowering the
   bar.
3. **Test the real code path, fake only the boundary.** We don't mock
   `arm_common` types, routers, or business logic. The only things faked
   are true I/O boundaries: the database session, the docker socket,
   outbound HTTP, the WS hub, the filesystem clock. A test that mocks the
   thing it's testing is deleted.
4. **Speed is a feature.** The full Backend suite (600+ tests) runs in
   ~15s. The deliberately-slow bits of production (argon2 work factor) are
   dialled down in tests *without changing the algorithm or code path*.
   Slow tests don't get run; un-run tests rot.
5. **Determinism over fidelity where they conflict.** A test that passes
   or fails based on whether the host has a GPU or a docker socket is
   worse than no test. Environment-dependent startup code is pinned to one
   deterministic path and the other side is covered by a unit test or an
   explicit, justified exclusion.

## Two tiers (Backend, as built)

The plan in 05 was "per-service unit tests against real Postgres" +
"contract tests". The Backend instead settled on two tiers that need no
external services:

### Tier 1 — fast fake-session tests

The bulk of the suite. Each test builds a minimal `FastAPI()` (or calls a
function directly), overrides the `get_session` dependency with an
**in-memory fake `AsyncSession`** (`tests/_fakes.FakeSession`) that
pattern-matches `select(...).where(...)` against rows the test seeded, and
asserts on status codes, response bodies, emitted WS events, and DB
mutations. ~0.3 s per test. This is where exhaustive branch coverage of
routers and pure logic lives.

The fake is a deliberate, owned piece of infrastructure — not a mock
framework. It models the narrow slice of the SQLAlchemy async API the
handlers actually use. When a handler needs a query shape the fake can't
express (e.g. `pg_insert(...).on_conflict_do_update`), that's a signal,
not a workaround: the SQL is Postgres-specific and belongs to the
integration tier, and the handler flow around it is covered with a
tailored per-test fake instead.

### Tier 2 — real-DB e2e harness

`tests/e2e/` boots the **actual `arm_backend.main:app`** — real lifespan,
real seeders, every router mounted, real `require_jwt` loading a real user
row — against a real SQLAlchemy engine on a file-backed **SQLite**
database. This is the only tier that exercises `main.py`, `db.py`,
`seeders.py`, and the wiring the fake-session tier structurally cannot
reach.

SQLite stands in for Postgres because the principle ("zero
infrastructure") outranks dialect fidelity for *API-surface* coverage. The
production models pin `JSONB`/`ARRAY`; the harness swaps them to generic
`JSON` in the shared metadata (snapshot-and-restore, so Tier 1 still sees
the real Postgres types) and creates the schema from model metadata rather
than running the Postgres-flavoured Alembic migrations. The consequence is
explicit and accepted: **migration fidelity and Postgres-only query paths
(`@>` array containment, `ON CONFLICT`) are out of scope for this tier**
and belong to the integration rig in 05.

### Why not real Postgres in CI?

Spinning Postgres in CI was the original Tier 1 design. It was abandoned
for the Backend because it violates principle 1 for the 99% of tests that
don't need real Postgres semantics — every contributor and every CI run
would pay container-startup latency and flakiness to test routing logic
that doesn't care what the database is. The few paths that *do* care
(dialect SQL, migrations) are better served by a separate, explicitly-
scoped integration tier (see [Planned tiers](#planned-tiers-not-yet-built))
than by taxing the whole suite.

## Coverage policy

- **100% statements on the Backend; branch coverage measured.** Config in
  `pyproject.toml [tool.coverage]`, `branch = true`.
- **CI measures, it does not gate.** `coverage run -m pytest` +
  `coverage report` run in the `test-python` job. There is no `fail_under`
  — a deliberate choice (a regression *ratchet* below the achieved level
  is ready to enable when wanted, but a hard gate was explicitly declined
  for now so coverage noise doesn't block unrelated PRs).
- **Exclusions are explicit and justified.** Unreachable-in-process code
  carries `# pragma: no cover` (or `# pragma: no branch` for
  exhaustively-handled enum/union fallthroughs) with a one-line reason on
  the comment *above* the statement. Categories: the real DB session
  (overridden in every test), `main()`'s uvicorn entrypoint, lifespan
  defensive/shutdown-timeout arms, post-seeder impossible states, async
  race guards, and code dead-by-construction (e.g. a fallback for a
  now-mandatory dependency). Protocol/`@overload` `...` stubs are excluded
  globally via `exclude_lines`.
- **Residual partial-branches are documented, not hidden.** A handful of
  branch arrows in the deepest async/race code remain uncovered rather
  than be forced with fragile fault injection. They are listed in the
  project memory, not papered over with a pragma (pragmas are for
  *unreachable* code, not *hard-to-reach* code — the distinction is load-
  bearing).

## What we don't test, and why

- **Real Postgres dialect + Alembic migrations.** Deferred to the
  integration tier ([Planned tiers](#planned-tiers-not-yet-built)). The
  SQLite e2e tier explicitly does not assert these.
- **Cross-service flows over real REST/WS between live containers.** The
  planned contract tier is the intended home; not yet built.
- **Browser e2e (Playwright).** Fragile, low return; the UI is thin and
  reviewed visually + via vitest unit tests.
- **Hardware** — real drives, real GPUs, real MakeMKV/HandBrake against
  arbitrary discs. GPU/docker probing is pinned deterministic; the planned
  Big Buck Bunny loop-device rig is the home for real-pipeline assertions.

## Planned tiers (not yet built)

These were specified in the original design and remain valid; they are not
yet implemented. They are deliberately *separate* from the zero-infra
suite above — they need infrastructure, so they run on demand / in a
dedicated job, never as a tax on `uv run pytest`.

### Contract tier

- The published OpenAPI (from FastAPI) is checked against
  `arm_common.schemas` on every PR — catches "schema changed, generated
  client didn't" before runtime.
- One contract test per ripper/transcoder call: frame a real request, post
  it to a spun-up Backend in test mode, assert shape + status. Catches
  "producer changed, consumer didn't".

This is the intended home for the cross-service REST/WS flows that the
in-process tiers deliberately don't cover.

### Integration rig — Big Buck Bunny

The project lead owns a copy of **Big Buck Bunny** (CC-BY, legally
redistributable); a BBB ISO is the integration fixture:

- A `devtools/arm-test-rip` script mounts the BBB ISO as a loop device in
  a disposable ripper container, lets real MakeMKV (or a loopback
  `dd`-based stub where MakeMKV's container licensing is awkward in CI)
  process it, and asserts the output lands in `/raw/` with correct
  metadata.
- Runs on a developer machine; may be reduced in CI to a recorded fixture
  if MakeMKV licensing is a blocker.
- This is the home for the real-pipeline / real-Postgres-dialect /
  Alembic-migration assertions the SQLite e2e tier explicitly skips.

Arbitrary proprietary discs are never tested — obvious legal reasons.

## Conventions & sharp edges

These cost real debugging time; they are load-bearing, not trivia.

- **The `arm_backend.config` Settings object is a process singleton.**
  `tests/e2e/conftest.py` is imported during collection *before any test
  module*, so its module-level `os.environ.setdefault(...)` wins the
  singleton session-wide. Its values **must match the rest of the suite's
  convention** (`ARM_SERVICE_TOKEN="tok-service"`, a dummy Postgres
  `DATABASE_URL`) or unrelated fake-session tests start 401'ing. New
  shared env defaults go through this lens.
- **Test module basenames must be unique across services.** pytest's
  default prepend import mode with no `tests/` package `__init__.py` means
  two `test_dispatcher.py` files (one in `backend`, one in `ripper`) abort
  *whole-suite* collection with `import file mismatch`. Keep
  `services/*/tests/test_*.py` basenames globally unique.
- **`db._build_engine` mangles `sqlite://` URLs** via a urlparse round-
  trip, so the import-time `DATABASE_URL` stays a dummy Postgres URL and
  the e2e harness swaps the engine object after import.
- **Long inline `# pragma` comments get reflowed by ruff** and the pragma
  ends up on the wrong physical line (coverage then doesn't honour it).
  Keep the inline pragma to the bare `# pragma: no cover`; put the
  justification on the line above.
- **argon2 cost is dialled down in the e2e harness** (the hash self-
  describes its params, so a cheap hasher still round-trips the real
  verifier — cost changes, code path doesn't). ~80s → ~15s.

See also: [05-cross-cutting.md](05-cross-cutting.md) (the other cross-
cutting concerns; testing was consolidated out of it into this document),
[08-v2-isolation-and-cutover.md](08-v2-isolation-and-cutover.md) (why v3
tests were kept under `v3/` during development).
