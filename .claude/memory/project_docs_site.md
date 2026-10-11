---
name: project_docs_site
description: Where the ARM docs site lives, what it builds, and how it deploys (site/, build/site for Pages, build/app baked into ui-neu's /docs-data)
metadata:
  type: project
---

The docs site is `site/` — a static-site generator (`node src/build.mjs`)
that renders the repo's docs into two outputs from one build. Docs are split
by audience (2026-09-25 reorg): `docs/user/` holds user docs (flat; also the
GitHub wiki source via publish-wiki.yml, with its own `_Sidebar.md`) and
`docs/developers/{architecture,contributing,ui,reference}/` plus the root
`CONTRIBUTING.md` hold developer docs. `site/manifest.json` lists the sections
in nav order; each section's `audience` (user/dev) picks the page id prefix
(`guide/`, `dev/`) and whether the app carries it. Every `docs/user/*.md`
must be placed in the manifest or the build fails.

- `build/site` — the standalone Pages site with every page (relative URLs everywhere, no
  `href="/`/`src="/`; served locally with `npm run serve` at `/arm-v3/` to
  mimic Pages' base path).
- `build/app` — user docs only, as JSON (links to developer docs point at
  the public Pages URL), baked into the ui-neu image at
  `/docs-data/` (see `services/ui-neu/Dockerfile`, `COPY --from=docs
  /repo/site/build/app /usr/share/nginx/html/docs-data`). ui-neu's `/help`
  route (home) and `/help/<section>/<slug>` routes read from `/docs-data/`
  client-side; `/help` itself needs no backend API call.

`npm test` (site/test) fails the build on broken doc links — treat a red
`npm test` in `site/` as a genuine broken-link regression, not flakiness.

Branch `feat/docs-site` sits at the end of the wolfy PR stack, on
`feat/encoder-first-presets` (#87; the stack runs #61..#66, #75, #76, #73,
#74, #81, #83, #84, #85, #87). It needs #74's ui-neu styling system; it was
moved to the end so its migration numbers and doc moves come after the rest
of the stack. Rebase/merge order matters.
