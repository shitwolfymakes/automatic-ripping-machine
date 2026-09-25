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
