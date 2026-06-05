# Contributing Guide

Thank you for contributing to the Automatic Ripping Machine.

This is **ARM v3** — a greenfield rebuild (FastAPI backend, Vue UI, Postgres, a
ripper-per-drive and an ephemeral transcoder). The architecture is documented
under [docs/arch/](docs/arch/); start at [docs/arch/README.md](docs/arch/README.md).
ARM v2 is frozen — no new work targets it. Its code remains in the
repository's pre-cutover git history.

## Reporting issues, bugs, and feature requests

Open an issue on GitHub. For a bug report, please include:

- **Which service** is involved (`backend`, `ripper`, `transcode`, or `ui`).
- **Logs.** Grab them with `docker compose logs <service>`; set
  `ARM_LOG_LEVEL=debug` for a clean, detailed log and reproduce before
  attaching. You can drag-and-drop a log file onto an issue comment.
- Because ARM drives external tools (MakeMKV, HandBrake), try the underlying
  tool by hand to rule out an upstream problem — see
  [docs/ops/makemkv.md](docs/ops/makemkv.md).

When filing a bug, enhancement, or feature request, please say whether you are
able/willing to make the change yourself in a pull request.

## Development model: trunk-based

ARM v3 uses **trunk-based development**. There is **no long-lived `develop` or
`dev` branch** — `main` is the trunk and the single source of truth, kept
always-releasable.

- **Branch short, merge fast.** Cut a short-lived branch from `main`, keep it
  small and focused, rebase on `main` often, and merge it back via PR. Long-running
  branches accumulate drift; avoid them.
- **Releases are tags, not branches.** A semver tag on `main` (`v3.1.0`) triggers
  the release workflow to build the matching versioned image; `latest` tracks the
  tip of `main`. Cutting a release never means promoting work through a parallel
  branch.
- **Backports are on-demand and temporary.** If an already-released version needs
  a fix while `main` has moved ahead, cut a short-lived `release/3.0.x` branch from
  that tag, land the fix, tag it, and delete the branch. Don't maintain a permanent
  release line.
- **v2 is closed.** It lives in the pre-cutover git history; nothing new branches off it.

## Pull requests

- Fork the repo (or push a branch) and open the PR **against `main`**. See
  <https://help.github.com/articles/creating-a-pull-request/>.
- **One logical change per PR.** Independent changes get separate PRs so they can
  be reviewed and merged individually. Trivial or mutually-dependent changes may
  share a PR.
- **Rebase before review** so your branch is current with `main`; we squash-merge
  to keep the trunk linear.
- **CI must pass** (`.github/workflows/ci.yml`): ruff format/lint, mypy and
  `vue-tsc` type checks, the per-service `pytest` suites, and the OpenAPI
  drift check.
- Update affected docs / `README.md` in the same PR.

## Local development

Prerequisites: [`uv`](https://astral.sh/uv), Docker with the `docker compose`
v2 plugin, `openssl`, and Node/`npm` (for the UI).

```bash
bash devtools/setup-dev.sh     # one-shot, idempotent dev-env setup
docker compose up -d           # bring up the stack
```

The UI is served at <https://localhost:8081>.

## Tests

The Python suites run with **one command and zero infrastructure** — no Docker,
Postgres, drives, or network:

```bash
uv run pytest                  # all backend / ripper / transcode suites
```

See [docs/arch/09-testing.md](docs/arch/09-testing.md) for the two-tier design
(fast fake-session unit tests + the real-DB e2e harness) and the coverage policy.

Heavier end-to-end drills live in `devtools/`:

- `bash devtools/iso-smoke.sh` — full scan → identify → rip → transcode against an
  ISO fixture (no physical disc required).
- `bash devtools/crash-drill.sh` — backend crash-recovery drill.

## Linting, formatting, and types

Style and type checks run through `pre-commit`:

```bash
uv run pre-commit install              # install the git hook once
uv run pre-commit run --all-files      # run everything manually
```

Hooks: `ruff-format` + `ruff` and `mypy` on Python; ESLint, Prettier and
`vue-tsc` on the UI; `shellcheck` on shell scripts. Line length is **120**.

## Wire contract (OpenAPI)

The UI is generated from the backend's OpenAPI schema, and CI's `openapi-drift`
job fails if they diverge. If you change a backend router or an `arm_common`
schema that affects the API:

```bash
bash devtools/regen-openapi-snapshot.sh   # refresh services/ui/openapi.snapshot.json
cd services/ui && npm run openapi-types    # regenerate the TypeScript types
```

Commit both regenerated artifacts with your change.

## Hardware/OS documentation

Many contributors run ARM in environments other than the reference setup. If you
have ARM working somewhere new and want to help others, please submit a how-to to
the [wiki](https://github.com/automatic-ripping-machine/automatic-ripping-machine/wiki).

## Testing and quality

If you are interested in helping out with testing, quality, or release
engineering, please let us know.
