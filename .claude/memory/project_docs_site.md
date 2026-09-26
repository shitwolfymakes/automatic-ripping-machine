---
name: project_docs_site
description: Where the ARM docs site lives, what it builds, and how it deploys (site/, build/site for Pages, build/app baked into ui-neu's /docs-data)
metadata:
  type: project
---

The docs site is `site/` — a static-site generator (`node src/build.mjs`)
that renders `arm_wiki/*.md` and `docs/arch/*.md` into two outputs from one
build:

- `build/site` — the standalone Pages site (relative URLs everywhere, no
  `href="/`/`src="/`; served locally with `npm run serve` at `/arm-v3/` to
  mimic Pages' base path).
- `build/app` — the same content as JSON, baked into the ui-neu image at
  `/docs-data/` (see `services/ui-neu/Dockerfile`, `COPY --from=docs
  /repo/site/build/app /usr/share/nginx/html/docs-data`). ui-neu's `/help`
  route (home) and `/help/<section>/<slug>` routes read from `/docs-data/`
  client-side; `/help` itself needs no backend API call.

`npm test` (site/test) fails the build on broken doc links — treat a red
`npm test` in `site/` as a genuine broken-link regression, not flakiness.

Branch `feat/docs-site` is stacked on `chore/ui-neu-css-cleanup` (wolfy PR
#74) — rebase/merge order matters; don't land `feat/docs-site` without that
base.
