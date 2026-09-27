# ARM docs site

Builds the repo's markdown into:

- `build/site/`: the public site deployed to GitHub Pages by
  `.github/workflows/docs-pages.yml`. Every page, relative URLs only.
- `build/app/`: JSON page fragments baked into the ui-neu image at
  `/docs-data/` and rendered by its `/help` route. User docs only; links
  from them to developer docs point at the public site.

The docs live in two trees:

- `docs/user/`: user docs (also the GitHub wiki source, flat, with its own
  `_Sidebar.md`). Every page here must be placed in `manifest.json` or the
  build fails.
- `docs/developers/`: `architecture/`, `contributing/`, `ui/` and
  `reference/`, plus the root `CONTRIBUTING.md`. Site only.

`manifest.json` lists the sections in nav order. A section's `audience`
(`user` or `dev`) sets its page ids (`guide/...` or `dev/...`) and whether
the app carries it. Group `files` take a path or glob, a
`{ "file", "label", "slug" }` object to override the nav label or URL slug,
or a `{ "label", "link" }` nav link.

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
