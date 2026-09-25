# ARM documentation site - design

Date: 2026-09-25
Branch: `feat/docs-site`, stacked on `chore/ui-neu-css-cleanup` (wolfy PR #74,
the ui-neu tokens/blocks styling system)
Status: approved design, awaiting implementation plan

## Problem

ARM v3's user documentation lives in `arm_wiki/` (synced to the GitHub wiki)
and its developer documentation is scattered across `docs/arch/`, `docs/ops/`,
`docs/dev-setup.md` and `CONTRIBUTING.md`. There is no single browsable,
searchable site; the wiki is online-only, unversioned relative to the
installed release, and looks nothing like the app. The ui-neu frontend has a
design system (tokens, blocks, 25 colour schemes; PR #74) that the docs do
not share.

## Goals

1. Documentation built **from the repo's own markdown** - no duplicated
   content, no separate docs repo.
2. A public site **deployed to GitHub Pages** from `uprightbass360/arm-v3` by
   a workflow in this repo (`https://uprightbass360.github.io/arm-v3/`).
3. **Styled from ui-neu**: the site consumes ui-neu's real `tokens.css` and
   block stylesheets at build time, and the stylesheet for rendered doc
   content is a ui-neu block, shared by both hosts.
4. **Included in the app, versioned with it**: the ui-neu image carries the
   docs built from the same commit, rendered natively by a `/help` route in
   the app's own layout, so the in-app docs always match the installed
   release, work offline, and follow the user's colour scheme for free.

## Non-goals (this project)

- Contextual "?" deep links from settings and other screens into `/help`
  (follow-up; the route makes them one-line additions).
- Help reachable before login. `/help` sits behind the same client-side auth
  as every route; the public Pages site covers the logged-out case.
- Replacing or retiring the GitHub wiki sync (`publish-wiki.yml` stays).
- Versioned archives on Pages. Pages shows `main`; the app shows its own
  version.
- Publishing `docs/plans/`, `docs/superpowers/`, `docs/PSDs/`, `CLAUDE*.md`,
  `TODO.md`.
- A general-purpose static site generator. The build is ARM-specific.

## Decisions

| decision | choice | why |
|---|---|---|
| generator | small custom Node build (markdown-it + Shiki + MiniSearch) | off-the-shelf generators fight the ui-neu look and cannot also emit app fragments |
| outputs | one build, two targets: a static HTML site (Pages) and an app bundle of JSON page fragments (ui-neu) | one renderer, identical content on both hosts |
| in-app presentation | native SvelteKit `/help/[...slug]` route renders fragments in the app layout | no iframe: schemes, layout and navigation are the app's own; no CSP framing change |
| site URLs | relative only | the Pages build works under `/arm-v3/` and from `file://` with no `base` setting |
| content styling | `docs-prose` block in ui-neu's `components/`; the Pages site imports it | one stylesheet for doc content, governed by the ui-neu style guide and lint |
| search | MiniSearch index emitted by the build, used by both hosts | no WASM, so no CSP change in the app; same results everywhere |
| location | `site/` in the ARM repo; ARM root is `..` | docs, tokens and site change together; the ui-neu Docker build context is the repo root |
| base branch | stacked on PR #74 | the token/block system only exists there |

## Architecture

```
site/
  package.json            scripts: build, build:app, test, dev
  manifest.json           sections, source paths/globs, ordering, repo slug
  src/
    build.mjs             entry: collect -> render -> write site + app bundle
    collect.mjs           manifest -> page list; wiki nav from arm_wiki/_Sidebar.md
    links.mjs             link/image resolution, validation, per-target hrefs
    render.mjs            markdown-it pipeline -> content HTML + toc
    search.mjs            MiniSearch index from rendered text
    template.html         Pages page shell (header, sidebar, content, toc, footer)
    styles/site.css       @imports ui-neu tokens + blocks (incl. docs-prose); site chrome layout
    client/theme.js       sync in <head>: light/dark before first paint
    client/site.js        mobile drawer, toc scroll-spy, search box
  test/                   node:test suites + fixture ARM trees
  build/                  output (gitignored): site/ and app/

services/ui-neu/frontend/
  src/lib/styles/components/docs-prose.css   rendered-content block (shared)
  src/lib/docs/            loader + search wrapper for the app bundle
  src/routes/help/[...slug]/+page.svelte, +page.ts
  static/docs-data/        dev-only copy of the app bundle (gitignored)

.github/workflows/docs-pages.yml
```

The ARM root defaults to the parent of `site/` and can be overridden with the
`ARM_ROOT` environment variable (tests use fixture trees).

### Units

**collect** - input: `manifest.json`, ARM root. Output: an ordered list of
`Page { id, srcPath, section, slug, title }` plus the nav tree. `id` is
`<section>/<slug>`.

- *Guide* section (`guide`): every `arm_wiki/*.md` except files starting with
  `_`. Nav order and group headings come from parsing `arm_wiki/_Sidebar.md`
  (bold lines are groups, list items are links). `Home.md` has id
  `guide/home`; the site writes it as the root `index.html` (not
  `guide/home.html`) and the app serves it at bare `/help`. Sidebar entries that point outside the
  wiki (issues, license, arch README) are kept as nav links, resolved by
  `links` like any other link.
- *Developers* section (`dev`): `docs/arch/*.md` (ordered by `NN-` prefix,
  `README.md` first as the section landing page), `docs/ops/*.md`,
  `docs/dev-setup.md`, `CONTRIBUTING.md`, `docs/ui-neu-style-guide.md`,
  `docs/ui-neu-theming.md`, `docs/contributors/*.md`.
- `slug` is the lowercased filename stem (arch files keep their `NN-`
  prefix).
- Title: first `# ` heading, else the stem de-slugged.
- A manifest entry that matches no files, or two sources mapping to the same
  `id`, is a build error.

**links** - input: a link target, the source file's repo path, the page map.
Output: a resolved target (`page id + fragment`, `repo file`, `external`) or
an error. Resolution is target-independent; hrefs are produced per target at
write time:

| resolved to | site href | app href |
|---|---|---|
| published page | relative `../dev/01-architecture.html#frag` | `/help/dev/01-architecture#frag` |
| unpublished repo file | `https://github.com/<repo>/blob/main/<path>` | same |
| external | unchanged, `target="_blank" rel="noopener"` | same |

- Wiki-style bare targets (`Getting-Started`, `Getting-Started#install`)
  resolve against `arm_wiki/`.
- Absolute wiki URLs for this project
  (`github.com/automatic-ripping-machine/automatic-ripping-machine/wiki/<Page>`
  and the `uprightbass360/arm-v3` equivalent) are treated as wiki targets.
- Relative repo paths (`../docs/arch/README.md`, `./ui-neu-theming.md`) and
  absolute blob URLs to this repo's `main` resolve against the ARM root.
- Target file missing on disk: **error** with `src:line`.
- Fragment on a published page that does not match a generated heading id:
  **error**.
- Images: copied into `assets/<repo path>` in each output and rewritten
  (site: relative; app: `/docs-data/assets/...`). Missing image: error.

Rendering emits links as placeholders (`data-doc-link` attributes carrying
the resolved target) and the writer substitutes the per-target href, so the
markdown pipeline runs once per page.

**render** - markdown-it producing a content HTML fragment and a toc:
GitHub-compatible heading ids (existing `#fragment` links keep working),
tables wrapped in a scroll container, GitHub alerts (`> [!NOTE]`,
`[!WARNING]`, ...) and bold-lead blockquotes (`> **Note**`) mapped to the
ui-neu `alert` block, fenced code highlighted by Shiki with a light and a
dark theme emitted as CSS variables (the `dark` class picks the set, so no
per-mode inline colour). The fragment's only classes are block vocabulary
(`alert`, `table`, `code-block`, ...) and `docs-prose` element classes;
never Tailwind utilities, so it complies with the style guide wherever it is
injected. No `<script>` in any fragment.

**search** - builds a MiniSearch index over `{ id, title, headings, text }`
per page and serialises it to JSON, emitted into both outputs. MiniSearch is
a small zero-dependency library; the site bundles it into `site.js`, ui-neu
adds it as a dependency.

**write** - two outputs from one render pass:

- `build/site/`: one HTML file per page (`index.html`, `guide/<slug>.html`,
  `dev/<slug>.html`) from `template.html`, compiled CSS, client JS,
  `fonts/`, `assets/`, `search.json`.
- `build/app/`: `nav.json` (sections, groups, items with ids and labels),
  `pages/<section>/<slug>.json`
  (`{ id, title, html, toc, source, editUrl }`), `assets/`, `search.json`,
  `meta.json` (`{ version, commit, builtAt }`).

**css (site only)** - `styles/site.css` `@import`s, from the ARM root,
ui-neu's `tokens.css`, `base.css`, `layout.css`, `utilities.css` and the
blocks the site uses (`panel`, `button`, `alert`, `badge`, `code-block`,
`table`, `nav`, `field`, `text`, `docs-prose`), then site-chrome layout.
Compiled with the Tailwind v4 CLI (the ui-neu sheets use `@theme`/`@apply`).
Rajdhani is copied from `services/ui-neu/frontend/static/fonts/`.

## ui-neu integration

**`docs-prose` block** (`src/lib/styles/components/docs-prose.css`): prose
rhythm, headings, lists, links, inline code, blockquotes, images, the table
scroll wrapper and Shiki variable switching, all from tokens. Follows the
style guide (tokens only, no `!important`, `@layer components`) and passes
the style lint. The style guide's block table gains a `docs-prose` row.

**`/help/[...slug]` route**:

- `+page.ts` loads `/docs-data/nav.json` and
  `/docs-data/pages/<slug>.json` (empty slug means `guide/home`). A missing
  page or a non-JSON response (nginx's SPA fallback returning `index.html`)
  renders a not-found state with a link back to `/help`.
- `+page.svelte` renders a two-column layout inside the app shell: a docs
  nav (`nav` block, grouped by section) and the content
  (`<article class="docs-prose">{@html page.html}</article>`), with the toc
  on wide screens and the nav collapsing to a select or drawer on mobile.
- `{@html}` is acceptable here: the HTML is produced at image build time from
  the repo's own markdown, served same-origin, and contains no scripts. This
  is stated in a comment at the injection site.
- Internal link clicks inside the fragment are intercepted and routed with
  `goto` (client-side navigation); fragment links scroll within the page.
- Search box in the docs nav, backed by `search.json` via MiniSearch, results
  link to `/help/<id>#<heading>`.
- The app's nav gains a "Help" entry (`/help`) with a Lucide help glyph,
  available to guests.
- Colour schemes need no work: the route is ordinary app DOM.

**Container** - `services/ui-neu/Dockerfile` gains a stage that builds the
app bundle, and the nginx stage copies it to `/usr/share/nginx/html/docs-data`:

```dockerfile
FROM node:26-slim AS docs
WORKDIR /repo/site
COPY site/package.json site/package-lock.json ./
RUN npm ci
COPY site/ ./
COPY arm_wiki/ /repo/arm_wiki/
COPY docs/ /repo/docs/
COPY CONTRIBUTING.md VERSION /repo/
COPY services/ui-neu/frontend/src/lib/styles/ /repo/services/ui-neu/frontend/src/lib/styles/
ARG ARM_COMMIT=unknown
RUN ARM_COMMIT=$ARM_COMMIT npm run build:app
# ...
COPY --from=docs /repo/site/build/app /usr/share/nginx/html/docs-data
```

The docs build must not need `.git`. `nginx.conf` gains
`location /docs-data/ { try_files $uri =404; }` ahead of `location /` so a
missing file is a real 404, not the SPA fallback. No CSP change: no frames,
no WASM, no inline scripts; the Shiki CSS-variable `style` attributes are
covered by the existing `style-src 'unsafe-inline'`.

**Dev loop** - `npm run docs` in `services/ui-neu/frontend` runs the site's
`build:app` with its output pointed at `static/docs-data/` (gitignored), so
`vite dev` serves `/help` with real content.

## Pages site design

- Header bar: ARM wordmark in the display face, search, light/dark toggle,
  GitHub link. Icons are inline SVG (Lucide paths), never emoji.
- Left sidebar: "Guide" and "Developers" groups, `nav`-block items, active
  page highlighted. Collapses to a drawer below the `lg` breakpoint.
- Content column (`docs-prose`) capped at ~75ch; right toc with scroll-spy
  on wide screens only.
- Footer: "Edit this page on GitHub", ARM version (from `VERSION`), build
  commit.
- No horizontal page scroll at 360px; wide tables and code scroll in their
  own containers.
- Theming: default ui-neu tokens. `theme.js` runs synchronously in `<head>`
  and sets the `dark` class from `localStorage.theme` (`'dark'|'light'`, the
  key ui-neu uses), falling back to `prefers-color-scheme`; it tolerates
  `localStorage` throwing. The header toggle writes the same key. Colour
  schemes are an in-app feature only.
- UI copy in chrome (site and `/help`) contains no em-dashes (repo
  convention).

## Deployment

### GitHub Pages - `.github/workflows/docs-pages.yml`

- Triggers: push to `main` touching `arm_wiki/**`, `docs/**`,
  `CONTRIBUTING.md`, `VERSION`, `site/**`,
  `services/ui-neu/frontend/src/lib/styles/**`,
  `services/ui-neu/frontend/static/fonts/**`, or the workflow file; and
  `workflow_dispatch` (for testing from `feat/docs-site`).
- Jobs: `build` (checkout, setup-node with npm cache on
  `site/package-lock.json`, `npm ci`, `npm test`, `npm run build`,
  `actions/upload-pages-artifact` with `site/build/site`) then `deploy`
  (`actions/deploy-pages`, environment `github-pages`).
- Permissions: `contents: read`, `pages: write`, `id-token: write`;
  concurrency group `pages`, cancel-in-progress false.
- Every `uses:` pinned to a 40-char SHA with a `# vX.Y.Z` comment.
- One-time repo setup (manual, by the owner): Settings > Pages > Source
  "GitHub Actions"; Settings > Environments > github-pages > add
  `feat/docs-site` to deployment branches while testing.

### CI - `.github/workflows/ci.yml`

New `test-site` job on PRs and pushes: `npm ci && npm test && npm run build`
in `site/`. A broken doc link fails the PR, not the deploy. The existing
ui-neu jobs cover the route and the `docs-prose` block (vitest, svelte-check,
style lint).

## Error handling

All content failure is at build time.

| condition | result |
|---|---|
| ARM root or `tokens.css` missing | exit 1, message names the path and `ARM_ROOT` |
| manifest entry matches nothing, duplicate page id | exit 1 |
| link to nonexistent file, missing anchor, missing image | all collected and reported as `src:line: message`, then exit 1 |
| link to unpublished repo file | rewritten to GitHub blob URL, info log |

Runtime (app): missing or malformed page JSON renders the not-found state;
missing `nav.json` or `search.json` renders the page without nav or search
and logs a console warning, never a crash.

## Testing

- `site/` `node --test` suites:
  - `links`: wiki bare targets, fragments, absolute wiki URLs, relative repo
    paths, blob URLs, unpublished-file fallback, missing file/anchor/image
    errors, per-target href generation (site relative vs app route).
  - `collect`: `_Sidebar.md` parsing (groups, external items), arch
    ordering, title extraction, empty-glob and duplicate-id errors.
  - `render`: alert mapping, table wrapper, GitHub-compatible heading ids,
    no `<script>` and no Tailwind utility classes in fragments.
  - Integration: build against the real ARM root; zero errors; every site
    page has a `<title>`; no `href`/`src` in `build/site` starts with `/`;
    every `nav.json` item has a page file.
- ui-neu vitest: `/help` load with fixture JSON (page, empty slug, missing
  page, SPA-fallback HTML response), internal link interception, search
  wiring.
- Manual verification with Playwright before calling it done:
  1. `build/site/index.html` from `file://` navigates and searches.
  2. `build/site` served under `/arm-v3/` (mimicking Pages): navigation,
     search, light and dark.
  3. ui-neu via `vite dev` with `npm run docs`: `/help` renders, internal
     links navigate client-side, search works, a non-default scheme (e.g.
     LCARS) styles the docs.
  4. ui-neu container built locally: `/help` works with the baked-in bundle;
     `/docs-data/pages/nope.json` returns 404.
  5. 360px viewport on both hosts: no horizontal page scroll, drawer works.
  6. Pages deploy from `feat/docs-site` via `workflow_dispatch` succeeds and
     the live URL passes check 2.

## Follow-ups (out of scope)

- Contextual "?" deep links from settings and other screens into `/help`.
- Consider retiring the wiki sync once the site is the canonical user guide.
