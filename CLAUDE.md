# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Automatic Ripping Machine **v3** — a greenfield rebuild that now occupies the
whole repository. It is a multi-service system (FastAPI Backend, Vue UI, a
ripper per optical drive, and an ephemeral transcoder) on Postgres, and it
shares nothing with the legacy v2 codebase at the code level. ARM v2 is frozen
and not in this tree; its code remains in the repository's pre-cutover git history.

Start with the architecture docs:

- [docs/arch/README.md](docs/arch/README.md) — architecture overview and index.
- [docs/arch/01-architecture.md](docs/arch/01-architecture.md) — service topology.
- [docs/plans/MASTER_IMPLEMENTATION_PLAN.md](docs/plans/MASTER_IMPLEMENTATION_PLAN.md) — per-phase rollout.

## Project memory (read this at session start)

Claude-specific memory for this repo is tracked in source control at [.claude/memory/](.claude/memory/). This is authoritative for this project and overrides the default guidance in `~/.claude/CLAUDE.md` that points at `~/.claude/projects/<slug>/memory/` — the per-user path is not used here, so every device and every teammate sees the same memory.

At the start of every session touching this repo, `Read` [.claude/memory/MEMORY.md](.claude/memory/MEMORY.md) — it's a short index (one line per entry). Read individual entries on demand when their hook is relevant to the task at hand.

When saving a new memory, write the file into `.claude/memory/` and update `MEMORY.md` there; commit both alongside the related code change.

## Architecture

The Python side is a **uv workspace** ([pyproject.toml](pyproject.toml) `[tool.uv.workspace]`): `packages/arm_common` plus the three Python services are members, and `arm_common` is wired in as a workspace source. Python 3.14; ruff line-length 120.

Layout:

- [services/backend/](services/backend/) — FastAPI app (`arm_backend`), Alembic migrations ([services/backend/migrations/](services/backend/migrations/)), the WebSocket hub, and dispatchers (transcode, notification, log-tail). JWT + service-token auth.
- [services/ripper/](services/ripper/) — per-drive poller + Backend client + makemkv/HandBrake/abcde drivers (`arm_ripper`). One ripper service per optical drive.
- [services/transcode/](services/transcode/) — ephemeral, per-task transcoder spawned by the Backend (`arm_transcode`).
- [services/ui/](services/ui/) — Vue 3 SPA served by nginx. Its TypeScript API types are generated from the Backend's OpenAPI schema.
- [services/_common/](services/_common/) — shared container entrypoint (CA-merge + PUID drop + tini exec).
- [packages/arm_common/](packages/arm_common/) — shared Pydantic schemas, enums, SQLModel models, ULID helper, and structured-logging helpers, imported by every Python service.

### Database

Postgres, via async SQLAlchemy/SQLModel. Schema is managed by Alembic under [services/backend/migrations/](services/backend/migrations/) — generate a new revision for a model change; do not hand-edit existing ones. **Enums are stored as VARCHAR and validated in the app layer at write time — never use Postgres `CREATE TYPE` enums** (see [.claude/memory/](.claude/memory/)).

### Wire contract (OpenAPI)

The UI is generated from the Backend's OpenAPI schema, and CI's `openapi-drift` job fails if they diverge. After changing a Backend router or an `arm_common` schema that affects the API, regenerate both and commit the artifacts:

```bash
bash devtools/regen-openapi-snapshot.sh    # refresh services/ui/openapi.snapshot.json
cd services/ui && npm run openapi-types     # regenerate the TypeScript types
```

## Commands

Run from the repo root.

### Dev setup / run

```bash
bash devtools/setup-dev.sh     # uv sync, certs, .env (idempotent)
docker compose up -d           # bring up the stack; UI at https://localhost:8081
```

### Tests

```bash
uv run pytest                  # all backend / ripper / transcode suites — zero infra
```

The suite needs no Docker, Postgres, drives, or network (in-memory fake session + file-backed SQLite). See [docs/arch/09-testing.md](docs/arch/09-testing.md) for the two-tier design (fast fake-session unit tests + the real-DB e2e harness under `tests/e2e/`) and the Backend's 100%-statement-coverage policy. Heavier end-to-end drills live in `devtools/`: `bash devtools/iso-smoke.sh` (full scan → rip → transcode against an ISO fixture, no disc) and `bash devtools/crash-drill.sh` (backend crash recovery).

### Lint / format / types

```bash
uv run pre-commit install              # install the git hook once
uv run pre-commit run --all-files      # ruff, mypy, eslint, prettier, vue-tsc, shellcheck
```

## Development model

Trunk-based: `main` is the trunk and always releasable; short-lived branches merge back via PR; releases are semver **tags** on `main` (built by `release.yml`), and `latest` tracks `main`. There is no long-lived dev branch. See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/arch/08-v2-isolation-and-cutover.md](docs/arch/08-v2-isolation-and-cutover.md).

## Gotchas / invariants

- **OpenAPI drift gates CI.** Touching Backend routers or `arm_common` schemas without regenerating the snapshot + TS types fails the `openapi-drift` job — see [Wire contract](#wire-contract-openapi).
- **No Postgres native enums.** Store enums as VARCHAR and validate in the app layer; never `CREATE TYPE`.
- **Ripper: one `makemkvcon` per disc, never per title.** A single `makemkvcon mkv … all` invocation rips every title; per-title invocations trigger USB-BD drive autosuspend / SCSI NOT_READY failures between titles.
- **Tests stay zero-infra.** Tier-1 tests fake only the I/O boundary (DB session, docker socket, outbound HTTP, WS hub, clock). Don't pull a real service into the fast suite — un-run tests rot.
- **uv workspace discipline.** Add Python deps to the right member's `pyproject.toml`; `arm_common` is consumed as a workspace package, not vendored.

The memory entries hold the detail behind several of these — read [.claude/memory/MEMORY.md](.claude/memory/MEMORY.md) at session start.
