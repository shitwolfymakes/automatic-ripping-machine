# Intended visual deviations

One bullet per screen file that is allowed to differ from the baseline, with the reason.
Format: `- \`<scheme>__<viewport>__<screen>.png\`: reason`

## Global: the header live-activity mask (not a per-screen entry)

`ui-neu-parity.mjs diff` zeroes one rectangle per desktop/wide image, identically in BOTH the
baseline and the current PNG, before running pixelmatch: the app header's live-activity cluster
(`.layout-activity-group`, the "N ripping / N transcoding / N notifications" counts). It stands for
one accepted, app-wide token collapse made in Task 5 - those three bespoke shades
(`text-blue-*`, `text-indigo-600`/`dark:text-indigo-400`, `text-amber-600`/`dark:text-amber-400`)
were mapped onto the semantic roles `--color-status-ripping`, `--color-status-transcoding` and
`--color-warning`. Because that cluster renders in the shared header, the collapse contributed a
constant slice of diff to EVERY desktop and wide screen in the suite, where it could both hide a
real per-screen regression under the 0.5% gate and inflate every screen's number by the same
amount. Masking it once, globally, is the honest accounting: the collapse is recorded here rather
than repeated in every screen's entry.

Bounds (`HEADER_ACTIVITY_MASK` in `devtools/ui-neu-parity.mjs`):

| viewport | rectangle (x, y, w, h) | how measured |
| --- | --- | --- |
| desktop (1280x900) | 597, 17, 280, 23 | `getBoundingClientRect()` on `.layout-activity-ripping` / `-transcoding` / `-notification` in the live dev server gives x 599-874, y 19-37; the flagged-pixel bounding box in `baseline/default__desktop__dashboard.png` is x 601-872, y 22-34. Padded 2px for glyph antialiasing. |
| wide (1536x900) | 597, 17, 280, 23 | identical - the cluster is left-anchored inside `.layout-stats-bar`, so its bounds do not move with viewport width (verified on `baseline/default__wide__dashboard.png`: same x 601-872, y 22-34). |
| mobile (390x844) | none | `.layout-stats-bar` is `hidden lg:flex`; at 390px it computes to `display: none` and the cluster does not render at all (`getBoundingClientRect()` returns a zero rect). No region to mask. |

Nothing else is masked. The mask is applied by filename viewport segment, so it covers every scheme.

Note: Group 1 (drawer-stats activity counts/disk meter) and Group 3 (settings-users dark-mode role
shades) were removed in Task 8 fix round 2 - their screens now pass under the re-seeded baseline and
parity-harness stats freeze.

## Group 2 (Task 6): transcoder progress-bar tone (2 screens, re-validated Task 11)

`ProgressBar.svelte`'s `color` prop (a literal Tailwind class) was dropped for `colorVar` (a CSS
value via `style:--progress-color`); `transcoder/+page.svelte`'s in-progress task bars used
`color="bg-indigo-500"`, and indigo has no token, so they now use
`colorVar="var(--color-status-transcoding)"` - bar colour `rgb(99,102,241)` (indigo-500) ->
`rgb(139,92,246)` (--color-status-transcoding). Re-validated after the Task 8 fix-round-2 baseline
re-seed and parity-harness stats freeze: the mobile screens now land under threshold (stats-bar
telemetry noise removed), so only the desktop screens - which show more in-progress bars per
screen - remain over the gate. Crop-verified: rows 756-781 of `default__desktop__transcoder.png`
show the identical indigo-vs-violet progress-fill collapse, no other regions differ besides the
shared pre-existing header band (rows 16-39, ~2000px, present on every desktop screen).

Task 11 re-validation (migrated `transcoder/+page.svelte` off Tailwind utilities entirely): the
worker-pool "in progress" tile (`transcoder-page-worker-card`/`-pulse`/`-heartbeat`) and the stats
strip's "In Progress" value (`transcoder-page-stat-value-progress`) carried the SAME literal indigo
hue in the original (`border-indigo-200`, `bg-indigo-50/50`, `bg-indigo-500`, `text-indigo-600`/
`dark:text-indigo-400`) with no shared token, so they collapse onto the identical
`--color-status-transcoding` role as the progress-bar fix above - the whole transcoder "in-progress"
domain now reads one consistent violet instead of indigo, which is more diff than the single
progress-bar collapse alone but the same class of accepted change, not a new regression. Both
desktop screens remain `allowed` (re-validated after fix round 1's `alert.css`/`table.css` fixes:
`4.371%`/`3.775%`, still crop-confirmed as the same tone
collapse family plus the header band); the migration also fixed a real layout bug the original
branch never had a screen to catch: the tab strip (`All/Queued/In Progress/Done/Failed`) used
`gap-1`/`px-4 py-2` with no `whitespace-nowrap`, so "In Progress" wrapped to two lines within its
own tab at narrow widths while the strip stayed on one row - `.tabs`/`.tabs-tab`'s own defaults
(tuned for the wider Settings strip) don't reproduce that, and needed `transcoder-page-tabs`/`-tab`
overrides restating the original gap/padding and allowing per-tab text wrap without a
container-level `flex-wrap` (which drops whole tabs to a second row instead of wrapping text within
one). Mobile screens dropped from failing at `4.275%`/`4.669%` (pre-fix) to `3.981%`/`4.095%`
(re-validated after fix round 1, `allowed`) - real, measured improvement, and still `allowed` rather
than `ok` on the residual indigo/violet collapse repeated across every job card in the list at
mobile's smaller total pixel count (the same tone family, more of the screen's area at 390px width
than 1280px).

- `default__desktop__transcoder.png`: worker-pool tile + "In Progress" stat value + progress-fill, bg/text/border-indigo-* -> --color-status-transcoding rgb(139,92,246)
- `dark__desktop__transcoder.png`: same
- `default__mobile__transcoder.png`: same collapse, plus a larger share of screen area at this viewport (job cards each show the "in progress" tone)
- `dark__mobile__transcoder.png`: same

## Group 4 (Task 8, fix round 2): settings-sessions residual (1 screen)

Fix round 1 addressed the controller's three findings: (1) `.btn-danger:disabled`/`.btn-warning:disabled`'s
`opacity: 0.6` override was removed from `button.css` - the base `.btn:disabled { opacity: 0.4 }` now
applies unmodified, matching the original's own `disabled:opacity-40`; (2) the recipe card's output-path
text used `overflow-wrap: break-word` instead of the original's `break-all` (`word-break: break-all`),
which wrapped one word earlier than the original at the same column width - fixed, wrap point now matches
byte-for-byte; (3) the BUILT-IN tag's `--color-warning-soft`/`--color-on-warning-soft` mapping measured
~40 sRGB units off the original's literal `bg-amber-100 text-amber-700` (baseline bg `rgb(254,243,198)` vs
the token's `rgb(255,251,235)`, baseline text `rgb(187,77,13)` vs the token's `rgb(146,64,14)`) - fixed with
literal Tailwind amber values (`rgb(254 243 199)`/`rgb(180 83 9)` light, `rgb(120 53 15 / .3)`/`rgb(252 211
77)` dark), the same literal-value precedent already used for the recipe box's black-alpha wash (no
warning-tone role in spec 5.1 matches amber-100/700 this closely). A fourth issue found during the fix
(not in the controller's list): the "Clone" button's border used `.btn`'s default `--color-border-strong`
(primary-blue-tinted by design), but the original was genuinely neutral (`border-gray-300 dark:border-
gray-600`) - fixed with the same literal-value approach.

`default__desktop 2.760%` and `dark__desktop 2.101%` (fix round 0) dropped to `0.531%`/`0.667%`;
`default__mobile` and `dark__mobile` passed at that point (`0.324%`/`0.497%`).

### Fix round 2 (baseline re-seed + parity-harness stats freeze)

The baseline was re-seeded from `441d35d2` and the harness gained a network-level intercept plus a
DOM backstop that freeze `BottomStatsBar`/`SidebarStats` telemetry to fixed placeholder figures on
every capture (`devtools/ui-neu-parity.mjs`'s `freezeLiveStats` and the `**/api/system/resources`
route fulfil), removing the "live stats bar" band entirely from the accounting below. Re-running the
full diff after the re-seed: `default__desktop__settings-sessions.png` now passes (`0.487%`, was
`0.531%`); `dark__mobile__settings-sessions.png` also passes (`0.471%`). Only one screen remains
over the 0.5% gate:

  `dark__desktop__settings-sessions.png` at `0.614%` (7074 / 1,152,000 px). (Historical note from
  fix round 2; the live entry for this file is the fix-round-3 one below.)

Per-row hotspot histogram (pngjs, `r>200 && g<100 && b<100`) crop-verified against the baseline:

| band (y) | pixels | cause |
| --- | --- | --- |
| 16-39 | 1916 | app header/notification-bell region - pixel-identical crop confirms this is the same pre-existing header noise present on every dark-desktop screen (e.g. the transcoder screen's own rows 16-39/209-228 show the identical counts), not caused by this task |
| 176, 209-228 | 373 | same header band, notification-bell/badge sub-pixel antialiasing - crop-verified identical between baseline and current |
| 289-302 | 457 | sidebar "Files" nav row - unrelated to sessions/presets content, sub-pixel antialiasing on the sidebar's own text, crop-verified visually identical |
| 486-584, 640-738, 794-856 (three repeated card bands) | ~4300 | recurring per-card pattern: the recipe strip's `rgb(0 0 0 / 0.1)`/`rgb(0 0 0 / 0.2)` literal black-alpha wash (byte-identical to Tailwind's own `bg-black/10`/`bg-black/20`) and the disabled "Delete" button's accepted base-opacity fade (`.btn:disabled { opacity: 0.4 }`, per the fix-round-1 controller ruling that dark-mode legibility of this control is out of scope) - crop-verified the "RIP PRESET / TRANSCODE / OUTPUT PATH" recipe row text and layout are pixel-identical, the diff is compositing/antialiasing noise on the alpha wash repeated across three session cards |

No structural difference remains: crop comparison at every flagged band shows identical text,
layout, and element positions between baseline and current. The header/sidebar bands (approx.
2750 px, 0.239%) are pre-existing and not caused by this task; the remaining card-content bands
(approx. 4300 px, 0.373%) are the same accepted token collapse (recipe alpha wash) and controller-
ruled disabled-button fade already on record from fix round 1, now re-confirmed against the fresh
baseline.

  (Historical note from fix round 2: the residual was the recipe box's black-alpha wash and the
  disabled-Delete-button base-opacity fade, both crop-verified. Superseded by the fix-round-3 entry
  below, which is the live one for this file.)

### Fix round 3 (raw colours removed from scoped styles)

A spec-compliance review found literal `rgb()`/hex/`white`/`black` values in scoped `<style>` blocks,
which the strict token set forbids outright ("no token matches" is not an exemption - the nearest
role is used and any visible gap is recorded here). Fixed in `PresetRow.svelte`, `SessionCard.svelte`,
and `PresetEditor.svelte`:
- BUILT-IN tag: literal Tailwind amber (`rgb(254 243 199)`/`rgb(180 83 9)` light,
  `rgb(120 53 15 / .3)`/`rgb(252 211 77)` dark, added in fix round 1) replaced with
  `--color-warning-soft`/`--color-on-warning-soft` in both files.
- Clone button: literal neutral grey border/text (`rgb(209 213 219)`/`rgb(75 85 99)` light,
  `rgb(75 85 99)`/`rgb(209 213 219)` dark, added in fix round 1) replaced with bare `.btn` (its default
  `--color-border-strong`/`--color-primary-text`) in both files, per the migration reference's line-70
  ruling that a neutral border has no token in spec 5.1.
- The `data-media="data"` dark-mode pill wash and the recipe strip's `bg-black/10`/`bg-black/20` washes:
  literal `rgb(55 65 81 / 0.3)` / `rgb(0 0 0 / 0.1)` / `rgb(0 0 0 / 0.2)` replaced with
  `color-mix(in srgb, var(--color-backdrop) N%, transparent)` (a fixed-black-anchored token in both
  themes, scaled to reproduce the original alpha: 20%/33% of `--color-backdrop` reproduces `/10`/`/20`
  almost exactly; an initial attempt using `--color-text` was wrong for dark mode, since `--color-text`
  is near-white there and lightened rather than darkened the surface - caught by a 14-17% FAIL on the
  first post-fix capture, corrected before this entry was written).
- PresetEditor's undo toast: the literal `rgb(17 24 39)`/`white` solid bar replaced with the `toast`
  block (`class="toast"`, message + Undo button wrapped in `toast-body`), keeping only the fixed
  bottom-centre position scoped.
- PresetEditor's Retry-button hover (`color-mix(in srgb, var(--color-warning) 85%, black)`, also a raw
  colour inside `color-mix`): replaced with `filter: brightness(0.85)` - no `--color-warning-hover`
  token exists (unlike `--color-primary-hover`), and mixing against a text token would flip direction
  between light/dark, so a brightness filter reproduces the darkened solid fill without any literal
  colour value.

Full diff after these fixes: `default__desktop__settings-sessions.png` `0.530%` and
`dark__mobile__settings-sessions.png` `0.531%` are now marginally over the 0.5% gate (both were `ok`
at `0.487%`/`0.471%` before this round); `dark__desktop__settings-sessions.png` stays `allowed` at
`0.666%` (was `0.614%`). Crop comparison at every newly-flagged band confirms the increase is exactly
the two visible collapses above (the BUILT-IN badge is a touch less saturated than the literal amber
it replaces; the Clone button border is now primary-blue-tinted instead of neutral grey) plus the
same pre-existing header/tab-strip sub-pixel noise already on record - no other region differs.

- `dark__desktop__settings-sessions.png`: BUILT-IN badge amber-100/700 -> --color-warning-soft/--color-on-warning-soft, and its `rounded` (4px) -> badge-sm's --radius-sm (2px): the radius scale has no 4px step (2px/6px), so both the shade and the radius are named collapses on the same 20px badge; Clone button gray-300/600 -> btn defaults (--color-border-strong/--color-primary-text); recipe strip bg-black/10 and /20 -> color-mix(--color-backdrop 20%/33%, transparent); disabled Delete button .btn:disabled opacity 0.4 over .btn-danger's already-30%-alpha-mixed border/text
- `default__desktop__settings-sessions.png` (1.788%): the same four collapses as the entry above, repeated once per visible session card down the page (Task 8b's own surface, the SessionsHub filter bar and TYPE chip row, was made geometry- and fill-exact against baseline by DOM measurement; the residual mass sits on the SessionCard rows, whose components the 8b commits never touched).
- `default__mobile__settings-sessions.png` (2.449%): same; the mobile ratio runs higher because each card fills the narrow viewport, so the per-card collapses cover a larger pixel fraction.
- `dark__mobile__settings-sessions.png` (2.826%): same, dark twin.

## Group 5 (Task 9, fix round 1): notifications residual after the inbox-card and channel-column rework (6 screens)

Fix round 1 restored the inbox page to `panel` cards in a `stack` (matching the original's rounded/
bordered/shadowed cards with gaps, in place of Task 9's incorrect `list-row` conversion) and the
channel-list actions column to the original's fixed `64px` (in place of Task 9's `auto`, which
resolved independently on the header vs each row and misaligned them). Both root causes are gone -
`default__desktop__notifications.png` and both `settings-notifications` desktop screens are back to
`ok` - and every screen below dropped by 60-90% from its Task 9 number. The two real bugs found and
fixed along the way, both shared patterns worth naming since they recur wherever `.btn`/`.btn-sm` is
used with a non-`.btn`-standard text size:

1. **`ring-1 ring-primary/25`, not a border.** The inbox page's Dismiss/Dismiss-All buttons and
   NotificationsTab's "+ Add channel" button were `ring`-styled in the original (a `box-shadow`, no
   layout-box height) but `.btn`'s own 1px `border` (real box height) made them 2px taller, which
   pushed every sibling and everything below down by that same 2px, compounding down the whole page.
   Fixed with `border: 0` (+ `box-shadow: 0 0 0 1px var(--color-border-strong)` where the ring's own
   look needed reproducing).
2. **`.btn-sm`/`.btn-link` set `font-size` but not `line-height`.** `.btn`'s own `line-height: 1.25rem`
   survives on a button whose original size class (`text-xs`, 1rem bundled line-height) wasn't
   `.btn`'s own default, adding another 2-4px per occurrence. Fixed on NotificationsTab's
   "+ Add channel" and BashScriptFields' "Refresh list"/"View script" buttons with an explicit
   `line-height: 1rem` override.
3. **`panel-section`'s own background (`--color-primary-tint-1`, a translucent `color-mix`) is not
   `bg-page`** (an opaque flat colour) in light mode, only in dark (where the reference's own mapping
   table row is written for). Fixed on NotificationsTab's toolbar and empty-state boxes with an
   explicit `background: var(--color-page)` override; this is a real gap in `panel-section`'s own
   documented `bg-page` mapping (spec row 60) that any other light-mode `bg-page`-via-`panel-section`
   consumer should be re-checked against, not something specific to notifications.

### Fix round 2 (btn-icon border, dark tone solids, header mask)

Fix round 2 removed three of the round-1 causes outright, and four of round 1's six entries plus two
of Task 8's are deleted above because their screens now measure `ok`:

1. **`.btn-icon` kept `.btn`'s 1px border box** (`border-color: transparent`, so invisible but still
   2px of layout width and height per button). The originals were `rounded p-1.5` with no border at
   all, so every icon-button cluster in the app - the header's Settings/Log-out/Theme trio, the
   channel-row Edit/Send-test/Expand trio - sat 1px off per button and pushed its neighbours. Fixed
   with `border: 0` in `src/lib/styles/components/button.css`; the 0.375rem padding already equalled
   the original's `p-1.5` (6px) exactly, so no padding adjustment was needed. Re-verified across all
   88 default+dark screens: the header icon cluster is now aligned (crop-verified on
   `dark__desktop__settings-sessions.png` rows 12-44, x 960-1260) and no Task 5-8 consumer regressed.
2. **Dark-mode `--color-danger` and `--color-success` were a shade too light** (red-300 / green-300).
   The spec was amended to red-400 `rgb(248, 113, 113)` and green-400 `rgb(74, 222, 128)`;
   `--color-on-danger-soft` / `--color-on-success-soft` keep the -300 values, which is what those
   on-soft roles are for.
3. **The inbox card's message text used the wrong dark-mode role.** The original was
   `text-gray-600 dark:text-gray-400`; `--color-text-secondary` is gray-700 in light (correct) but
   gray-300 in dark (a shade too bright - measured `rgb(209,213,219)` rendered against the baseline's
   `rgb(153,161,175)`). `--color-text-muted` is the role that is gray-400 in dark, so
   `.notifications-page-row-message` now takes a `:global(.dark)` override to it. This is the same
   unqualified-Tailwind-colour trap already recorded in the task-7 lessons, not a new class of bug.

The `white-space: normal` wrap theory from round 1 was re-measured and disproved: the badge's amber
pill occupies exactly x 200-244, y 80-115 in BOTH the baseline and the current
`default__mobile__notifications.png` (and x 201-243 in the dark pair), so it wraps to two lines
identically in both and there is no width regression to fix. What actually differs there is the
fill colour, below.

What remains on the two screens still over the gate is two specific, named token collapses:

- **`bg-amber-500` with no `dark:` variant, mapped onto `--color-warning`.** The inbox page's
  unseen-count badge (`.notifications-page-unseen-badge`) and each card's unseen dot
  (`.notifications-page-row-dot`) were a bare `bg-amber-500` in the original, which keeps the same
  shade in both modes. `--color-warning` does not: it is amber-500 `rgb(245,158,11)` in light but
  amber-400 `rgb(251,191,36)` in dark, so the badge and dots read visibly lighter in dark mode
  (sampled `rgb(254,157,39)` baseline vs `rgb(251,193,70)` current at x 210, y 85). No warning-family
  role in spec 5.1 is amber-500 in dark, and `--color-status-finishing` (which is) is a job-status
  role, semantically wrong for an unseen-notification count - so this is the accepted nearest-role
  collapse, not an invented token. It accounts for 1206 of the 2513 flagged pixels on
  `dark__mobile__notifications.png`, plus the antialiasing of the badge's own white "3 new" glyphs
  against the changed fill.
- **`dark:text-white` mapped onto `--color-text`** (gray-100 `rgb(243,244,246)`, not pure white). The
  app-wide Task 5 collapse, visible here on the "Notifications" page heading and, on the add-bash
  screen, the "Service (Apprise)" / "Enable notifications" labels - 466 of the 1684 flagged pixels on
  `dark__mobile__settings-notifications-add-bash.png`. Crop comparison at every flagged band on both
  screens shows identical glyph shapes, positions, box sizes and layout; only the text shade differs.

- `dark__mobile__notifications.png`: unseen-count badge + per-card unseen dots, bg-amber-500 (no dark variant) -> --color-warning, which is amber-400 rgb(251,191,36) in dark rather than amber-500 rgb(245,158,11); page heading dark:text-white -> --color-text gray-100
- `dark__mobile__settings-notifications-add-bash.png`: "Service (Apprise)" / "Enable notifications" labels, dark:text-white -> --color-text gray-100; RECOMMENDED badge bg-primary/15 -> color-mix(--color-primary 15%, transparent) against the original's own oklch primary tint

## Group 4 (Task 10): dashboard and job-detail (9 screens)

DiscReviewWidget's action row (Info/Search/Apply session/View details/Cancel/Start rip),
ActiveJobRow's Details pill, and the JobActions Abandon/Delete pills were originally
`bg-primary/5 text-gray-700 ring-primary/25` (or an unbordered filled tint), not `.btn`'s
outlined default; matching them required per-button `border: 0` overrides (the original ring is
a `box-shadow`, not layout space, and several buttons had no border at all) plus explicit
`padding`/`font-size`/`line-height` restated per original `px-*/py-*/text-*` value, since `.btn-sm`
does not match every button whose original was `text-sm` rather than `text-xs`. A companion
sweep restored the Tailwind-bundled line-height (text-xs 1rem, text-sm 1.25rem, text-base 1.5rem,
text-lg/text-xl 1.75rem) on every scoped `font-size` declared at those exact steps, since dropping
a Tailwind text-size utility silently drops its line-height too and the resulting 1-2px-per-row
drift compounds down a tall page. That work (commit `fix(ui-neu): dashboard and jobs parity: button
box-model, line-height`) brought this group from 14 screens failing at 3-8% down to 9 screens at
0.5-1.3%, all now genuine small token-shade collapses rather than layout bugs:

- **`bg-primary/10` / `dark:bg-primary/15` mapped onto the single fixed `--color-primary-tint-2`.**
  Per the migration reference's own token table this pairing collapses onto tint-2, which is a flat
  10% mix in both modes; the original's dark variant was a stronger 15% wash. Visible on the disc
  badge pills (drive/disc-type/video-type chips) in `DiscReviewWidget` and the matching pills
  elsewhere in this group - a few RGB units per pixel, not a shape or position difference.
- **`text-gray-700` / `dark:text-gray-200` mapped onto `--color-text-secondary`** (gray-700 light,
  gray-300 dark) rather than gray-200. Affects the DiscReviewWidget action-row button text in dark
  mode; readable and the correct role family, just one shade off the original's dark value.
- **IMDb badge (`bg-yellow-400 text-black`) collapsed onto `--color-warning` / `--color-on-frame-accent`**
  (see `badge.css`'s `.badge-imdb` header comment) since no yellow-gold brand token exists and the
  strict token set forbids a literal colour; amber-500 is close in hue to IMDb's yellow-gold but not
  identical, and `--color-warning` itself shifts to amber-400 in dark mode where the brand mark
  should stay fixed. Visible wherever an IMDb link badge renders in this group.

These three collapses, repeated across the multiple job cards/rows the seeded dashboard renders,
account for the remaining sub-1.5% diffs in this group (the drawer screens render the same
dashboard underneath the mobile nav drawer). Crop comparison at every flagged band on every screen
in this group shows identical glyph shapes, positions, box sizes and layout - only fill/text shade
differs, confirming no further layout fix is available without inventing a token.

**Fix round 2 correction**: `default__desktop__job-detail.png` and `dark__desktop__job-detail.png`
were carrying a real layout bug folded into their token-collapse numbers, not noise: `LogView.svelte`'s
service chip (`.log-view-chip`, migrated from the original's `text-[10px]`) dropped Tailwind's own
default line-height ratio for that arbitrary font-size (`1.3333`, i.e. 4/3 - confirmed by measuring
the compiled utility's computed `line-height` directly, `13.3333px` at `font-size: 10px`), not the
ambient `1rem`/16px the chip's ancestor container carries. Losing that ratio shrank the chip's own
box by ~3px, and since the row is `align-items: flex-start` (the chip is the row's tallest child),
every log line rendered ~3px shorter than baseline - compounding to ~6-7px over two visible rows in
the job-detail LogView panel (measured via a pngjs row-band scan at x=560, y625-710: baseline row
pitch ~21px, pre-fix current row pitch ~24px). Fixed with an explicit `line-height: 1.3333333333333333`
on `.log-view-chip`; row pitch now matches baseline exactly (~21px) and the panel's own bottom edge
is within 2px of baseline (down from 7px), the residual now consistent with the two token collapses
below rather than a distinct bug. `default__desktop__job-detail.png` dropped from 1.308% to 0.792%;
`dark__desktop__job-detail.png` from 0.904% to 0.805%. Both remain `allowed` (above the 0.5%
threshold) on the genuine collapses named below, not on any remaining layout difference.

- `dark__desktop__dashboard.png`: DiscReviewWidget action-row buttons, bg-primary/10 dark:bg-primary/15 -> --color-primary-tint-2 (flat 10%); button text dark:text-gray-200 -> --color-text-secondary gray-300
- `dark__desktop__job-detail.png`: same DiscReviewWidget/ActiveJobRow token collapses as above, reached via the header/action rows and disc-type pills on this page (LogView row-height bug fixed in fix round 2; residual is token-collapse only)
- `dark__mobile__dashboard.png`: same DiscReviewWidget action-row and disc pill token collapses as `dark__desktop__dashboard.png`
- `dark__mobile__drawer-menu.png`: dashboard renders underneath the mobile nav drawer; same token collapses as `dark__mobile__dashboard.png`
- `dark__mobile__drawer-stats.png`: dashboard renders underneath the mobile nav drawer; same token collapses as `dark__mobile__dashboard.png`
- `dark__wide__dashboard.png`: same DiscReviewWidget action-row and disc pill token collapses as `dark__desktop__dashboard.png`
- `default__desktop__job-detail.png`: IMDb badge bg-yellow-400 text-black -> --color-warning / --color-on-frame-accent (amber-500 close in hue to IMDb yellow-gold, not identical); LogView row-height bug fixed in fix round 2, residual is this token-collapse only
- `default__mobile__dashboard.png`: DiscReviewWidget disc pills, bg-primary/10 -> --color-primary-tint-2, a few RGB units off the original's own flat 10% mix at this viewport's antialiasing
- `default__mobile__drawer-stats.png`: dashboard renders underneath the mobile nav drawer; same token collapse as `default__mobile__dashboard.png`

## Group 5 (Task 11): login guest button + logs row divider (2 screens over gate)

Task 11 migrated files, logs, transcoder, setup, login, and change-password to the block
vocabulary. The initial pass left 15 screens failing; a controller review of
`default__desktop__files`/`login` ruled the files/logs/transcoder/setup magnitudes were layout
regressions, not collapses, and login was a colour-only collapse plus 1px. Fix round 1 addressed
every named finding:

1. **`alert-lg` modifier added to `alert.css`** (padding 1rem, radius `var(--radius-lg)`, declared
   in `blocks.test.ts`) for every page-level banner whose original was `rounded-lg p-4` (the default
   `alert`'s own `0.5rem 0.75rem` is tuned for inline messages, not full-width banners) - applied
   across files/transcoder/setup/IngressBrowser/ImportWizard's error and warning boxes. Several
   further padding mismatches (the files page's own Warning/read-only/feedback banners, each a
   distinct original `px-*/py-*` pair not matching either the default or `alert-lg`) got scoped
   overrides restating the exact original value.
2. **`alert.css`'s own base rule was missing an explicit `line-height`** for its `font-size:
   0.875rem` (Tailwind's own `text-sm` bundles `1.25rem`); a 2-line banner drifted 2px per box from
   the browser's own ambient line-height instead, compounding down the page - this is why
   `default__desktop__files.png` at 1.24% turned out to be a real, fixable app-wide bug, not a
   files-page-only colour issue. Fixed with an explicit `line-height: 1.25rem` on `.alert`/`.alert-info`.
3. **The files page's icon-button toolbar cluster** (Orphan folders/Transcoder cleanup/New
   folder/Refresh) was `rounded-lg p-2` in the original; `.btn-icon`'s own `padding: 0.375rem`
   default (tuned for a different consumer) put every button ~4px closer together per side. Fixed
   with a `files-page-toolbar-btn { padding: 0.5rem }` override restoring the original spacing (the
   icon's own size was already correct - `h-5 w-5` is an allowed inline utility on an icon inside
   `btn-icon` and already wins over `.btn-icon svg`'s smaller default).
4. **The logs table header row was missing its border entirely** - an earlier pass had removed
   `table-header`'s own `border-bottom` on the mistaken visual read that the original was borderless;
   the true original was `border-b border-gray-200 dark:border-gray-700`, a real (if faint) line.
   Restored by dropping the `border-bottom: 0` override, letting `table-header`'s own default
   (`--color-border`) apply.
5. **A genuine, systemic bug found while investigating the logs/files mobile magnitude**:
   `.table-row`, `.table-cell`, and bare `.table` are not just this block's class names - `table`,
   `table-row`, and `table-cell` are also valid CSS `display` keywords, and Tailwind v4 auto-generates
   a utility class for every keyword value of `display`. Those Tailwind-generated utilities land in
   Tailwind's own `utilities` layer, which has higher priority than this block's `components` layer
   regardless of selector specificity or source order, so the bare Tailwind utility of the identical
   name silently won over `table.css`'s own `display: block !important`-free responsive-table rule -
   confirmed via Chrome DevTools Protocol's `CSS.getMatchedStylesForNode`, which showed a second,
   Tailwind-authored `.table-row { display: table-row }` rule (not textually present in any of this
   repo's own `.css` files) outranking both this block's own `.table-row` rule and the
   `@media`-scoped `.responsive-table tr` rule. This is why `responsive-table`'s documented mobile
   stacking never actually worked for ANY consumer app-wide (dashboard, job-detail, files, logs -
   every task that has used this modifier since Task 8), not something introduced by this task, but
   fixable within it: added `!important` to the six `display: block` declarations in `table.css`'s
   `@media (max-width: 1023.98px)` block, which reverses layer priority per spec and lets the
   earlier-declared `components` layer win. Verified against the TRUE original `app.css` (pre-dating
   the whole block-vocabulary migration): its own copy of this exact `responsive-table` CSS is
   byte-identical to this block's (proving the baseline screenshots already reflect this exact,
   correctly-stacking behaviour, and the `!important` fix is a restoration, not a new design).
   Fixing this dropped `default__mobile__logs.png` from 5.06% to 1.71% and `default__mobile__files.png`
   from ~2% to 0.02% in one change, and is very likely the actual root cause behind several
   `allowed`-but-large mobile numbers other tasks had already accepted as unfixable token collapses -
   any future task revisiting a `responsive-table` consumer's mobile screen should re-measure now
   that this is fixed rather than assume the old magnitude still applies.
6. **Login's inputs/buttons and the setup page's error alert both needed ambient-body-size
   overrides**: the login inputs needed `border-color: var(--color-border)` (not `field`'s own
   `--color-border-strong`) and `background: transparent` (the original had no `bg-*` class at all,
   confirmed live against the swapped-in true pre-task-11 markup); its buttons and the setup page's
   "Failed to load setup status" alert all sit OUTSIDE any `text-sm`-classed ancestor in their
   originals, so they render at the browser's ambient `1rem`/`1.5rem`, not `.btn`'s or `.alert`'s own
   `text-sm` default - fixed with explicit `font-size: 1rem; line-height: 1.5rem` overrides, which
   closed the login mobile and setup screens' remaining 1-3px height/position gaps entirely (both
   pages are now `ok` on every scheme).

After all of the above, `files` and `setup` are `ok` on every scheme, and `transcoder` (this task's
part of it) carries only the already-accepted indigo/violet collapse re-validated above. `login` and
`logs` still show numbers over the 0.5% threshold on several screens; every one is a single named
colour-only gap - no layout/position difference remains at any of them (measured and crop-verified
per screen below):

- **Login's "Continue as Guest" button**: the original was a solid `bg-amber-500` fill with **no**
  `dark:` variant, so it rendered the identical amber-500 `rgb(245,158,11)` in both light and dark
  mode. `--color-warning` does not: it is amber-500 in light but amber-400 `rgb(251,191,36)` in dark
  (same family of collapse as the notifications-page unseen-badge entry above), so the dark-mode
  button reads visibly lighter/more saturated yellow than baseline. No warning-family role in spec
  5.1 is amber-500 in dark; a literal colour value was ruled out by the Task 8 fix-round-3
  controller precedent ("no token matches" is not an exemption). Fix round 3 correction: an earlier
  pass of this entry claimed the button box itself was pixel-identical to baseline aside from hue;
  a task review measured this false (`dark__mobile__login.png` row 570 was amber in current, page
  background in baseline - a genuine 1px-taller submit button pushing the guest button down by the
  same amount). Root cause: `.login-page-submit` (`btn btn-primary`) never got a `border: 0`
  override - `.btn-primary`'s own 1px border is invisible (same colour as the fill) but still
  occupies 2px of layout height, and the original submit button had no border/ring class at all
  (the exact pattern already on record for other buttons with a bare `bg-*-600 text-white` string).
  Fixed with `border: 0` on `.login-page-submit`; both buttons now measure pixel-exact against
  baseline (`474-513`/`530-569` in both baseline and current at x=200 in `dark__mobile__login.png`).
  This single button accounts for the large majority of both dark login screens' remaining flagged
  pixels, purely the fill-hue collapse now that the box model matches exactly
  (`default__desktop__login.png` and `default__mobile__login.png` are both `ok`).
- **Logs table row divider**: the header row's original border was `border-gray-200`/
  `dark:border-gray-700`; the data rows' was `border-gray-100`/`dark:border-gray-800` - a lighter
  pairing, by design, distinguishing the header from its data. `table-row`'s own `--color-border`
  (primary at 18%/22%) is the shared block default every other migrated table uses successfully, and
  is the correct mapping for the HEADER pairing (confirmed: restoring the header's border with
  `--color-border` alone closed most of the desktop gap in fix round 1). The DATA-row pairing does
  not match `--color-border` as closely in dark mode (baseline samples `rgb(54,65,83)`, close to the
  raw `--color-p-gray-700` primitive but with no semantic border-family role resolving to it in dark;
  `--color-border-strong` was tried empirically and measured worse, `rgb(22,48,107)`, since it mixes
  against `--color-primary` rather than a neutral grey), and in light mode the original's flat, literal
  `rgb(243,244,246)` (`border-gray-100`) cannot be reproduced by any `color-mix` percentage against
  either theme's page background at a ratio that also matches dark mode's target (checked
  numerically: no single mix percentage of any text/border token hits both targets). No border-family
  token in spec 5.1 reproduces a genuinely neutral gray-100/800 pairing distinct from the
  primary-tinted `--color-border`/`--color-border-strong` pair (the same "no neutral role exists" gap
  already on record for `.btn`'s default border and other components); the block default is kept and
  this specific shade is accepted as a named collapse. Crop- and pixel-verified at every flagged row:
  text, badges, and row heights (197px per stacked row on mobile, exactly matching the un-modified
  original CSS) are byte-identical between baseline and current; only this one border's RGB differs.
  The app-wide `dark:text-white` -> `--color-text` gray-100 collapse (Task 5) also contributes on the
  dark screens, visible on job title text.

- `dark__desktop__login.png` (1.095%, re-measured after fix round 3's border:0 fix): "Continue as Guest" button, bg-amber-500 rgb(245,158,11) (no dark: variant) -> --color-warning, which is amber-400 rgb(251,191,36) in dark
- `dark__mobile__login.png` (3.515%, re-measured after fix round 3): same
- `default__desktop__logs.png` (1.112%): table header/data-row divider colour, border-gray-200/700 (header, now matches --color-border) and border-gray-100/800 (data rows) -> --color-border
- `default__mobile__logs.png` (1.709%): same data-row divider colour gap, repeated down every stacked card in the list (now correctly stacking after the responsive-table fix above)
- `dark__desktop__logs.png` (0.513%): same divider colour gap, plus the same pre-existing header-band antialiasing noise on record for every dark-desktop screen since Task 8 (rows 16-39/132-145/209-228, crop-confirmed identical to the `settings-sessions`/`transcoder` entries above)
- `dark__mobile__logs.png` (2.122%): same divider colour gap, plus the app-wide dark:text-white -> --color-text gray-100 collapse on job title text

## Group 7 (post-Task-13 winamp stats pass): broken-baseline screen

- `winamp-97__mobile__drawer-stats.png` (51.687%): the baseline shows the drawer's MENU tab (the
  nav-item list) where the screen is defined to show the STATS tab. Re-seeded directly from a
  pristine 441d35d2 worktree and it still captures the Menu tab: the drawer's Stats toggle fails
  to activate in the pre-branch tree under this scheme, so this baseline records a broken
  interaction, not a look. The current capture correctly shows the Stats tab (services list,
  resource meters). Content differs by tab state, not styling; not reproducible by any CSS change,
  and re-creating it would mean re-breaking the toggle.
