# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current status: v2.x is frozen, all new work is in `v3/`

**v2.x is no longer being developed.** No new features, no refactors, no consolidation. Existing v2 files at the repo root (`arm/`, `Dockerfile*`, root `docker-compose.yml`, `devtools/`, `setup/`, `scripts/`, `test_ui/`, `test_ripper/`, etc.) stay byte-identical until the v3 cutover PR.

**All new development happens under [v3/](v3/).** The v3 architecture is a greenfield rebuild — different DB (Postgres, not MySQL), different framework (FastAPI, not Flask), different topology (UI / Backend / ripper-per-drive / ephemeral transcoder), different auth, different protocol. It shares nothing with v2 at the code level.

Start here for v3:

- [v3/docs/arch/README.md](v3/docs/arch/README.md) — architecture overview.
- [v3/docs/arch/08-v2-isolation-and-cutover.md](v3/docs/arch/08-v2-isolation-and-cutover.md) — the isolation rule (no v3 PR modifies a v2 file) and the eventual cutover plan.

**The rest of this file describes v2 as it exists today and is retained as reference for anyone spelunking in the legacy code.** None of it applies to work under `v3/` — that subtree has its own compose, its own tooling, and its own docs.

---

## Historical: v2 state (frozen reference)

What follows was written when v2 was still the active line of development. The "v3 in flight" phrasing below refers to an earlier incremental-split plan that has been superseded by the greenfield rebuild under `v3/`. The content is accurate as a description of what is currently in the repo at the root.

### Repository status: v3 in flight, expect mess

This is the **v3.x development branch** (VERSION=`3.0.0_alpha_1`). The README warns it is not production-ready and the codebase is mid-migration from a single all-in-one container to a **Multi-Container Architecture (MCA)** that splits UI, Backend, Ripper, and DB. Treat older docs/comments as unreliable; trust the code.

Migration state you will run into:

- [Dockerfile](Dockerfile) — legacy single-container build (still referenced, but not the v3 target).
- [Dockerfile-UI](Dockerfile-UI) — v3 UI container. Builds on `phusion/baseimage:jammy-1.0.4` directly instead of the old `arm-dependencies` image.
- [Dockerfile-Ripper](Dockerfile-Ripper) — v3 Ripper container (MakeMKV/HandBrake/abcde). Currently **commented out** in [docker-compose.yml](docker-compose.yml#L38-L78) — only `arm-ui` + `arm-db` come up by default.
- A dedicated "Backend" container is planned but does not exist yet; ripper-monitor code in [arm/ripper/monitor/](arm/ripper/monitor/) is the seed of it (writes system status into the DB for the UI to display).
- Files prefixed `temp_` at repo root (`temp_healthcheck.sh`, `temp_install_handbrake.sh`, `temp_install_makemkv.sh`, `temp_install_mkv_hb_deps.sh`, `temp_add-ppa.sh`) are WIP copies the new Dockerfiles `COPY` from. Dockerfiles have `TODO: fix before rolling into prod` markers pointing at eventually moving them back under [scripts/](scripts/). Don't clean these up casually.
- [arm-dependencies/](arm-dependencies/) is a git submodule for the legacy dependency image — v3 containers are moving off it.

### Architecture

**Everything is one Python package tree under [arm/](arm/) that gets mounted into whichever container.** Imports rely on `PYTHONPATH=/opt/arm` (set in Dockerfile-UI) and on `sys.path.append("/opt/arm")` / `sys.path.insert(0, ".../arm")` hacks in [arm/ripper/main/main.py](arm/ripper/main/main.py#L20) and [test_ui/conftest.py](test_ui/conftest.py#L9). If you move files or rename packages you will break imports silently.

Layout:

- [arm/ui/](arm/ui/) — Flask app served by Waitress ([arm/runui.py](arm/runui.py)). Blueprints registered in [arm/ui/ui_blueprints.py](arm/ui/ui_blueprints.py): `main`, `errors`, `settings`, `logs`, `auth`, `database`, `history`, `jobs`, `sendmovies`, `notifications`. App factory is [arm/ui/__init__.py](arm/ui/__init__.py).
- [arm/ripper/main/](arm/ripper/main/) — the actual ripping pipeline. Entry is [main.py](arm/ripper/main/main.py), invoked per-disc by udev (one process per disc insertion). Dispatches to `arm_ripper.rip_visual_media` (DVD/Blu-ray), `utils.rip_music` (CD), or `utils.rip_data` (data disc) based on `identify.identify(job)`.
- [arm/ripper/monitor/](arm/ripper/monitor/) — long-running sidecar that writes ripper container status into the DB so the UI can show it.
- [arm/models/](arm/models/) — shared SQLAlchemy models (`Job`, `Config`, `Track`, `User`, `UISettings`, `SystemDrives`, `SystemInfo`, `Notifications`, `AlembicVersion`). `db` is a single `SQLAlchemy()` instance in [db_setup.py](arm/models/db_setup.py) that both UI and ripper import.
- [arm/common/](arm/common/) — shared helpers used by both UI and ripper (`database_manager`, `server_ip`, `ServerDetails`).
- [arm/config/config.py](arm/config/config.py) — loads `/arm/config/arm.yaml` at import time and migrates it against [setup/arm.yaml](setup/arm.yaml) if keys diverge. `import arm.config.config as cfg; cfg.arm_config[...]` is the pattern used everywhere.
- [arm/ui_config.py](arm/ui_config.py) — Flask config classes `Development` / `Testing` / `Production` selected by `FLASK_ENV`. Docker overrides `SERVER_HOST` to `0.0.0.0`, port to `8080`, and MySQL credentials come from env vars (`MYSQL_IP`, `MYSQL_USER`, `MYSQL_PASSWORD`). `Testing` swaps `MYSQL_DATABASE` to `arm_testing`.

Runtime flow inside a container (phusion baseimage pattern):
- [scripts/docker/runit/arm_setup_ui.sh](scripts/docker/runit/arm_setup_ui.sh) runs first (remaps arm user UID/GID, seeds `/arm/config/arm.yaml` + `apprise.yaml` from `setup/`).
- [scripts/docker/runsv/armui.sh](scripts/docker/runsv/armui.sh) is the `runit` service that `exec`s `arm/runui.py` as user `arm`.
- On first boot the app factory sleeps 60s to wait for MySQL, then `alembic upgrade head` against [arm/ui/migrations/](arm/ui/migrations/), then [ui_initialise.py](arm/ui/ui_initialise.py) seeds a default **admin/password** user and default `UISettings` if the tables are empty.

### Database

MySQL 8.3 only in v3 (SQLite config still lingers in `SQLALCHEMY_BINDS` but is no longer the primary). Schema is managed by Alembic at [arm/ui/migrations/](arm/ui/migrations/versions/) — migrations run automatically on UI startup via `flask_migrate.upgrade`. When adding a model change, generate a new revision here; do not hand-edit existing ones.

Two logical DBs on the same MySQL container config:
- `arm` — production (persistent volume).
- `arm_testing` — tests (tmpfs, wiped on restart). Service `arm-db-test` is commented-out in compose by default; the `-test_ui` devtool starts/stops it around the pytest run. They share port 3306, so only one at a time.

### Commands

Everything assumes you are at the repo root.

#### Dev rebuild / run

```bash
# Full rebuild + start (uses docker compose in detached mode)
./devtools/armdevtools.py -dc

# Same, but stream logs to the console (useful for debugging startup)
./devtools/armdevtools.py -dc --monitor

# Manual equivalents
docker compose build
docker compose up -d      # or: docker compose up    (foreground)
docker compose stop
```

UI is exposed at `http://localhost:8080` (login: `admin` / `password` on a fresh DB).

#### Lint

```bash
# devtools wrapper (flake8 against the whole repo)
./devtools/armdevtools.py -qa

# CI-equivalent call (from .github/workflows/main.yml)
flake8 . --max-complexity=15 --max-line-length=120 --show-source --statistics
```

Note: [setup.cfg](setup.cfg) sets `max-line-length=160` for local runs, but CI enforces **120**. If you rely on `-qa`, you may still fail CI — lint with `--max-line-length=120` before pushing.

#### Tests

`test_ui/` runs against a live MySQL; it is not self-contained. [test_ui/conftest.py](test_ui/conftest.py) calls `create_app('testing')`, which hard-requires `MYSQL_DATABASE == "arm_testing"` or exits. Use the devtool wrapper — it stops `arm-db`, starts `arm-db-test`, runs pytest, and restores state:

```bash
./devtools/armdevtools.py -test_ui
```

Manual equivalent (if you have a venv at `.venv/`):

```bash
docker compose stop arm-db
docker compose start arm-db-test
.venv/bin/python -m pytest test_ui --maxfail=1 -v
docker compose stop arm-db-test
docker compose start arm-db
```

Run a single test:

```bash
.venv/bin/python -m pytest test_ui/test_model_job.py -v
.venv/bin/python -m pytest test_ui/test_model_job.py::TestJob::test_something -v
```

`test_ripper/` also exists but is minimal (`ARMInfo`, `ProcessHandler`) and has no fixtures — run directly with pytest.

#### Pre-PR check

```bash
./devtools/armdevtools.py -pr
```

### Gotchas

- **Default credentials are seeded on every fresh DB.** If you blow away the DB volume, `admin` / `password` comes back. Don't assume existing admin state.
- **Container import paths are hard-coded**: [arm/common/database_manager.py](arm/common/database_manager.py#L17) uses the literal `/opt/arm/arm/ui/migrations`; alembic config in [ui_config.py](arm/ui_config.py#L158) does the same. These break on non-Docker runs unless `/opt/arm` symlinks exist.
- **Ripper entry is a per-disc process**, not a long-running service. udev triggers it via [scripts/docker/custom_udev](scripts/docker/custom_udev) + [setup/51-docker-arm.rules](setup/51-docker-arm.rules). The long-running piece in the ripper container is just the monitor.
- **docker-compose.yml has `arm-db` mapped to `/arm/db/mysql` on the host** with `user: 1000:1000`. Running the compose file without that host path prepared (and owned 1000:1000) will fail silently on first start.
- The `Dockerfile` (legacy, all-in-one) and the two split Dockerfiles coexist. Don't "consolidate" without confirming which path the current work targets.
