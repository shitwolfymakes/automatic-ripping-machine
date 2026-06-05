# Contributing

Thanks for helping build ARM! This page is the wiki-side summary; the
**authoritative contributor guide is in the repo** at
[`CONTRIBUTING.md`](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/CONTRIBUTING.md).
Start there, and read the architecture docs at
[`docs/arch/README.md`](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/docs/arch/README.md)
to understand the v3 service topology before making changes.

> This is **ARM v3** — a FastAPI backend, a Vue UI, Postgres, a ripper per drive,
> and an ephemeral transcoder. It shares no code with v2 (frozen, no longer developed).
> If you're patching Flask/`arm.yaml`/the v2 monolith, you're in the wrong tree.

## Project layout

The Python side is a [`uv`](https://astral.sh/uv) workspace; the UI is a Vite/Vue
app.

- `packages/arm_common/` — shared Pydantic schemas, enums, SQLModel models.
- `services/backend/` — FastAPI app, Alembic migrations, WS hub, dispatchers.
- `services/ripper/` — per-drive poller + MakeMKV/HandBrake/abcde drivers.
- `services/transcode/` — ephemeral per-job transcoder.
- `services/ui/` — Vue 3 SPA served by nginx.
- `devtools/` — contributor tooling (setup, smoke tests, OpenAPI regen).

## Local development

Prerequisites: `uv`, Docker + the `docker compose` v2 plugin, `openssl`, and
Node/`npm` for the UI. From a checkout:

```bash
bash devtools/setup-dev.sh        # uv sync, generate certs, seed .env (idempotent)
docker compose up -d --build      # build images from your working tree and start
```

The dev compose that `devtools/setup-dev.sh` generates from
`docker-compose.yml.example` (into a gitignored `docker-compose.yml`, one
`arm-ripper-srN` per drive) keeps `build:` blocks (vs the installer's `image:`
references) so you iterate against your own code. The UI comes up at
<https://localhost:8081>.

## Development model: trunk-based

`main` is the trunk and is always releasable. **There is no long-lived `dev`
branch.** Cut a short-lived branch from `main`, keep it focused, rebase often,
and open a PR back into `main`. Releases are semver **tags** on `main`. Full
rules in
[`CONTRIBUTING.md`](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/CONTRIBUTING.md#development-model-trunk-based).

## Tests, lint, and the wire contract

```bash
uv run pytest                       # all backend/ripper/transcode suites; zero infra
uv run pre-commit run --all-files   # ruff, mypy, eslint, prettier, vue-tsc, shellcheck
```

If you change a backend router or an `arm_common` schema that affects the API,
regenerate the OpenAPI artifacts (CI's `openapi-drift` job gates on this) and
commit them:

```bash
bash devtools/regen-openapi-snapshot.sh    # refresh services/ui/openapi.snapshot.json
cd services/ui && npm run openapi-types     # regenerate the TS types
```

Heavier end-to-end drills live in `devtools/` — `iso-smoke.sh` (full
scan → rip → transcode against an ISO fixture, no disc needed) and
`crash-drill.sh` (backend crash recovery).

## Pull requests

- One logical change per PR; open it **against `main`**.
- Rebase before review (the trunk is squash-merged and kept linear).
- CI must pass: ruff format/lint, mypy + `vue-tsc`, the `pytest` suites, and the
  OpenAPI drift check.
- Update affected docs — including this wiki — in the same PR. See
  [Contributing to the Wiki](Contribute-Wiki).

## Reporting bugs

Open an issue with the **service** involved (`backend`/`ripper`/`transcode`/`ui`)
and logs captured at `ARM_LOG_LEVEL=debug` (`docker compose logs <service>`).
Because ARM drives MakeMKV/HandBrake, try the underlying tool by hand to rule out
an upstream problem — see
[`docs/ops/makemkv.md`](https://github.com/automatic-ripping-machine/automatic-ripping-machine/blob/main/docs/ops/makemkv.md).
