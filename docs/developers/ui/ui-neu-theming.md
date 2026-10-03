# ui-neu theming contract

How a colour scheme is loaded, what it is allowed to target, and which tokens
and block classes it may rely on.

This document is the contract between the app's CSS and the 25 colour schemes
in `services/ui-neu/frontend/static/themes/`. If you are writing or repairing a
scheme, everything you need is here.

## 1. How a scheme loads

`services/ui-neu/frontend/src/lib/stores/colorScheme.ts` owns the whole
lifecycle. A scheme has two halves:

1. **A token map** (`ColorScheme.tokens`), compiled into the app as part of
   `COLOR_SCHEMES`. On `applyScheme(id)` these are written with
   `root.style.setProperty(...)` as an **inline style on `<html>`**.
2. **A stylesheet**, fetched at runtime and injected into a single managed
   `<style id="arm-theme-css">` element appended to `<head>`. Built-in schemes
   load `static/themes/<id>.css` same-origin; user-uploaded schemes come from
   the backend theme API.

`applyScheme` also sets `document.documentElement.dataset.scheme = id`, which
is what every selector in a sheet keys off, and adds or removes the `dark`
class. A scheme may pin the mode with `mode: 'light' | 'dark'`; a pinned scheme
ignores the user's theme toggle (`schemeLocksMode`).

`app.html` runs a small boot script before the bundle loads: it sets the `dark`
class from the saved scheme, and injects a `localStorage`-cached copy of the
sheet into a `<style id="theme-cache">` element to avoid a flash of unstyled
content. That cached copy is replaced on the next successful fetch.

### 1.1 Precedence, and the one rule that surprises everyone

The token map wins over the stylesheet, always.

An inline `style` attribute on `<html>` outranks every selector any stylesheet
can write, including `:root[data-scheme="x"]` and including `!important` in a
non-`!important` sheet. So:

> **A role that appears in a scheme's `tokens` map cannot be overridden from
> that scheme's stylesheet.** Change it in `colorScheme.ts`, or not at all.

The roles most schemes list in their map are `--color-primary`,
`--color-primary-hover`, `--color-primary-text`, `--color-on-primary`,
`--color-page`, `--color-surface`, their `-dark` twins, and `--radius`.
Everything else in section 2 is free for the sheet to set.

The sheet's own layer position is the other half of the picture: it is injected
**unlayered**, so it beats every `@layer components` block rule regardless of
specificity. It does **not** automatically beat a Svelte component's scoped
style, which is also unlayered; there, ordinary specificity and source order
decide. A scoped selector carries the component's hash class
(`.sidebar.svelte-12qhfyh`, specificity 0-2-0), so a theme selector of
`[data-scheme="x"] aside` (0-1-1) loses. Raise the theme selector instead of
reaching for `!important`: `[data-scheme="x"][data-scheme] aside` is 0-2-1 and
wins cleanly.

## 2. Tokens

Declared in `src/lib/styles/tokens.css`. Primitive tokens (the raw palette) are
private to that file; schemes and components reference the semantic roles only.
Do not invent new token names.

### 2.1 Colour roles

| Token | Role | Light default | Dark default |
|---|---|---|---|
| `--color-page` | page background | rgb(232 240 255) | rgb(13 16 28) |
| `--color-surface` | panels, cards, sidebar | rgb(241 247 255) | rgb(22 28 45) |
| `--color-surface-raised` | popovers, modals, flyouts, table header | white | rgb(30 37 58) |
| `--color-border` | hairlines, dividers, input borders at rest | primary at 18% | primary at 22% |
| `--color-border-strong` | focused/hovered borders, rings, emphasised dividers | primary at 30% | primary at 38% |
| `--color-text` | body text, headings | rgb(17 24 39) | rgb(243 244 246) |
| `--color-text-secondary` | form labels, row titles, secondary headings | rgb(55 65 81) | rgb(209 213 219) |
| `--color-text-muted` | secondary text, hints, table captions | rgb(107 114 128) | rgb(156 163 175) |
| `--color-text-faint` | placeholders, disabled, eyebrows | rgb(156 163 175) | rgb(107 114 128) |
| `--color-primary` | brand, primary actions, focus ring | rgb(37 99 235) | same |
| `--color-primary-hover` | primary hover | rgb(29 78 216) | same |
| `--color-on-primary` | text on a primary fill | white | white |
| `--color-primary-text` | primary-coloured text and links | rgb(29 78 216) | rgb(96 165 250) |
| `--color-primary-tint-1` | primary at 5%: subtle wash | mix | mix |
| `--color-primary-tint-2` | primary at 10%: chips, active nav, input backgrounds | mix | mix |
| `--color-primary-tint-3` | primary at 20%: selected, pressed | mix | mix |
| `--color-backdrop` | modal and slide-over scrim | rgb(0 0 0 / .5) | rgb(0 0 0 / .6) |
| `--color-danger` / `-soft` / `--color-on-danger-soft` | destructive actions, error alerts | rgb(220 38 38) / rgb(254 242 242) / rgb(185 28 28) | rgb(248 113 113) / rgb(127 29 29 / .35) / rgb(252 165 165) |
| `--color-warning` / `-soft` / `--color-on-warning-soft` | warnings, attention | rgb(245 158 11) / rgb(255 251 235) / rgb(146 64 14) | rgb(251 191 36) / rgb(120 53 15 / .35) / rgb(252 211 77) |
| `--color-success` / `-soft` / `--color-on-success-soft` | success, healthy | rgb(22 163 74) / rgb(240 253 244) / rgb(21 128 61) | rgb(74 222 128) / rgb(20 83 45 / .35) / rgb(134 239 172) |
| `--color-info` / `-soft` / `--color-on-info-soft` | informational alerts | primary / primary-tint-2 / primary-text | same |
| `--color-status-scanning`, `-ripping`, `-transcoding`, `-finishing`, `-waiting`, `-success`, `-error` | job and drive status glyphs, cards, badges | existing values | same |
| `--color-accent-1` .. `-4` | the fixed accent set used by disc-type icons and glyph tiles (amber, blue, violet, cyan) | existing values | same |
| `--color-frame-accent`, `--color-on-frame-accent` | the `section-frame` accent bar and its text | rgb(255 153 0) / rgb(0 0 0) | same |

Each of the four tones comes in exactly three tokens: solid (fills, badges,
dots, icons), soft (backgrounds), and on-soft (text). Tone borders are derived
in block CSS with `color-mix(in srgb, var(--color-<tone>) 30%, transparent)`;
there are no per-tone border tokens.

### 2.2 Non-colour tokens

| Token | Values |
|---|---|
| `--radius`, `--radius-sm/md/lg/xl/2xl` | radius scale; the `-sm`..`-2xl` steps are computed from `--radius` |
| `--shadow-1`, `--shadow-2` | card and popover elevation (two steps only) |
| `--font-sans`, `--font-display` (Rajdhani), `--font-mono` | font families |
| `--motion-fast` (150ms), `--motion-base` (250ms), `--ease` | all transitions; `prefers-reduced-motion` zeroes both in `base.css` |
| `--control-h` (2.25rem), `--control-h-sm` (1.75rem) | field and button heights, so rows line up |
| `--eyebrow-size` (11px), `--eyebrow-tracking` (0.12em) | the small uppercase tracked label used by panel titles and table headers |

### 2.3 Dark mode

`tokens.css` flips the semantic values once, in its `.dark {}` block. A scheme
does not need `dark:` anything: set a role and both modes follow, or scope an
override to `:root[data-scheme="x"].dark` when the two modes genuinely differ.

A scheme's own `tokens` map handles the mode split differently, through
`-dark`-suffixed twins (`--color-surface` / `--color-surface-dark`):
`applyTokens` writes whichever matches the effective mode. `--color-primary` is
deliberately mode-invariant there (`MODE_INVARIANT_ROLES`); the
`--color-primary-dark` name is a separate legacy alias, not primary's dark twin.

## 3. What a scheme may target

A scheme may select:

- the semantic tokens in section 2;
- the block classes and their elements, modifiers and state hooks in section 4;
- real HTML elements (`aside`, `header`, `main`, `body`, `hr`, `table`,
  `input`, `select`, `option`);
- the published data attributes: `[data-scheme]`, `[data-active]`,
  `[data-status]`, `[data-selected]`, `[data-progress-track]`,
  `[data-progress-fill]`, `[data-indeterminate]`, `[data-bar]`,
  `[data-frame-variant]`, `[data-dialog]`, `[data-logo]`,
  `[data-sidebar-stats]`, `[data-poster]` (every PosterImage img and its
  fallback tile, plus the job-detail track posters — the hook for framing
  cover art), plus the ARIA state attributes (`[aria-selected]`,
  `[aria-checked]`, `[aria-pressed]`, `[aria-expanded]`);
- its own decorative pseudo-elements.

### 3.1 A scheme must never target a component-local class

Component-local class names (`session-builder-*`, `sessions-hub-*`,
`job-card-*`, `disc-review-widget-*`, `layout-*`, `interface-settings-*`, and
every other `<component>-<part>` name) live inside one component's scoped
`<style>`. They are private. They are renamed, split and deleted whenever that
component is refactored, with no deprecation and no notice, and Svelte hashes
them, so a scheme that depends on one is depending on a build artefact.

This is the single most important rule in this document, and it is the reason
the block vocabulary exists at all: **the blocks are the public surface, the
scoped classes are the private one.**

If a scheme wants to restyle something that only has a component-local class,
the answer is a token, not a selector. Set the role that element paints from
and it follows. If no token reaches it, the correct outcome is that the scheme
does not restyle it, not a selector reaching into the component.

### 3.2 Prefer a token to a rule

If a scheme only wants different colours, it should set tokens under its
`[data-scheme="x"]` prefix and write no selectors at all. Fifteen of the 25
schemes are exactly this. A structural rule is for shape: a clip-path, a
pseudo-element ornament, a different radius or border language, a changed
box model. Colour alone is always a token.

Corollary: when a token now does the job, **delete the rule**. A theme sheet
full of colour rules that duplicate what a token already sets is how these
sheets rotted in the first place.

### 3.3 A rule that matches nothing is a bug, and the fix is deletion

A theme rule whose selector no longer matches any element is not harmless
dead weight: it is a bug in the theme, and it is how these sheets rotted.
Delete it.

Deletion, not repair, is the default. Before retargeting a stale selector,
check whether the markup it wants still exists **under a new name** or whether
it is gone outright, and check that at the branch point rather than at HEAD:

```bash
git grep -l 'data-stats' <branch-point> -- 'services/ui-neu/frontend/src'
```

- Still present under a new name (`nav a` becoming `.nav-item`, `.bg-surface`
  becoming `.panel`): retarget it to the block.
- Gone because the UI it styled was removed, or never present at all: delete
  it. Repairing such a rule does not restore the theme, it adds a decoration
  the app has not had for many commits.

Two selectors in these sheets were in the second category and were deleted
rather than retargeted: `aside [data-stats]`, whose attribute went away with
the old hardware-stats UI, and `[data-surface]`, which was never in any markup
at all.

### 3.4 `!important`

Do not write new `!important`. The sheet is unlayered and already outranks
every block rule; the only thing it does not automatically beat is a
component's scoped style, and the fix there is specificity (section 1.1), not
force. Existing `!important` in decorative rules may stay where removing it
changes rendering.

### 3.5 Literal colours

A theme sheet is the one place a scheme's own literal colours belong: its token
definitions, and its decorative rules, are inherently scheme-specific. That is
the opposite of the rule for component CSS, where literals are banned outright.
Do not invent new token *names* though: use the section 2.1 roles.

## 4. The block contract

Each block's CSS file in `src/lib/styles/components/` carries a header comment
naming its purpose, elements, modifiers and state hooks. That comment is the
contract; this table is a copy of it.

| Block | Elements | Modifiers | State hooks |
|---|---|---|---|
| `alert` | `alert-title`, `alert-body` | `alert-info` (default), `alert-warning`, `alert-danger`, `alert-success`, `alert-lg` | none |
| `badge` | none | `badge-status`, `badge-danger`, `badge-warning`, `badge-success`, `badge-info`, `badge-sm`, `badge-imdb` | `[data-status]` on `badge-status` |
| `btn` | none | `btn-primary`, `btn-danger`, `btn-warning`, `btn-ghost`, `btn-link`, `btn-icon`, `btn-sm` | `:disabled`, `[aria-pressed="true"]`, `[data-busy="true"]`; a `.chevron` child rotates on `[aria-expanded="true"]` |
| `card` | `card-header`, `card-title`, `card-body`, `card-footer`, `card-accent` | `card-status` (accent colour from `data-status`) | `[data-status]`, `[data-selected="true"]` |
| `chip` | none | `chip-danger`, `chip-warning`, `chip-success`, `chip-info`, `chip-sm` | `[aria-pressed="true"]`, `[data-selected="true"]` |
| `code-block` | none | `code-block-scroll` | none |
| `field` | `field-label`, `field-help`, `field-error`, `field-control`; native `input`/`select`/`textarea` styled by descendant rule | `field-row` | `[aria-invalid="true"]`, `:disabled`, `:focus-visible` |
| `flyout` | `flyout-item`, `flyout-divider` | none | `[data-placement]` |
| `glyph` | none | `glyph-sm`, `glyph-md`, `glyph-lg`, `glyph-danger`, `glyph-warning`, `glyph-success`, `glyph-info` | `[data-glyph]` |
| `list-row` | `list-row-lead`, `list-row-main`, `list-row-meta`, `list-row-actions` | `list-row-compact` | `[data-active="true"]`, `[data-disabled="true"]`, `[aria-expanded]` |
| `modal` | `modal-backdrop`, `modal-panel`, `modal-title`, `modal-body`, `modal-actions` | `modal-wide` | none |
| `nav` | `nav-item`, `nav-badge`, `nav-logo` | none | `[data-active="true"]` on `nav-item` |
| `panel` | `panel-title`, `panel-hint`, `panel-actions`, `panel-body`, `panel-section` | `panel-compact` | `[aria-expanded]` on a collapsible `button.panel-title` |
| `progress` | `progress-track`, `progress-fill` (keep the `data-progress-track` / `data-progress-fill` attributes: schemes hook them) | `progress-sm` | `[data-indeterminate="true"]`, `[data-status]`, `[data-bar="danger"\|"warning"\|"cpu"\|"mem"\|"disk"]` |
| `section-frame` | `section-frame-bar-top`, `section-frame-bar-bottom`, `section-frame-sidebar`, `section-frame-body` | none | `[data-frame-variant]`; accent via `--frame-accent` |
| `skeleton` | none | `skeleton-text`, `skeleton-block`, `skeleton-card` | none |
| `slide-over` | `slide-over-panel`, `slide-over-header` | none | none |
| `stat` | `stat-label`, `stat-value` | `stat-danger`, `stat-warning`, `stat-success`, `stat-info`, `stat-muted` | none |
| `status-dot` | none | none | `[data-status]` |
| `table` | `table-header`, `table-row`, `table-cell`, `table-sort` | `table-compact`, `table-right`, `responsive-table` | `[aria-sort]` on `table-sort`, `[data-selected="true"]` on `table-row` |
| `tabs` | `tabs-tab` | `tabs-pills` | `[aria-selected="true"]` on `tabs-tab` |
| `toast` | `toast-title`, `toast-body` | `toast-info` (default), `toast-danger`, `toast-warning`, `toast-success` | none |
| `toggle` | `toggle-thumb` | `toggle-sm`, `toggle-lg` | `[aria-checked]`, `:disabled`; also matches a split control via `[role="switch"][aria-checked="true"] > .toggle` |
| `eyebrow`, `mono`, `kbd` | text helpers | none | none |

Layout helpers (`stack`, `stack-sm`, `stack-lg`, `cluster`, `grid-2`, `grid-3`,
`page`, `page-header`, `page-title`, `split`) live in `layout.css`. They
describe arrangement, and a scheme should touch them only to change spacing it
genuinely owns.

### 4.1 `.nav` is a flex column

Worth calling out because it has bitten six schemes: `.nav` is
`display: flex; flex-direction: column; gap: 0.25rem`. Adjacent margins do
**not** collapse in a flex container. A scheme that spaces its nav links with
`margin: 8px 0` on `.nav-item` therefore gets 16px between links plus the
block's own gap, not the 8px a block-level `<nav>` would have given it. Express
inter-link spacing as `.nav { gap: ... }` and, if the original also had space
above the first link and below the last, add it to `.nav`'s padding.

### 4.2 The `table` / `table-row` / `table-cell` name collision

`table`, `table-row` and `table-cell` are also valid CSS `display` keyword
values, so Tailwind v4 auto-generates its own utility class of each of those
names (`display: table`, `display: table-row`, `display: table-cell`). Those
land in Tailwind's `utilities` layer.

Cascade layers are ordered, and `utilities` comes after `components`. An
ordered layer always wins over an earlier one **regardless of selector
specificity**, so Tailwind's one-declaration `.table-row { display: table-row }`
silently beats anything `table.css` declares for `display` on the same class,
which is exactly what broke `responsive-table`'s documented mobile stacking
app-wide (it sets `display: block` on `tr`/`td` below 1024px).

The fix, and the resolution to remember: those media-query rules live in
`utilities.css`'s own `@layer utilities`, not in `table.css`'s
`@layer components`, so they sit in the same layer as the colliding Tailwind
utilities and plain source order decides. `!important` would also have worked
and is the wrong tool.

For a theme this matters in one way only: a scheme's sheet is **unlayered**, and
unlayered styles beat every layer, so a scheme restyling `.table-row` does not
hit this problem at all. Do not copy the `@layer utilities` workaround into a
scheme.

## 5. Worked example

Here is a real rule from the LCARS sheet as it was before this cleanup, and
what it became.

**Before.** The sheet painted every panel by hand, because the app's markup
carried Tailwind utilities and the sheet keyed off them:

```css
[data-scheme="lcars"] main .bg-surface,
[data-scheme="lcars"] main .dark\:bg-surface-dark {
	--frame-accent: #99f;
	background: rgba(153, 153, 255, 0.15) !important;
	border-radius: 21px !important;
	border: none !important;
	box-shadow: none !important;
}
```

Three separate problems. `.bg-surface` no longer exists in the markup, so the
rule matches nothing. `.dark\:bg-surface-dark` was only ever a dark-variant
utility, which the token flip has replaced entirely. And the whole thing is
`!important`, which was needed only to beat the utility it was fighting.

**After.** The colour half becomes a token, and the shape half becomes one rule
on the blocks that actually carry the role:

```css
/* the lifted plate LCARS panels sit on; this scheme's --color-page is pure
   black, so a surface painted with the page colour would be invisible */
:root[data-scheme="lcars"] {
	--color-surface: rgb(23, 23, 38);
	--shadow-1: none;
	--shadow-2: none;
}

/* panels, cards and stat tiles are rounded LCARS plates: no border, no
   shadow. The fill comes from --color-surface above. */
[data-scheme="lcars"] main .panel,
[data-scheme="lcars"] main .card,
[data-scheme="lcars"] main .stat {
	--frame-accent: #99f;
	border-radius: 21px;
	border: none;
}
```

Note what happened to each declaration:

- `background` left the rule entirely: `--color-surface` is the role every one
  of those blocks already paints from, so the token does it once for panels,
  cards, stat tiles, and every future consumer of the role.
- `box-shadow: none` became `--shadow-1`/`--shadow-2: none`, for the same
  reason: the blocks read the elevation tokens.
- `border-radius` and `border` stayed as a rule, because they are shape, and
  because LCARS's 21px plate is not the `--radius` scale.
- Every `!important` went away. The sheet is unlayered and already outranks the
  block rules it is overriding.

One caveat this example is a good illustration of: `--color-surface` is in
LCARS's `tokens` map in `colorScheme.ts`, so per section 1.1 the token line
above cannot live in the sheet at all: it has to be changed in the map. The
`--shadow-*` lines are not in the map, so those do belong in the sheet. Check
the map before writing a token override, every time.
