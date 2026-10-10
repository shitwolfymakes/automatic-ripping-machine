# ui-neu Style Guide

The reference for styling the SvelteKit frontend (`services/ui-neu/frontend`).
It covers where every visual decision belongs, the token set, the block
vocabulary, and the rules the style lint enforces in CI. Theme authors should
read this first, then [ui-neu-theming.md](./ui-neu-theming.md) for the
scheme-authoring contract.

A rendered, interactive version of this guide - live token swatches and
working block specimens - is served by every deployment at
[`/style-guide.html`](../services/ui-neu/frontend/static/style-guide.html).

The one-sentence version: **tokens are the only raw values, blocks are the
shared looks, components scope what is genuinely local, and markup carries
layout only.**

## 1. Architecture

Styling lives in four places, in order of preference:

| layer | where | what belongs there |
|---|---|---|
| tokens | `src/lib/styles/tokens.css` | every colour, radius, shadow and motion value; nothing else may hold a literal |
| blocks | `src/lib/styles/components/*.css` | a look shared by 2+ components (a button, a panel, a badge) |
| layout helpers / utilities | `src/lib/styles/{layout,utilities}.css` | arrangement (`stack`, `cluster`, `grid-2`) and a handful of behaviours (`tabular`, `spin`, `sr-only` companions) |
| component-scoped `<style>` | the `.svelte` file | what only that component needs: its grid template, a one-off metric, a delta on top of a block |

Inline markup classes are for **layout only** (flex/grid/gap/spacing/sizing;
section 8 has the exact list). Colour, type, borders, radius, shadows and
effects never appear inline.

### Cascade order (load-bearing, memorise it)

Tailwind's `utilities` layer > our `components` layer, and **Svelte scoped
styles compile unlayered, so they beat both** regardless of specificity.
Consequences:

- A scoped rule overrides a block with no `!important`, ever. `!important`
  is banned outright.
- To override a block *per instance*, set a custom property in the template
  (`style:--jt-accent={...}`) and read it in a scoped rule
  (`.job-card { border-left-color: var(--jt-accent) }`). This is the JobCard
  precedent; use it instead of specificity games.
- A scheme's `tokens` map is written as **inline style on `<html>`** and
  beats every stylesheet. A theme sheet cannot out-cascade its own token map.
- `table`, `table-row`, `table-cell` are also Tailwind display utilities;
  responsive-prefixed forms (`lg:table-cell`) are banned because the
  utilities layer silently beats the table block. Rules that must outrank a
  Tailwind utility go in `@layer utilities` (see `responsive-table`).

## 2. Tokens

Everything below lives in `tokens.css`. Primitives (`--color-p-*`) are
private to that file; reference the semantic roles only. Every colour role
flips in `.dark {}` — never write a `.dark` override in a component; use the
token and it flips for free.

### Surfaces and borders

| token | light | dark | use |
|---|---|---|---|
| `--color-page` | blue-tinted `rgb(232,240,255)` | `rgb(13,16,28)` | the body ground |
| `--color-surface` | `rgb(241,247,255)` | `rgb(22,28,45)` | panels, cards |
| `--color-surface-raised` | white | `rgb(30,37,58)` | flyouts, popovers, anything floating |
| `--color-backdrop` | black/50% | black/60% | modal and slide-over scrims |
| `--color-border` | primary @ 18% | primary @ 22% | the default hairline |
| `--color-border-strong` | primary @ 30% | primary @ 38% | form controls, floating panels |

### Text (exactly four roles)

`--color-text` (gray-900/100), `--color-text-secondary` (700/300),
`--color-text-muted` (500/400), `--color-text-faint` (400/500). If a fifth
shade feels needed, the answer is one of these four.

### Primary family

`--color-primary`, `--color-primary-hover`, `--color-on-primary` (text on a
primary fill), `--color-primary-text` (primary-coloured text on a plain
surface: blue-700 light / blue-400 dark), and the tint ladder
`--color-primary-tint-1/2/3` (5/10/20% mixes) for hover washes, selected
rows, and tinted fills. Tints are mixes of `--color-primary`, so they
re-tint automatically under every scheme.

### Tones (danger / warning / success / info)

Each tone is a triple: `--color-<tone>` (the solid fill), `--color-<tone>-soft`
(the tinted background), `--color-on-<tone>-soft` (text on that background).
Solid tone text on a plain surface uses the solid token; text inside a soft
box uses the on-soft token. Info aliases the primary family.

Dark solids are the Tailwind -400 row (danger `rgb(248,113,113)`, success
`rgb(74,222,128)`, warning `rgb(251,191,36)`).

The twelve literal names: `--color-danger`, `--color-danger-soft`,
`--color-on-danger-soft`; `--color-warning`, `--color-warning-soft`,
`--color-on-warning-soft`; `--color-success`, `--color-success-soft`,
`--color-on-success-soft`; `--color-info`, `--color-info-soft`,
`--color-on-info-soft`.

### Status scale (the job/drive state machine)

`--color-status-{ripping,transcoding,finishing,waiting,scanning,success,error}`.
These colour **state indicators**: dots, progress fills, status badges.
Schemes are free to redefine them wholesale (winamp maps them all onto its
LED palette), so never use them for ordinary text — that is what cost the
header counts their four distinct colours until they moved to the accents.

### Accents, frame, and the rest

- `--color-accent-1..4` (amber/blue/violet/cyan): fixed identity colours for
  disc-type icons, glyph tiles, and the header activity counts.
- `--color-frame-accent` / `--color-on-frame-accent`: the section-frame bar
  (per-instance override via `--frame-accent`).
- Radius scale on the `--radius` (8px) base: `--radius-sm` 2px,
  `--radius-md` 6px, `--radius-lg` 8px, `--radius-xl` 12px,
  `--radius-2xl` 16px. There is deliberately no 4px step.
- `--shadow-1/2`, `--motion-fast` / `--motion-base` + `--ease`,
  `--control-h` (36px) / `--control-h-sm` (28px),
  `--eyebrow-size` (11px) / `--eyebrow-tracking` (0.12em),
  `--font-display`, `--font-mono`, `--animate-indeterminate`.

### The type scale

Nine sizes are in deliberate use; pick from this table rather than
inventing a tenth. Line heights pair as unitless calc ratios (section 9).

| size | ratio | used for |
|---|---|---|
| 0.625rem (10px) | -- | `badge-sm` uppercase tags |
| 11px | -- | the eyebrow (`--eyebrow-size`, 0.12em tracking): panel titles, table headers, stat labels |
| 0.72rem | 1.6 | `code-block` |
| 0.75rem (12px) | `calc(1 / 0.75)` | the small role: meta rows, hints, badges, chips, `field-help/-error` |
| 0.875rem (14px) | `calc(1.25 / 0.875)` | the body role: controls, buttons, nav, cell text, `field-label` |
| 1rem | -- | `glyph-lg` marks |
| 1.125rem (18px) | -- | `modal-title` |
| 1.5rem (24px) | `calc(2 / 1.5)` | `page-title`, `stat-value` |

Two roles carry almost everything: 12px small and 14px body. A new size is
a design decision, not a convenience.

### Token rules

1. No literal colours (`rgb()`, `hsl()`, hex, named — `white` included)
   outside `tokens.css` and theme sheets. `color-mix()` **against a token**
   is fine.
2. The set is closed. A missing exact match is a **named collapse onto the
   nearest role**, recorded in the PR/DEVIATIONS — not a new token.
3. Radius, shadow and motion values come from tokens too, not just colours.

## 3. Naming

BEM-lite, kebab-case:

- **block**: `card`, `panel`, `btn`, `table`
- **element**: `block-element` — `card-header`, `panel-title`, `toggle-thumb`
- **modifier**: `block-modifier` — `btn-primary`, `alert-lg`, `tabs-pills`;
  tone modifiers are the bare tone name (`chip-danger`, never
  `chip-tone-danger`)
- every part of a block starts with the block's name; family members align
  (`table`, `table-header`, `table-row`, `table-cell`)
- **state is never a class.** Use `aria-*` (`[aria-selected="true"]`,
  `[aria-pressed]`, `[aria-checked]`, `[aria-expanded]`, `[aria-invalid]`),
  `data-*` (`[data-active]`, `[data-status]`, `[data-selected]`,
  `[data-busy]`, `[data-indeterminate]`), or pseudo-classes (`:disabled`,
  `:hover`, `:focus-visible`)
- component-scoped classes are prefixed with the component's own name
  (`session-builder-*`, `job-card-*`) and are **private**: themes and other
  components never reference them

## 4. Block vocabulary

One file per block in `src/lib/styles/components/`; each file's header
comment is the block's contract (name, elements, modifiers, state). Summary:

| block | elements | modifiers | state |
|---|---|---|---|
| `alert` | alert-title, alert-body | -info (default), -warning, -danger, -success, -lg | |
| `badge` | | -status, -danger, -warning, -success, -info, -sm, -imdb | [data-status] |
| `btn` | .chevron child | -primary, -danger, -warning, -ghost, -link, -icon, -sm | :disabled, [aria-pressed], [data-busy], [aria-expanded] |
| `card` | -header, -title, -body, -footer, -accent | -status | [data-status], [data-selected] |
| `chip` | | -danger, -warning, -success, -info, -sm | [aria-pressed], [data-selected] |
| `code-block` | | -scroll | |
| `field` | -label, -help, -error, -control | -row | [aria-invalid], :disabled, :focus-visible |
| `flyout` | -item, -divider | | [data-placement] |
| `glyph` | | -sm, -md, -lg; -danger, -warning, -success, -info | [data-glyph] |
| `list-row` | -lead, -main, -meta, -actions | -compact | [data-active], [data-disabled], [aria-expanded] |
| `modal` | -backdrop, -panel, -title, -body, -actions | -wide | |
| `nav` | -item, -badge, -logo | | [data-active] |
| `panel` | -title, -hint, -actions, -body, -section | -compact | [aria-expanded] on a button title |
| `progress` | -track, -fill (+ keep the `data-progress-*` attrs: theme hooks) | -sm | [data-indeterminate], [data-status], [data-bar] |
| `section-frame` | -bar-top, -bar-bottom, -sidebar, -body | | per-instance `--frame-accent` |
| `skeleton` | | -text, -block, -card | |
| `slide-over` | -panel, -header | | |
| `stat` | -label, -value | -danger, -warning, -success, -info, -muted | |
| `status-dot` | | | [data-status] |
| `table` | -header, -row, -cell, -sort | -compact, -right, responsive-table | |
| `tabs` | -tab | -pills | [aria-selected] |
| `text` helpers | eyebrow, mono, kbd | | |
| `toast` | -title, -body | -info, -danger, -warning, -success | |
| `toggle` | -thumb | -sm, -lg | [aria-checked], :disabled |

Notes with teeth:

- `.mono` is **size-neutral** (family + tabular-nums only); size comes from
  context.
- `field-control` is the **full-size** form control (`--control-h` floor,
  0.5rem vertical padding, tinted fill). A compact filter-bar control keeps
  the class and restates its own metrics in a scoped rule — the SessionsHub
  precedent. The tinted fill is correct for most call sites; a genuinely
  white original overrides to `--color-surface-raised` in scope.
- `progress-track` clips (`overflow: hidden`) to keep a rounded fill inside
  a rounded track; a theme whose decoration hangs outside opts out in its
  own sheet.
- A block earns its place by recurring across components. A look used once
  is a scoped style; promote it only when the second consumer appears.

## 5. Interaction, elevation, icons and structure

### Interaction states

- **Focus**: one global ring for everything - `:focus-visible { outline:
  2px solid var(--color-primary); outline-offset: 2px }` in `base.css`.
  Never remove it, never add a second style.
- **Hover** climbs the tint ladder: transparent -> `tint-1` (rows, ghost
  buttons) -> `tint-2` (selected/active). Filled controls darken to
  `--color-primary-hover`.
- **Disabled** is `opacity: 0.4` + `cursor: not-allowed`, from the block -
  never restated darker "for emphasis" (a Task 8 revert).
- **Busy** is `[data-busy="true"]` on the control, not a spinner class.
- **Reduced motion**: `base.css` zeroes `--motion-*` and caps every
  animation/transition under `prefers-reduced-motion`. Components need no
  handling of their own - but any keyframe animation a component adds must
  ride the motion tokens or a named keyframe, so the cap catches it.

### Elevation and stacking

Two shadows and two z tiers, frozen:

| tier | shadow | z-index | who |
|---|---|---|---|
| resting surface | `--shadow-1` | auto | `card`, `panel`, `stat` |
| floating | `--shadow-2` | 40 | `flyout` |
| overlay | `--shadow-2` | 50 | `modal`, `slide-over` (scrim included) |

No other `z-index` values exist; do not introduce one. A stacking problem
is solved by DOM order or a portal, not a bigger number.

### Iconography

Icons are `lucide-svelte`, colouring via `currentColor` - never a fill
token of their own. **Size is owned by the containing block**, not the
call site: `nav-item svg` 20px, `glyph svg` 16px, `btn-icon svg` 14px,
`btn .chevron` 14px (and it rotates on `[aria-expanded="true"]`). A
scoped rule targeting a lucide component instance needs `:global(` (Svelte
scoping cannot see into the instance) - which the lint allows only with an
explanatory comment on or before the line.

### Responsive structure

Three breakpoints are in deliberate use; do not add a fourth casually:

| width | what changes |
|---|---|
| 640px | `grid-2`/`grid-3` collapse to one column |
| 1024px (`lg:`) | the sidebar replaces the drawer; `responsive-table` stacks rows into label/value cards - give every cell `data-label="Column"` for its stacked caption |
| 1536px (`2xl:`) | the sidebar stats panel appears |

Wide content (tables, code) scrolls inside its own `overflow-x-auto`
container; the page body never scrolls sideways.

### Page states and microcopy

- **Loading** is `skeleton` shapes in the layout the data will fill -
  never a lone spinner on an empty page.
- **Empty** is a sentence in `--color-text-muted` saying what will appear
  and how to cause it ("No unenrolled drives. Plug one in and it appears
  here on the next scan.").
- **Errors** are an `alert alert-danger` (page-level: `alert-lg`) saying
  what failed and what to do; field-level errors are `field-error` plus
  `[aria-invalid="true"]` on the control.
- **Copy**: sentence case everywhere (themes uppercase for themselves);
  controls say what they do ("Scan for drives"); three dots `...` not the
  ellipsis character; no em-dashes, no unicode-as-UI, no emojis.

## 6. Layout helpers

`stack` (column flex, 1rem gap; `-sm` 0.5rem, `-lg` 1.5rem), `cluster`
(wrapping row, 0.5rem gap), `grid-2`/`grid-3` (collapse below 640px),
`page`, `page-header`, `page-title`, `split` (main + 20rem side column).
These are the one exception to role naming: they say what they arrange.

Beware two flexbox facts that bit repeatedly: a `stack` is a column flexbox,
so children **stretch full width** regardless of `display` (shrink one with
`align-self: flex-start`), and **flex gaps do not collapse** the way block
margins do — a child's `margin-bottom` adds to the gap instead of merging
into it.

## 7. Dynamic values

`style="..."` string attributes are banned. Dynamic styling flows through
custom properties: `style:--progress="{pct}%"`, `style:--jt-bg={...}`,
`style:--frame-accent={...}` — the block or scoped rule reads the var.
The only non-custom-property `style:` allowlist is Flyout positioning
(`top/left/right/bottom/max-height`).

Theme hooks are `data-*` attributes, not classes: `data-progress-track`,
`data-progress-fill`, `data-sidebar-stats`, `data-poster`,
`data-indeterminate`, `data-logo`, plus the state attributes. Keep them on
the elements even where the block class is present — schemes key off them.

## 8. Inline utilities: the allowed families

The style lint (`devtools/ui-neu-style-lint.mjs`, run in CI) is the
authority. Allowed in markup:

- spacing: `m*/p*-<n|px|auto>`, `gap*/space-*`
- display: `flex/inline-flex/grid/inline-grid/contents/block/inline/inline-block/hidden`
- flex/grid arrangement: `flex-row/col/wrap/nowrap/1/auto/none`, `grow/shrink`,
  `items-*/justify-*/self-*/place-*`, `col-span-*/row-span-*/order-*`,
  `grid-cols-<n>/grid-rows-<n>` (digits only)
- sizing: `w-full/h-full/min-w-0/min-h-0/max-w-*/w-auto/h-auto`
- text behaviour: `truncate/whitespace-*/break-*/overflow-*`
- `sr-only`; positioning: `relative/absolute/inset-0/…-0`
- responsive prefixes `sm:/md:/lg:/xl:` on any of the above

Banned: every colour/type/border/radius/shadow/effect family, `dark:`,
`hover:`/`focus:` variants, arbitrary values (`w-[13px]`), `style=`
attributes, `class:` directives, `:global(` without a same-line or preceding
comment, literal colours inside `<style>`, and responsive table display
utilities. The lint scans class attributes, class-expression strings, and
script literals. Target: **0 violations** (from 7,439 pre-cleanup).

## 9. Component-scoped styles

Scoped `<style>` is the right home for a component's own grid, a metric
delta on a block, or a look with exactly one consumer. Rules:

1. Never copy a block's declarations — use the block class and add deltas.
2. Original metrics win over a block default. When a migrated element's
   original padding/line-height/size differs from the block, restate the
   original in scope (and say so in a comment).
3. Line heights are **unitless ratios** written as `calc()` —
   `calc(1.25 / 0.875)` for text-sm, `calc(1 / 0.75)` for text-xs — never
   fixed lengths (they pin the line box when a theme resizes type) and never
   rounded decimals (`1.4286` computes to 19.9996px and the sub-pixel miss
   shifts dense pages).
4. No literal colours, no `!important`, no `dark:` — tokens flip on their own.

## 10. Theming (summary)

Themes target the block vocabulary, semantic tokens, real elements, and the
published `data-*` hooks — never component-scoped classes. A scheme's
`tokens` map lands as inline style on `<html>` (mode-resolved, cleared on
scheme switch); its stylesheet carries structural/decorative rules, and is
the one place literal scheme colours are legal. A theme rule that matches
nothing is a bug: delete it unless the markup exists under a new name. Full
contract: [ui-neu-theming.md](./ui-neu-theming.md).

## 11. Building a new component

Work through this decision tree for every visual element in the new
component, in order:

1. **A block already looks like this** -> use the block class, done.
2. **A block almost looks like this** -> block class + a scoped delta
   restating only what differs (with a comment naming the reason).
3. **Blocks compose into this** -> combine them with the layout helpers
   (`panel` + `stack` + `field` covers most forms).
4. **Nothing fits and only this component wants it** -> a scoped style,
   prefixed with the component's name.
5. **Nothing fits and a second component will want it** -> a new block
   (section 12).

### Component file anatomy

```svelte
<script lang="ts">
	// imports, then a typed Props interface, then $props()/$state()/$derived
	interface Props { job: Job; compact?: boolean }
	let { job, compact = false }: Props = $props();
</script>

<!-- markup: block classes + allowed layout utilities only;
     state as aria-*/data-*; dynamic values as style:--x -->
<div class="card" data-status={job.status} style:--jt-accent={accentVar}>
	<div class="card-header">
		<h3 class="card-title">{job.title}</h3>
		<span class="badge badge-status" data-status={job.status}>{label}</span>
	</div>
	<div class="card-body stack stack-sm">
		<div class="mt-0.5 flex items-center gap-2 job-card-meta">...</div>
	</div>
</div>

<style>
	/* scoped styles LAST in the file; every class prefixed job-card-*.
	   Overrides carry a comment naming the original value and why. */
	.job-card-meta { font-size: 0.75rem; line-height: calc(1 / 0.75); color: var(--color-text-muted); }
</style>
```

Conventions the codebase holds to:

- One component per file under `src/lib/components/` (route-private pieces
  live beside their `+page.svelte`); the colocated test is
  `ComponentName.test.ts` or `__tests__/ComponentName.svelte.test.ts`.
- `<style>` is the last section of the file. No `<style global>`.
- Interactive state is reflected in the attribute that styles it: the code
  sets `aria-pressed`/`data-selected`, the CSS keys off it - never a
  parallel `active` class.
- If a theme should be able to reach an element (a meter, a poster, a
  shimmer), give it the published `data-*` hook and keep it even where a
  block class is present.
- New copy follows the repo rules: no em-dashes, no unicode-as-UI, no
  emojis - comments included.

### Definition of done

```
cd services/ui-neu/frontend && npx vitest run && npm run check   # green
node devtools/ui-neu-style-lint.mjs --files <your files>          # 0
node devtools/ui-neu-parity.mjs capture current && ... diff       # for changes to existing screens
```

A brand-new screen has no parity baseline; a change to an existing screen
must hold its screens at 0 FAIL or record a named colour collapse in
`devtools/ui-neu-parity/DEVIATIONS.md`.

## 12. Growing the vocabulary

### Adding an element or modifier to an existing block

1. Add the rule to the block's file, inside its `@layer components` block,
   tokens only. Tone modifiers are bare tone names (`chip-danger`).
2. Extend the file's **header comment** - it is the block's contract.
3. Add the class to the block's list in
   `src/lib/styles/__tests__/blocks.test.ts` (`BLOCKS` registry).
4. Update the vocabulary tables here and in `ui-neu-theming.md`.

### Adding a new block

A block earns its place when the same look appears in a second component.
Promote the existing scoped style rather than writing a parallel one:

1. Create `src/lib/styles/components/<block>.css`:

```css
/* <block>: one line saying what it is.
   Elements: <block>-part, ...
   Modifiers: <block>-variant, ...
   State: [aria-...], [data-...], :disabled. */
@layer components {
	.<block> { /* tokens only; line-heights as calc ratios */ }
}
```

2. `@import` it from `src/app.css` (the index - keep it sorted with its
   neighbours).
3. Register it in `blocks.test.ts` `BLOCKS` with every class it declares -
   the test enforces the header comment, the class list, and the
   no-raw-colours rule from then on.
4. Convert the original consumers to the block class and delete their
   scoped duplicates.
5. Document it: the table in this guide and the block contract table in
   `ui-neu-theming.md` (themes may target it from that moment on - name
   its state hooks deliberately).
6. Run the full gates; parity must hold on every screen the converted
   consumers appear on.

### Adding a token

Almost never. The set is closed by design: a colour with no exact role
collapses onto the nearest one and the difference is recorded. A genuinely
new **role** (not a shade - a role, like `--color-frame-accent` was) needs
all of: a second consumer, a light and a dark value, a name following the
existing families, the `.dark {}` twin, an entry in `tokens.test.ts`, and
an amendment note in the spec section of this guide's tables.

### Adding a theme hook

When a component owns a themeable surface that block classes cannot
express, publish a `data-*` attribute (the `data-poster` pattern): add it
to the markup, list it in `ui-neu-theming.md`'s published-hooks list, and
keep it stable - schemes depend on it from the first release it ships in.

## 13. Enforcement

- `npm run lint:styles` — the whole-frontend scan, wired into the ui-neu CI
  lint job with its own test suite (`devtools/ui-neu-style-lint.test.mjs`).
- `node devtools/ui-neu-parity.mjs capture current && … diff` — the visual
  gate: 44 screens x 6 schemes x 3 viewports against a pinned baseline,
  0.5% pixelmatch threshold, allowed deviations named in
  `devtools/ui-neu-parity/DEVIATIONS.md`.
- `blocks.test.ts` / `tokens.test.ts` — the vocabulary and token contracts
  (every block file layered, headered, literal-free; the legacy aliases
  stay gone).
