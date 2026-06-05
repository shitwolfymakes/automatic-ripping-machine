# 08 — v2 Isolation and Cutover Plan

v3 development must not disturb the running v2 codebase. The operating rule is strict and simple:

> **No v3 PR modifies a v2 file. Every v3 artifact is an addition under `v3/`. The only PR that modifies v2 files is the cutover PR, and it does so exactly once.**

This document codifies that rule and describes how the final cutover happens.

## The isolation rule

### What "untouched" means concretely

Every file and directory that exists at the repo root **today** — before v3 development begins — stays byte-identical during v3 development. That includes:

- `arm/` — the v2 Python package.
- `Dockerfile` — v2 single-container image.
- `devtools/` — v2 dev tooling.
- `setup/`, `scripts/` — v2 bootstrap and runit scripts.
- `test/` — v2 ripper unit tests (`test/unittest/test_ripper_*`).
- `arm-dependencies/` — v2 dependency-image submodule (the only entry in `.gitmodules`).
- `arm_wiki/` — wiki content (tracked files at root, not a submodule).
- `setup.cfg`, `requirements.txt`, `CHANGELOG.md`, `README.md`, `VERSION`, `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md` — all root-level files.
- `docs/` — the existing v2 docs tree at root (PSDs, `README-OMDBAPI.md`, `README-TMDBAPI.txt`).
- `.github/workflows/` — v2 CI (`main.yml`, `publish-image.yml`, `publish-wiki.yml`, `shellcheck.yml`, `stale.yml`, `test-pr-image-build.yml`, `version_bump.yml`, `greetings.yml`).
- `.gitignore`, `.pylintrc`, `.codeclimate.yml`, `.codecov.yml`, `.dockerignore`, `favicon.ico` — root-level configs and assets.

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

The v3 subtree currently tracks: `services/`, `packages/`, `docs/` (`arch/ contributors/ ops/ plans/`), `devtools/`, `docker-compose.yml`, `docker-compose.gpu.yml`, `.dockerignore`, `.env.example`, `install.sh`, `pyproject.toml`, `uv.lock`, `.pre-commit-config.yaml`, `README.md`. There is **no** `v3/.gitignore` and **no** `v3/test_fixtures` today — v3 relies on the root `.gitignore`, so there is nothing to merge for those.

```bash
git mv v3/services services
git mv v3/packages packages
git mv v3/install.sh install.sh
git mv v3/pyproject.toml pyproject.toml
git mv v3/uv.lock uv.lock
git mv v3/.pre-commit-config.yaml .pre-commit-config.yaml
git mv v3/docker-compose.gpu.yml docker-compose.gpu.yml
git mv v3/docs/arch docs/arch             # add v3 docs alongside the kept v2 docs/ (PSDs, API-key guides)
git mv v3/docs/contributors docs/contributors
git mv v3/docs/ops docs/ops
git mv v3/docs/plans docs/plans
git mv v3/devtools devtools_v3            # rename to avoid clash until step 2
git mv v3/docker-compose.yml docker-compose.v3.yml  # temp — replaces (absent) root compose in step 3
git mv v3/.dockerignore .dockerignore.v3  # temp — replaces v2 .dockerignore in step 3
git mv v3/.env.example .env.example.v3    # temp
git mv v3/README.md README.v3.md          # temp — replaces v2 README in step 4
```

### 2. Retire v2

```bash
git rm -r arm/
git rm Dockerfile
git rm -r devtools/
git rm -r setup/ scripts/
git rm -r test/
git rm requirements.txt setup.cfg
git rm .pylintrc .codeclimate.yml .codecov.yml .dockerignore favicon.ico
git submodule deinit arm-dependencies && git rm arm-dependencies   # the only entry in .gitmodules
# keep: LICENSE, CODE_OF_CONDUCT.md, SECURITY.md, CONTRIBUTING.md (rewrite), VERSION (bump),
#       docs/ (PSDs + OMDB/TMDB API-key guides — still used by v3; step 1 adds v3 docs alongside),
#       arm_wiki/ (tracked files), .github/ISSUE_TEMPLATE/, .github/dependabot.yml, .github/pull_request_template.md
```

There is **no** root `docker-compose.yml`, no `Dockerfile-UI`/`Dockerfile-Ripper`, no split `requirements_*.txt`, no `temp_*.sh`, and no `sqlite_mcp_server.db` to delete — those existed when this plan was first drafted but have since been removed or consolidated. The current v2 surface is the list above.

### 3. Finalize the v3 files at root

```bash
git mv devtools_v3 devtools
git mv docker-compose.v3.yml docker-compose.yml
git mv .dockerignore.v3 .dockerignore
git mv .env.example.v3 .env.example
# v3 docs were already merged into the kept root docs/ in step 1 — nothing to do here
# root .gitignore already covers v3 artifacts (no separate v3/.gitignore exists), so nothing to merge
```

### 4. Rewrite user-facing docs

- `README.md` — `git mv README.v3.md README.md` to drop the v3 README staged in step 1 over the v2 one (it links to `docs/arch/`).
- `CHANGELOG.md` — add a `v3.0.0` entry describing the rebuild.
- `CONTRIBUTING.md` — replace v2 workflow instructions with v3 (pytest per service, arm_common schema discipline, etc.).
- `VERSION` — `2.23.2` → `3.0.0`.

### 5. Retire v2 CI workflows

```bash
git rm .github/workflows/main.yml \
       .github/workflows/publish-image.yml \
       .github/workflows/publish-wiki.yml \
       .github/workflows/shellcheck.yml \
       .github/workflows/stale.yml \
       .github/workflows/test-pr-image-build.yml \
       .github/workflows/version_bump.yml \
       .github/workflows/greetings.yml
git mv .github/workflows/v3-ci.yml .github/workflows/ci.yml
git mv .github/workflows/v3-release.yml .github/workflows/release.yml
git mv .github/workflows/v3-weekly-rebuild.yml .github/workflows/weekly-rebuild.yml
```

Drop the `v3-` prefix now that these are the only workflows. Re-evaluate `publish-wiki.yml` / `greetings.yml` / `stale.yml` before deleting if v3 still wants those repo-automation behaviors — they are not v2-specific, just currently v2-era.

### 6. Ports — no change

- The UI stays on host `8081` (mapped to container `443`/TLS). `8081` is the canonical port the installer generates and that existing installs already use; v2's `8080` is **not** reclaimed. (The earlier plan to move back to `8080` was dropped — the installed, TLS-secured deployment is the source of truth, and it has always run on `8081`.)

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
