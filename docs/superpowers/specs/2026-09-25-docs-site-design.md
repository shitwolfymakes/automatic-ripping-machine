# ARM documentation site - design

Date: 2026-09-25
Branch: `feat/docs-site` (off `main` = `wolfy/main` @ `ccecd688`)
Status: approved design, awaiting implementation plan

## Problem

ARM v3's user documentation lives in `arm_wiki/` (synced to the GitHub wiki)
and its developer documentation is scattered across `docs/arch/`, `docs/ops/`,
`docs/dev-setup.md` and `CONTRIBUTING.md`. There is no single browsable,
searchable site; the wiki is online-only, unversioned relative to the
installed release, and looks nothing like the app. The ui-neu frontend has a
mature design system (tokens, blocks, 25 colour schemes) that the docs do not
share.

## Goals

1. A static documentation site built **from the repo's own markdown** - no
   duplicated content, no separate docs repo.
2. **Deployed to GitHub Pages** from `uprightbass360/arm-v3` by a workflow in
   this repo (`https://uprightbass360.github.io/arm-v3/`).
3. **Styled from ui-neu**: the site consumes ui-neu's real `tokens.css` and
   block stylesheets at build time, so a token change in the app reaches the
   docs on the next build.
4. **Embeddable in the app**: the ui-neu container serves the same build at
   `/docs/`, version-matched and offline, and when framed by the app it
   follows the user's live colour scheme.

## Non-goals (this project)

- The ui-neu `/help` route, nav entry, and contextual "?" links. Follow-up
  project; this one delivers everything that route will need.
- Replacing or retiring the GitHub wiki sync (`publish-wiki.yml` stays).
- Versioned docs (per-release archives) on Pages. Pages shows `main`; the
  container shows the installed version.
- Publishing `docs/plans/`, `docs/superpowers/`, `docs/PSDs/`, `CLAUDE*.md`,
  `TODO.md`.
- A general-purpose static site generator. The build is ARM-specific.

## Decisions

| decision | choice | why |
|---|---|---|
| generator | small custom Node build (markdown-it + Shiki + Pagefind) | off-the-shelf generators fight the ui-neu look and bake in a build-time `base`; we need one artifact that works at two base paths |
| URLs | relative only, everywhere | the same `build/` works on Pages (`/arm-v3/`), in-app (`/docs/`), and from `file://`; no `base` to misconfigure |
| location | `site/` in the ARM repo; ARM root is `..` | docs, tokens and site change together; the ui-neu Docker build context is already the repo root |
| embedding | bundled into the ui-neu image, same-origin iframe | offline, version-matched, and same-origin lets the frame read the app's scheme |
| search | Pagefind | static index, client-side, works offline and in-app |

## Architecture

```
site/
  package.json            scripts: build, test, dev (build + static serve)
  manifest.json           sections, source paths/globs, ordering
  src/
    build.mjs             entry: collect -> render -> write -> css -> pagefind
    collect.mjs           manifest -> page list; wiki nav from arm_wiki/_Sidebar.md
    links.mjs             link/image rewriting + validation
    render.mjs            markdown-it pipeline + page template
    template.html         page shell (header, sidebar, content, toc, footer)
    styles/site.css       @imports ui-neu tokens + blocks; docs-only layout
    client/theme.js       sync, loaded in <head>: light/dark before first paint
    client/embed.js       embed mode + parent scheme mirroring
    client/nav.js         mobile drawer, toc highlight, search box wiring
  test/                   node:test suites + fixtures
  build/                  output (gitignored)
.github/workflows/docs-pages.yml
```

The ARM root defaults to the parent of `site/` and can be overridden with the
`ARM_ROOT` environment variable (used by tests with fixture trees).

### Units

**collect** - input: `manifest.json`, ARM root. Output: an ordered list of
`Page { srcPath, outPath, section, title, navLabel }` plus the nav tree.

- *Guide* section: every `arm_wiki/*.md` except files starting with `_`.
  Nav order and group headings come from parsing `arm_wiki/_Sidebar.md`
  (bold lines are groups, list items are links). `Home.md` becomes
  `index.html`. Sidebar entries that point outside the wiki (issues, license,
  arch README) are kept as nav links, remapped by `links` like any other link.
- *Developers* section: `docs/arch/*.md` (ordered by `NN-` prefix, `README.md`
  first as the section landing page), `docs/ops/*.md`, `docs/dev-setup.md`,
  `CONTRIBUTING.md`, `docs/ui-neu-style-guide.md`, `docs/ui-neu-theming.md`,
  `docs/contributors/*.md`.
- Output path: `guide/<slug>.html` and `dev/<slug>.html`, where `slug` is the
  lowercased filename stem (arch files keep their `NN-` prefix).
- Title: first `# ` heading, else the filename stem de-slugged.
- A manifest entry that matches no files is a build error.

**links** - input: a link target, the source file's repo path, the page map.
Output: a rewritten href, or an error.

- Wiki-style bare targets (`Getting-Started`, `Getting-Started#install`)
  resolve against `arm_wiki/`.
- Absolute wiki URLs for this project
  (`github.com/automatic-ripping-machine/automatic-ripping-machine/wiki/<Page>`
  and the `uprightbass360/arm-v3` equivalent) are treated as wiki targets.
- Relative repo paths (`../docs/arch/README.md`, `./ui-neu-theming.md`) and
  absolute blob URLs to this repo's `main` resolve against the ARM root.
- Resolved target is a published page: emit a relative `.html` href from the
  current page, preserving the fragment.
- Resolved target is a repo file that is not published: emit
  `https://github.com/uprightbass360/arm-v3/blob/main/<path>` and log an info
  line.
- Resolved target does not exist on disk: **error** with `src:line`.
- Fragment on a published page that does not match a generated heading id:
  **error**.
- Images: relative image paths are copied into `build/assets/` under their
  repo path and rewritten; a missing image is an error.
- External `http(s)` links pass through unchanged and get
  `target="_blank" rel="noopener"`.

The GitHub owner/repo used for blob and edit links is a single constant in
`manifest.json`.

**render** - markdown-it with: heading anchors (GitHub-compatible slugs so
existing `#fragment` links keep working), tables wrapped in a scroll
container, GitHub alerts (`> [!NOTE]`, `[!WARNING]`, ...) and bold-lead
blockquotes (`> **Note**`) mapped to the ui-neu `alert` block, fenced code
highlighted by Shiki with a light and a dark theme emitted as CSS variables
(switched by the `dark` class, so no inline colour per mode), and a
right-hand table of contents from h2/h3. The template fills title, nav (with
the active page marked), content, toc, an "Edit on GitHub" link to the source
file, and the relative prefix to the site root. No inline `<script>` in any
page.

**css** - `styles/site.css` `@import`s, from the ARM root,
`services/ui-neu/frontend/src/lib/styles/tokens.css`, `base.css`, `layout.css`,
`utilities.css` and the blocks the docs use (`panel`, `button`, `alert`,
`badge`, `code-block`, `table`, `nav`, `tabs`, `field`, `text`), then
docs-only layout (page grid, sidebar, prose rhythm, toc). Compiled with the
Tailwind v4 CLI, since the ui-neu sheets use `@theme`/`@apply`. Rajdhani is
self-hosted by copying `services/ui-neu/frontend/static/fonts/*` into
`build/fonts/`. Docs chrome uses the same block classes as the app (`panel`,
`btn`, `nav-item`, ...) so scheme sheets that decorate those classes decorate
the docs too.

**search** - after pages are written, run Pagefind over `build/` to emit
`build/pagefind/`. The header search box uses Pagefind's JS API (no
Pagefind default UI styling), results rendered with ui-neu blocks.

## Page design

- Header bar: ARM wordmark in the display face, search, light/dark toggle,
  GitHub link. Icons are inline SVG glyphs (Lucide paths), never emoji.
- Left sidebar: "Guide" and "Developers" groups, `nav`-block items, active
  page highlighted. Collapses to a drawer below the `lg` breakpoint.
- Content column capped at ~75ch; prose uses `text-*` tokens.
- Right table of contents on wide screens only, with scroll-spy highlight.
- Footer: "Edit this page on GitHub", ARM version (from `VERSION`), build
  commit.
- No horizontal page scroll at 360px width; wide tables and code blocks
  scroll inside their own containers.
- UI copy in the chrome contains no em-dashes (repo convention).

## Theming

**Standalone** (Pages, direct visit, `file://`): default ui-neu tokens.
`theme.js` runs synchronously in `<head>` and sets the `dark` class from
`localStorage.theme` (`'dark'|'light'`, the key ui-neu uses), falling back to
`prefers-color-scheme`. The header toggle writes the same key. Colour schemes
are not available standalone.

**Embedded** (framed by the app): `embed.js` activates when the page is in a
frame, or when `?embed=1` is present.

- Adds `data-embed` to `<html>`; CSS hides the header and footer and keeps
  sidebar, search and toc. Internal links preserve `?embed=1`.
- If `window.parent` is same-origin (access does not throw), mirror from the
  parent `<html>`: the inline `style` attribute (the scheme token map), the
  `dark` class, and `data-scheme`; and copy the text of the parent's
  `#arm-theme-css` (or `#theme-cache` if that is all that exists) into a
  local `<style id="arm-theme-css">`. A `MutationObserver` on the parent
  `<html>` attributes and on the parent `<head>` child list re-runs the
  mirror, so switching schemes in the app updates the frame live.
- Cross-origin parent or any exception: do nothing beyond embed chrome;
  standalone theming applies.

The app needs no API changes; the contract is ui-neu's existing
`applyScheme` output documented in `docs/ui-neu-theming.md` section 1. That
section gains a note that the docs frame mirrors it.

## Deployment

### GitHub Pages - `.github/workflows/docs-pages.yml`

- Triggers: push to `main` touching `arm_wiki/**`, `docs/**`, `CONTRIBUTING.md`,
  `site/**`, `services/ui-neu/frontend/src/lib/styles/**`,
  `services/ui-neu/frontend/static/fonts/**`, or the workflow file; and
  `workflow_dispatch` (for testing from `feat/docs-site`).
- Jobs: `build` (checkout, setup-node with npm cache on
  `site/package-lock.json`, `npm ci`, `npm test`, `npm run build`,
  `actions/upload-pages-artifact` with `site/build`) then `deploy`
  (`actions/deploy-pages`, environment `github-pages`).
- Permissions: `contents: read`, `pages: write`, `id-token: write`;
  concurrency group `pages`, cancel-in-progress false.
- Every `uses:` pinned to a 40-char SHA with a `# vX.Y.Z` comment.
- One-time repo setup (manual): Settings > Pages > Source "GitHub Actions";
  Settings > Environments > github-pages > add `feat/docs-site` to deployment
  branches while testing.

### CI - `.github/workflows/ci.yml`

New `test-site` job on PRs and pushes: `npm ci && npm test && npm run build`
in `site/`. A broken doc link fails the PR, not the deploy.

### ui-neu container

`services/ui-neu/Dockerfile` gains a stage:

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
COPY services/ui-neu/frontend/static/fonts/ /repo/services/ui-neu/frontend/static/fonts/
RUN npm run build
```

and the nginx stage adds `COPY --from=docs /repo/site/build /usr/share/nginx/html/docs`.
The docs build must not require `.git` (build commit falls back to
`unknown` or a `--build-arg`).

`services/ui-neu/nginx.conf` gains, before `location /`:

```nginx
location /docs/ {
    # nginx add_header in a location replaces the server-level set, so the
    # full header set is restated here. Differences from the app CSP:
    # frame-ancestors 'self' (the app frames the docs), no inline script,
    # 'wasm-unsafe-eval' for Pagefind's search index.
    add_header Content-Security-Policy "default-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'wasm-unsafe-eval'; frame-ancestors 'self'; base-uri 'self'" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header Referrer-Policy "no-referrer" always;
    try_files $uri $uri/index.html =404;
}
```

`style-src 'unsafe-inline'` stays because the mirrored scheme sheet is
injected as a `<style>` element and tokens arrive as an inline style
attribute.

## Error handling

All failure is at build time; the runtime is static files.

| condition | result |
|---|---|
| ARM root or `tokens.css` missing | exit 1, message names the path and `ARM_ROOT` |
| manifest entry matches nothing | exit 1 |
| link to nonexistent file, missing anchor, missing image | collected, all reported as `src:line: message`, then exit 1 |
| link to unpublished repo file | rewritten to GitHub blob URL, info log |
| duplicate output path | exit 1 |
| Pagefind failure | exit 1 |

Runtime: `embed.js` wraps all parent access in try/catch and degrades to
standalone theming; `theme.js` tolerates `localStorage` throwing.

## Testing

- `node --test` unit suites:
  - `links`: wiki bare targets, fragments, absolute wiki URLs, relative
    repo paths, blob URLs, unpublished-file fallback, missing file/anchor
    errors, images, external links.
  - `collect`: `_Sidebar.md` parsing (groups, external items), arch ordering,
    title extraction, empty-glob error, duplicate-path error.
  - `render`: alerts mapping, table wrapper, heading ids match GitHub slugs,
    no inline `<script>` in output.
- Integration test: build against the real ARM root; assert zero errors, every
  page has a `<title>`, and no `href`/`src` in any output file starts with
  `/` (the two-host guarantee).
- Manual verification with Playwright before calling it done:
  1. `build/index.html` opened from `file://` navigates and searches.
  2. `build/` served under `/arm-v3/` (mimicking Pages) navigates and
     searches; light and dark both render.
  3. ui-neu container built locally, `/docs/` loads, and a page on the app
     origin framing `/docs/?embed=1` shows embed chrome and follows a
     non-default scheme (e.g. LCARS), including a live switch.
  4. 360px viewport: no horizontal page scroll, drawer works.
  5. The Pages deploy from `feat/docs-site` via `workflow_dispatch` succeeds
     and the live URL passes check 2.

## Follow-ups (out of scope)

- ui-neu `/help` route with a full-height `/docs/` iframe, nav entry, and
  contextual "?" deep links from settings pages.
- Consider retiring the wiki sync once the site is the canonical user guide.
