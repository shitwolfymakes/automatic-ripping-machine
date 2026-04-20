# 08 — v2 Isolation and Cutover Plan

v3 development must not disturb the running v2 codebase. The operating rule is strict and simple:

> **No v3 PR modifies a v2 file. Every v3 artifact is an addition under `v3/`. The only PR that modifies v2 files is the cutover PR, and it does so exactly once.**

This document codifies that rule and describes how the final cutover happens.

## The isolation rule

### What "untouched" means concretely

Every file and directory that exists at the repo root **today** — before v3 development begins — stays byte-identical during v3 development. That includes:

- `arm/` — the v2 Python package.
- `Dockerfile`, `Dockerfile-UI`, `Dockerfile-Ripper` — v2 images.
- `docker-compose.yml` at the repo root — v2 compose.
- `devtools/` — v2 dev tooling.
- `setup/`, `scripts/` — v2 bootstrap and runit scripts.
- `test_ui/`, `test_ripper/`, `test_fixtures/` (if present) — v2 tests.
- `arm-dependencies/`, `arm_wiki/` — v2 submodules.
- `setup.cfg`, `requirements_*.txt`, `CHANGELOG.md`, `README.md`, `VERSION`, `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md` — all root-level files.
- `docs/` — the existing docs tree at root (not including our new `v3/docs/arch/`).
- `.github/` workflow files — v2 CI.
- `.gitignore`, `.flake8`, any linter config.

If any of these needs to change for v3, the change happens in the cutover PR, not earlier.

### What may be added at root

There is **one** permitted modification at root during v3 development: appending to `.gitignore`. v3 produces untracked artifacts (`.env`, built SPA assets, Python venv, etc.) that must be ignored. We handle this additively:

- v3's own gitignore rules live in `v3/.gitignore`. Git respects nested `.gitignore` files.
- No edit to root `.gitignore` is required if rules are scoped to `v3/**`.

If a rule can only live at root (e.g. a global editor artifact suppression), we document why in the PR and treat it as the single allowed root-file edit.

### What happens inside `v3/`

Anything. v3 is a greenfield project within its own subtree. It has its own:

- Code (`services/`, `packages/`).
- Compose (`v3/docker-compose.yml`).
- Tooling (`v3/devtools/`).
- Tests (`v3/services/*/tests/`, `v3/test_fixtures/`).
- Docs (`v3/docs/arch/` — you are here).
- Git ignore (`v3/.gitignore`).
- CI (`v3/.github/workflows/` — actually lives at `.github/workflows/v3-*.yml` since GitHub only looks at root-level `.github/`; see "CI" below).

## Co-existence

During development, v2 and v3 run side by side on the same host. They cannot collide because every resource is namespaced.

| Resource | v2 | v3 |
|---|---|---|
| Compose project name | `arm` (default from root dir) | `armv3` (explicit in `v3/docker-compose.yml`) |
| Container name prefix | `arm-*` | `armv3-*` |
| Volume name prefix | `arm_*` | `armv3_*` |
| Host port (UI) | 8080 | 8081 |
| Host port (DB, if exposed) | 3306 (MySQL) | 5432 (Postgres) — different anyway |
| Host path (DB data) | `/arm/db/mysql` | `~/arm/db/` by default (see [06-deployment.md § Install prefix and layout](06-deployment.md#install-prefix-and-layout)) |
| Default user | `1000:1000` | `1000:1000` (same host user is fine; paths are distinct) |

The only shared resource is the **physical optical drive** (`/dev/sr0`). Both v2 and v3 compose files map it, but only one should be actively listening at a time. Stop v2's ripper service (or the whole v2 stack) before exercising v3 rips.

### Running both

```bash
# v2 (unchanged workflow):
docker compose up -d          # from repo root

# v3 (new workflow):
docker compose -f v3/docker-compose.yml up -d

# Inspect what's running under each:
docker compose ls             # shows "arm" and "armv3" as separate projects

# Tear down only v3:
docker compose -f v3/docker-compose.yml down

# Tear down only v2:
docker compose down
```

### Switching active stack

To run a real rip on v3 without conflict:

```bash
docker compose stop arm-ripper   # v2 releases the drive
docker compose -f v3/docker-compose.yml up -d
```

To go back:

```bash
docker compose -f v3/docker-compose.yml down
docker compose start arm-ripper
```

## CI

GitHub Actions only reads `.github/workflows/` at the repo root — subdirectory workflows are ignored. We cannot put v3 CI under `v3/.github/`. The compromise:

- v2's existing workflow files in `.github/workflows/` stay untouched.
- v3 adds new workflow files named `.github/workflows/v3-*.yml`. The filename prefix makes their ownership obvious at a glance.
- Adding files under `.github/workflows/` is NOT a modification of an existing file, so it does not violate the isolation rule.
- Every v3 workflow scopes its `paths:` filter to `v3/**` so it only fires on v3 changes. v2 workflows keep their existing path filters.

This is the **one exception** to the "all v3 lives under `v3/`" rule — pure addition inside `.github/workflows/`, zero edits to v2 workflow files.

## Branching

v3 development runs on a long-lived branch: `v3/main`. Feature branches target `v3/main`. PRs merge into `v3/main`.

The repo's default branch (`main`) keeps receiving v2 bug fixes if any are made. It does NOT receive v3 changes until cutover.

At cutover, a single PR merges `v3/main` → `main`. That PR contains both the additive v3 content (already on `v3/main`) and the v2-retirement diffs (moving `v3/*` up, deleting v2 files) staged in the same commit.

## The cutover PR

Exactly one PR modifies v2 files. Its contents:

### 1. Move v3 contents to root

```
git mv v3/services services
git mv v3/packages packages
git mv v3/test_fixtures test_fixtures    # if not already at root
git mv v3/docs/arch docs/arch            # or keep under docs/arch/ if already there
git mv v3/devtools devtools_v3           # rename to avoid clash until step 2
git mv v3/docker-compose.yml docker-compose.v3.yml  # temp
git mv v3/.gitignore .gitignore.v3       # temp
git mv v3/.env.example .env.example.v3   # temp
```

### 2. Retire v2

```
git rm -r arm/
git rm Dockerfile Dockerfile-UI Dockerfile-Ripper
git rm docker-compose.yml
git rm -r devtools/
git rm -r setup/ scripts/
git rm -r test_ui/ test_ripper/
git rm requirements_ui.txt requirements_ripper.txt setup.cfg
git rm temp_*.sh
git rm sqlite_mcp_server.db
git submodule deinit arm-dependencies && git rm arm-dependencies
# keep: LICENSE, CODE_OF_CONDUCT.md, SECURITY.md, CONTRIBUTING.md (rewrite), arm_wiki/ submodule
```

### 3. Finalize the v3 files at root

```
git mv devtools_v3 devtools
git mv docker-compose.v3.yml docker-compose.yml
# merge .gitignore.v3 → .gitignore (concatenate, dedupe)
# merge .env.example.v3 → .env.example
```

### 4. Rewrite user-facing docs

- `README.md` — replace v2 content with v3 content (links to `docs/arch/`).
- `CHANGELOG.md` — add a `v3.0.0` entry describing the rebuild.
- `CONTRIBUTING.md` — replace v2 workflow instructions with v3 (pytest per service, arm_common schema discipline, etc.).
- `VERSION` — `3.0.0`.

### 5. Retire v2 CI workflows

- `git rm .github/workflows/<v2-workflows>.yml`.
- Rename `.github/workflows/v3-*.yml` → `.github/workflows/*.yml` (drop the prefix now that they are the only workflows).

### 6. Update ports

- v3 UI moves from host `8081` back to `8080` in the new root `docker-compose.yml`.

### 7. Tag v2

Before merging the cutover PR, tag the current `main` so v2 is reachable forever:

```bash
git tag -a v2-final main -m "Final v2 release before v3 replaces main"
git push origin v2-final
```

Users who want to stay on v2 pin their image to this tag. No existing v2 install is disrupted by the cutover because the cutover ships new image tags under `v3.x`.

## What the cutover is NOT

- It is not a data migration. v2 users pick v3 by opting into a new database and re-ripping if they want (or keep running v2 off the pinned tag).
- It is not a branch rename. `main` stays `main`; its content just pivots from v2 to v3.
- It is not a soft migration. v2 is removed from `main` in one PR. The `v2-final` tag is the preservation mechanism.

## Readiness criteria for cutover

We run the cutover PR only after v3 meets all of these:

- All architecture decisions in this directory are either resolved or explicitly deferred with a known plug-in point (OQs from [07-open-questions.md](07-open-questions.md)).
- A fresh-host install of v3 (via the install-script one-liner — see [06-deployment.md § Install](06-deployment.md#install)) lands at the login screen, accepts a disc, and produces a transcoded file using the Big Buck Bunny ISO fixture.
- Crash-recovery exercise passes: five queued rips + simulated power cut mid-batch resumes cleanly without manual intervention.
- At least one real Blu-ray, DVD, and audio CD rip have completed end-to-end on a contributor's machine.
- `.github/workflows/v3-*.yml` CI passes on every targeted platform in the supported matrix.
- Maintainers have agreed that v3 is ready to replace v2.

Until all of those are true, `main` continues to ship v2 and v3 continues to develop on `v3/main` — exactly as the isolation rule requires.
