# ARM docs site

Builds the repo's markdown (`arm_wiki/`, `docs/arch/`, `docs/ops/`,
`CONTRIBUTING.md`, ...; see `manifest.json`) into:

- `build/site/`: the public site deployed to GitHub Pages by
  `.github/workflows/docs-pages.yml`. Relative URLs only.
- `build/app/`: JSON page fragments baked into the ui-neu image at
  `/docs-data/` and rendered by its `/help` route.

Styling comes from ui-neu: `site.css` is compiled from ui-neu's tokens and
blocks, and rendered content uses the ui-neu `docs-prose` block.

    npm ci
    npm test                 # unit tests + a full build of the real tree
    npm run build            # both outputs into build/
    npm run build:app        # app bundle only (the ui-neu Docker stage)
    npm run serve            # build/site at http://localhost:4173/arm-v3/

The build fails on any broken link, missing anchor or missing image, with
`file:line` for each. `ARM_ROOT` overrides the repo root (default `..`);
`ARM_COMMIT` sets the commit shown in the footer (default `git rev-parse`).

In ui-neu, `npm run docs` builds the app bundle into
`frontend/static/docs-data/` so `/help` works under `vite dev`.

## Deploying

`.github/workflows/docs-pages.yml` builds `build/site` and deploys it to
GitHub Pages on every push to `main` (or manually via `workflow_dispatch`).
One-time repo setup, done once per fork:

1. Settings > Pages > Build and deployment > Source: set to "GitHub
   Actions".
2. Settings > Environments > `github-pages` > Deployment branches and
   tags: allow `main` (and add a feature branch such as
   `feat/docs-site` only while testing via `workflow_dispatch`; remove it
   again afterwards).
3. The published site is served at `https://<owner>.github.io/<repo>/`
   (for this fork: https://uprightbass360.github.io/arm-v3/).

`npm run serve` mimics that base path locally at
`http://127.0.0.1:4173/arm-v3/`.
