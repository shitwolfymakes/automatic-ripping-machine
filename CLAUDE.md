# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Automatic Ripping Machine **v3** — a greenfield rebuild that now occupies the
whole repository. It is a multi-service system (FastAPI Backend, SvelteKit UI, a
ripper per optical drive, and an ephemeral transcoder) on Postgres, and it
shares nothing with the legacy v2 codebase at the code level. ARM v2 is frozen
and not in this tree; its code remains in the repository's pre-cutover git history.

Start with the architecture docs:

- [docs/developers/architecture/README.md](docs/developers/architecture/README.md) — architecture overview and index.
- [docs/developers/architecture/01-architecture.md](docs/developers/architecture/01-architecture.md) — service topology.
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
- [services/ui-neu/](services/ui-neu/) - SvelteKit (Svelte 5) SPA served by nginx, published as the `arm-ui` image. Its TypeScript API types are generated from the committed OpenAPI snapshot ([services/ui-neu/openapi.snapshot.json](services/ui-neu/openapi.snapshot.json)).
- [services/_common/](services/_common/) — shared container entrypoint (CA-merge + PUID drop + tini exec).
- [deploy/](deploy/) — the production installer: `armctl.sh` (install, up, down, upgrade), `lib/` (shared with `devtools/setup-dev.sh`), `install/` (production-only steps), and `docker-compose.release.yml`. Root `install.sh` is only a bootstrap that downloads a release bundle of this folder.
- [packages/arm_common/](packages/arm_common/) — shared Pydantic schemas, enums, SQLModel models, ULID helper, and structured-logging helpers, imported by every Python service.

### Database

Postgres, via async SQLAlchemy/SQLModel. Schema is managed by Alembic under [services/backend/migrations/](services/backend/migrations/) — generate a new revision for a model change; do not hand-edit existing ones. **Enums are stored as VARCHAR and validated in the app layer at write time — never use Postgres `CREATE TYPE` enums** (see [.claude/memory/](.claude/memory/)).

### Wire contract (OpenAPI)

The UI is generated from the Backend's OpenAPI schema, and CI's `openapi-drift` job fails if they diverge. After changing a Backend router or an `arm_common` schema that affects the API, regenerate both and commit the artifacts:

```bash
bash devtools/regen-openapi-snapshot.sh    # refresh services/ui-neu/openapi.snapshot.json
bash services/ui-neu/scripts/codegen.sh    # regenerate the TypeScript types (api.gen.ts)
```

## Commands

Run from the repo root.

### Dev setup / run

```bash
bash devtools/setup-dev.sh up    # setup (uv sync, certs, .env; idempotent) + build + start; UI at https://localhost:8081
bash devtools/setup-dev.sh down  # stop the stack AND the backend-spawned ripper/transcoder containers
```

Always spin the stack up/down through `setup-dev.sh` — a bare `docker compose
down` strands the backend-spawned per-drive ripper and per-task transcoder
containers (they are not compose services).

### Tests

```bash
uv run pytest                  # all backend / ripper / transcode suites — zero infra
uv run pytest -n auto          # the same suites in parallel (pytest-xdist), as CI runs them
```

Shell suites (zero-infra): `bash devtools/test-setup-dev.sh`, `bash devtools/test-install-walkthrough.sh`, and `bash deploy/tests/test-{armctl,bootstrap,bundle,stack-contract}.sh`.

The suite needs no Docker, Postgres, drives, or network (in-memory fake session + file-backed SQLite). See [docs/developers/architecture/09-testing.md](docs/developers/architecture/09-testing.md) for the two-tier design (fast fake-session unit tests + the real-DB e2e harness under `tests/e2e/`) and the Backend's 100%-statement-coverage policy. Heavier end-to-end drills live in `devtools/`: `bash devtools/iso-smoke.sh` (full scan → rip → transcode against an ISO fixture, no disc) and `bash devtools/crash-drill.sh` (backend crash recovery).

### Lint / format / types

```bash
uv run pre-commit install              # install the git hook once
uv run pre-commit run --all-files      # ruff, mypy, eslint + prettier (ui-neu), shellcheck
cd services/ui-neu/frontend && npm run check && npx vitest run   # UI: svelte-check + tests
cd services/ui-neu/frontend && npm run lint && npm run format    # UI: ESLint + Prettier (format rewrites files)
```

The ui-neu hooks need `npm ci --prefix services/ui-neu/frontend` once (`setup-dev.sh` does it). The bulk Prettier reformat is listed in `.git-blame-ignore-revs`; run `git config blame.ignoreRevsFile .git-blame-ignore-revs` to skip it in `git blame`.

## Development model

Trunk-based: `main` is the trunk and always releasable; short-lived branches merge back via PR; releases are semver **tags** on `main` (built by `release.yml`), and `latest` tracks `main`. There is no long-lived dev branch. See [CONTRIBUTING.md](CONTRIBUTING.md) and [docs/developers/architecture/08-v2-isolation-and-cutover.md](docs/developers/architecture/08-v2-isolation-and-cutover.md).

## Development guidelines

These rules apply to every change in every service. A PR that breaks one is not ready for review.

### Single responsibility

Be ruthless about it. Each module, class, function and component does one thing, and its name says what that thing is. If describing a function takes an "and", split it. Keep I/O, parsing, decisions and side effects in separate functions so each one can be tested alone. New behaviour gets its own function, not another branch in an existing one.

### Cognitive complexity of 15 or less

No function may have a cognitive complexity greater than 15. Confirm it with the **SonarQube for IDE** extension in the local VS Code: rule S3776 (Python and JavaScript/TypeScript, default threshold 15) reports each violation in the Problems panel for the open file. Open every file the diff touches and clear its S3776 warnings before opening the PR. Claude reads the same diagnostics through the VS Code `getDiagnostics` tool.

Bring complexity down by extracting named helpers, returning early, and replacing flag-driven branching with lookup tables or separate functions. Never suppress the rule.

### 100% unit test coverage of touched symbols

Every PR covers 100% of the symbols it adds or changes (functions, methods, classes, components) with unit tests, counting every line and every branch. Covering the changed lines is not enough; a touched symbol is covered in full. Untouched code is out of scope.

Python uses `coverage` (a root dev dependency, branch coverage on). The configured `source` is the Backend only, so name the packages you touched:

```bash
uv run coverage run --source=services/ripper/arm_ripper -m pytest
uv run coverage report --include='services/ripper/arm_ripper/<changed_file>.py'
```

JS/TS uses Vitest's v8 provider (`@vitest/coverage-v8`, configured in [services/ui-neu/frontend/vitest.config.ts](services/ui-neu/frontend/vitest.config.ts)):

```bash
cd services/ui-neu/frontend && npx vitest run --coverage --coverage.include='src/lib/<changed_file>.ts'
```

Any missing line or branch inside a touched symbol fails the rule. Use `# pragma: no cover` or `/* v8 ignore next */` only for code that cannot run, with a comment saying why.

### ui-neu file layout

Under `services/ui-neu/frontend/src/lib`; `npm run lint` enforces module and component file names, not test file names (`unicorn/filename-case`).

1. **Names:** kebab-case for every `.ts`, `.js` and `.svelte.ts` file and every folder (`session-routes.ts`, `handbrake-schema.svelte.ts`, `drive-card/`); Svelte components stay PascalCase (`DataTable.svelte`). In code: camelCase for variables, functions and properties; PascalCase for types, interfaces and components.
2. **Tests:** in a `__tests__/` folder beside the code they test, never a loose sibling `*.test.ts`. `src/lib/__tests__/` holds only tests of modules that sit directly in `src/lib/` and the layout guards; it is not a catch-all. A test file is named after its module (`data-table.test.ts` tests `data-table.ts`; extra suites use a dotted suffix: `data-table.cells.test.ts`). Shared test data lives in `__fixtures__/` (`src/lib/__fixtures__/` when several folders use it).
3. **Logic home:** pure logic lives in `lib/<domain>/` (handbrake, sessions, jobs, drives, ...), Svelte components in `components/<domain>/` (same domain names as `lib/` where both exist), and `lib/utils/` holds only generic helpers with no domain knowledge. Generic UI helpers live in `lib/ui/` (`lib/ui/data-table.ts` for `DataTable.svelte`). Test setup and render helpers live in `lib/testing/`; `features.ts` (app-wide feature flags) is the only module left at the `lib/` root.
4. **Layer folders:** `api/` (HTTP clients), `stores/` (stateful runes and stores), `types/`, `styles/` and `themes/` keep their folders; their files are kebab-case. Stateful `.svelte.ts` rune modules live in `stores/`.
5. **Dependency direction:** `lib/` outside `components/` never imports from `components/` (`no-restricted-imports` enforces it). `components/shared/` holds generic building blocks and components used by two or more domains.
6. **Components:** every component lives in `components/<domain>/`; none sits at the `components/` root. The app shell is in `components/layout/`, shared building blocks in `components/shared/`, and a parent component's child components in a folder nested inside its domain (`components/drives/drive-card/`). `src/lib/__tests__/component-layout.test.ts` enforces the folder list.

## Gotchas / invariants

- **OpenAPI drift gates CI.** Touching Backend routers or `arm_common` schemas without regenerating the snapshot + TS types fails the `openapi-drift` job — see [Wire contract](#wire-contract-openapi).
- **No Postgres native enums.** Store enums as VARCHAR and validate in the app layer; never `CREATE TYPE`.
- **Ripper: one `makemkvcon` per disc, never per title.** A single `makemkvcon mkv … all` invocation rips every title; per-title invocations trigger USB-BD drive autosuspend / SCSI NOT_READY failures between titles.
- **Tests stay zero-infra.** Tier-1 tests fake only the I/O boundary (DB session, docker socket, outbound HTTP, WS hub, clock). Don't pull a real service into the fast suite — un-run tests rot.
- **uv workspace discipline.** Add Python deps to the right member's `pyproject.toml`; `arm_common` is consumed as a workspace package, not vendored.
- **Production runs the dev compose template unchanged.** `docker-compose.yml.example` is shipped as is and layered with `deploy/docker-compose.release.yml`. Never add production-only branches to the template; a new service built from source needs one image line in the release overlay (`deploy/tests/test-stack-contract.sh` fails until it has one).
- **`deploy/lib/` is shared.** A change there changes `setup-dev.sh` and production at once; `devtools/test-setup-dev.sh` pins the dev output text.

The memory entries hold the detail behind several of these — read [.claude/memory/MEMORY.md](.claude/memory/MEMORY.md) at session start.
