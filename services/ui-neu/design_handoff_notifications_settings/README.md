# Handoff: ARM Notifications Settings Redesign

## Overview

Redesign of the **Notifications** tab in the ARM (Automatic Ripping Machine) UI settings page. The current implementation (see `frontend/src/routes/settings/+page.svelte` in the [`uprightbass360/automatic-ripping-machine-ui`](https://github.com/uprightbass360/automatic-ripping-machine-ui) repo) mashes the channel list and "add channel" form into one long flat form. This redesign:

- Splits the screen into a **compact channel list** (one row per channel) and a **unified Add Channel form** that opens above the list.
- Adds a status dot, type glyph, last-delivery timestamp, and inline enabled-toggle to each row.
- Lets users click any row to expand an inline editor with the same form sections used when adding.
- Surfaces overview stats (total channels, events delivered in 24h, issues, subscribed events) at the top of the section.
- Provides a quick test-send action with toast feedback, and a confirm dialog for deletion.

The user explicitly directed: match the existing ARM dark blue/violet theme exactly, single unified add form (not a multi-step wizard), featured services pinned above categorized services in the picker dropdown, checkbox grid for events, templates collapsed by default with expand-per-event, compact rows in the channel list, fully interactive (add / edit / delete / test with state).

## About the Design Files

The files in this bundle are **design references created in HTML** — a React prototype showing intended look and behavior. They are not production code to copy directly.

The target codebase is **SvelteKit + Tailwind CSS v4**, located at:

- Repo: `uprightbass360/automatic-ripping-machine-ui`
- File to update: `frontend/src/routes/settings/+page.svelte` (the notifications section)
- Theme system: `frontend/src/app.css` (uses Tailwind v4 `@theme` directive — see `THEME_TEMPLATE.md` in the repo root)
- API client: `frontend/src/lib/api/channels.ts`
- Existing components live in: `frontend/src/lib/components/`

The task is to **recreate the prototype's UX and visual treatment as native Svelte 5 components**, using the existing Tailwind theme tokens (so the redesign automatically picks up whatever color theme the user has selected — Synthwave, Hacker, etc.) and the existing `apiFetch` client. Do **not** hardcode the prototype's literal hex values; map them to the closest existing theme token.

## Fidelity

**High-fidelity (hifi).** Pixel-perfect mockup with final colors, typography, spacing, and interactions. All states (hover, focus, expanded, disabled, error, loading via toast) are designed and shown in the prototype.

That said: the hardcoded hexes used in the prototype (`#0a0d18`, `#161b2d`, `#252b48`, `violet-500`, etc.) approximate ARM's default "Synthwave" theme. When reimplementing, use the theme tokens (`bg-base-100`, `border-base-300`, `text-primary`, etc.) so it works across all themes.

## Screens / Views

The prototype is a single page representing the Settings → Notifications tab. Layout from the outside in:

### Page chrome (out of scope for this handoff)

The sidebar, top header bar, and Settings tabs row already exist in the live app. The prototype includes mocked versions for context only — **do not reimplement them**. The redesign only touches the body of the **Notifications** tab.

### Notifications tab body

The body is centered with `max-width: 1080px` and `padding: 24px`. Internal vertical rhythm: 20–24px between major blocks.

**Section header**

- Left column: H2 "Notifications" (18px, weight 600, white, tracking-tight) + helper text directly below (12.5px, `text-slate-400`, max 2 lines).
- Right column: primary action button **"Add channel"** (violet bg, `+` icon, 12.5px medium). Hidden while the Add Channel form is open.

**Stat strip** (4-column grid, gap 12px, below section header)

Each card: rounded 8px, bg `#13162a`, border `#252b48`, padding `16px 12px`.

- Label: 10.5px uppercase tracking-[0.12em], `text-slate-500`, weight 600
- Value: 24px tracking-tight, weight 600, color depends on accent (violet / blue / amber / emerald / slate)
- Hint: 11px, `text-slate-500`, inline next to value

Cards (in order): Channels (violet), Events delivered (blue), Issues (amber when > 0 / emerald when 0), Subscribed events (slate).

**Add Channel form** (only visible when the user clicks "Add channel")

Sits between the stat strip and the filter bar. Rounded 12px, bg `#161b2d`, border `#252b48`, subtle box-shadow `0 8px 40px -12px rgba(0,0,0,0.5)`.

Header (px-5 py-4, border-b `#252b48`, bg gradient violet-500/5 → transparent):
- Violet-glow square icon (28×28, bg violet-500/15, text violet-300, `+` glyph)
- Title "Add notification channel" (14px, weight 600, `text-violet-300`)
- Helper "Configure delivery, pick events, and customize templates — all in one place." (11.5px, slate-500)
- Right: text-only "Cancel" with X icon

Body (padding 20px, `space-y-5`). Four sections, each prefixed by a numbered chip header.

Section header pattern (`FormBlock`):
- 20×20 rounded-full chip with the section number, bg violet-500/15, text violet-300, border violet-500/30, 10.5px weight 600
- Title (13px, weight 600, slate-100)
- Subtitle "· …" (11.5px, slate-500, optional — used to surface state like "2 of 6 subscribed")

Sections:

1. **Delivery** — three big radio-card buttons in a 3-column grid (gap 12px). Each card is 16px padded, rounded-lg, bg `#13162a`, border `#252b48`. When selected: bg violet-500/10, border violet-500, plus a `box-shadow: 0 0 0 3px rgba(139,92,246,0.12)` ring. Each card contains:
   - 36×36 icon square (rounded-md, bg `#1c1f37` text slate-400; when selected: bg violet-500/20, text violet-300)
   - Card title (13.5px, weight 600)
   - Card description (11.5px, slate-500, leading-snug)
   - "RECOMMENDED" badge top-right on the Apprise card (9.5px tracking-wider, violet-300 on violet-500/15)
   - Cards: "Service (Apprise)" (bell icon), "Webhook" (webhook icon), "Bash script" (terminal icon)

   When **Service (Apprise)** is selected, an additional service-picker block appears directly below the cards: rounded-lg bg `#13162a` border `#252b48`, padding 16px, containing a `Field` wrapping the custom `ServiceDropdown` (see Components section).

2. **Configuration** — fields rendered based on the selected delivery type:
   - Top row: grid `[1fr_auto]`, "Channel Label" text input + on/off toggle with "Enabled" label
   - Below: an outlined "configuration" card (rounded-lg, bg `#13162a`, border `#252b48`, padding 16px) containing a 2-column grid of `Field`s. The card header shows the service glyph (18×18), service name, and the `scheme://…` (font-mono, 11px, slate-500). For Apprise services: render the service's declared field schema (see `data.js` SERVICES). For Webhook: URL (full width), Method, Shared Secret. For Bash: Script Path (full width), Arguments.
   - Some fields are marked `secret: true` → render as `<input type="password">`.
   - Some fields span both columns (`url`, `path`) — give them `col-span-2`.

3. **Events** — outlined card (rounded-lg, bg `#13162a`, border `#252b48`, padding 16px) with header row:
   - Left: section label "EVENTS" (11px uppercase tracking-[0.12em], violet-400, weight 600)
   - Right: text buttons "Select all" and "Clear" (11px, slate-400, hover violet-300), separated by `·`

   Body: 3-column grid (`gap-y-3 gap-x-6`) of custom `Checkbox` components — 16×16 box, violet-500 fill when checked, slate-200 label (13px), slate-500 description (11px).

4. **Message templates** — outlined card with sub-header "MESSAGE TEMPLATES" (11px uppercase tracking, violet-400) + "optional — leave blank to use defaults" hint. Body: one collapsible row per subscribed event, divided by `divide-y divide-[#252b48]`.

   Each row (collapsed): chevron (rotates 90° when open) + event label + "default"/"customized" pill + truncated preview of current title (font-mono 11px, slate-500, max-w 280, right-aligned).

   When expanded: shows two fields (Title input, Body textarea — font-mono, min-h 72px), then a strip of clickable variable chips (`{job_title}`, `{job_id}`, `{job_disc_type}`, `{job_imdb_id}`, `{occurred_at}`, `{drive_mount}`). Click a chip to append to the body. If the event has been customized, show a right-aligned "Reset to default" link (11px, slate-500, hover red-400).

   Empty state (no events subscribed): centered text "No events subscribed. Pick at least one event above to customize templates." in a 6-padding card.

Footer (px-5 py-3.5, border-t `#252b48`, bg `#131727`):
- Left: live readiness status. Either "Ready to save" (emerald-400 with check icon) or "Needs: channel label, required fields, at least one event" — only listing the unmet conditions, comma-separated, slate-400. The amber-400/90 icon precedes.
- Right: "Cancel" (ghost), "Send test" (secondary with paper-plane icon), "Save channel" (primary, disabled+40%-opacity when not ready).

**Filter bar** (above the channel list, only when channels exist)

- Left: pill-group filter (rounded-md, bg `#13162a`, border `#252b48`, padding 2px). Four pills: "All · {n}", "Enabled · {n}", "Paused · {n}", "Issues · {n}". Active pill: bg violet-500/15, text violet-300. Inactive: text slate-400, hover slate-200.
- Right: helper text "Click a row to edit · drag to reorder (coming soon)" (11.5px, slate-500).

**Channel list**

Rounded-xl, bg `#161b2d`, border `#252b48`, `divide-y divide-[#252b48]`.

Column header (px-4 py-2, bg `#131727`):
- Grid: `[auto_1fr_auto_auto_auto]` with gap 16px
- Labels: empty (avatar gutter) / "Channel" / "Last delivery" / "Enabled" / "Actions"
- Type: 10.5px uppercase tracking-[0.12em], slate-500, weight 600

Each row (collapsed):
- Grid: same `[auto_1fr_auto_auto_auto]`, items-center, gap 16px, px-4 py-3
- Whole row is clickable to toggle expand (cursor-pointer, hover bg `#13172a`/60)
- Avatar gutter: status dot (8×8, glow on `ok` emerald, `warn` amber, `error` red, `off` slate-600) + service glyph (28×28 monogram square) OR a fallback badge (`{}` for webhook in blue tones, `$_` for bash in amber tones)
- Channel info column: name (13.5px weight 500 slate-100) + secondary line (11.5px slate-500): `"{type description} · {n} events"`. If there's an error: append `· {error}` in amber-400.
- Last delivery column: timestamp (`12m ago`, 11.5px font-mono slate-300) + "X sent · Y failed (24h)" (10.5px slate-500). Right-aligned. Hidden on `md:` and below.
- Toggle column: 36×20 toggle (violet-500 when on, `#2d3458` when off). Click stops propagation.
- Actions column: paper-plane icon button (send test) + chevron (rotates 180° when expanded). Both small (14×14 icons, 1.5 padding).

Each row (expanded): the same `ChannelEditor` form opens beneath, with three collapsible sub-sections sharing the wizard's section components:
- "Configuration" (open by default)
- "Events · {n} subscribed" (open by default)
- "Message templates" (closed by default)

Footer of the editor: "Save changes" (disabled until dirty), "Send test", "Close" (ghost), spacer, "Delete" (danger variant — red ghost with red border on hover).

**Empty state** (channels.length === 0)

Centered card: rounded-xl, dashed `#2d3458` border, bg `#13162a`/40, padding `48px 24px`. 48×48 violet-500/10 circle with bell icon → title "No notification channels yet" (14px, weight 500, slate-200) → subtitle (12px, slate-500, max-w 28rem) → primary CTA "Add your first channel".

**Footnote**

Small centered text below the list: "Notification dispatch is queued and retried up to 3 times with exponential backoff. See **delivery logs** for the full audit trail." 11.5px, slate-600, with blue-400 link.

### Toasts

Fixed bottom-right (24px from edges). Rounded-lg, border + bg tinted by tone (success emerald-500/10+40, error red-500/10+40, info violet-500/10+40), padding `12px 16px`, min-width 280px, max-width 420px, backdrop-blur. Icon (4×4) on the left, title (13px, weight 600) + body (11.5px, opacity 80%) center, dismiss X on the right. Auto-dismiss after 4200ms.

### Confirm-delete dialog

Fixed inset-0, bg `rgba(0,0,0,0.6)`, backdrop-blur-sm, centered card (max-w 420px). Rounded-xl, border `#2d3458`, bg `#161b2d`. Body padding 20px: 40×40 red-500/15 warning triangle icon + title "Delete channel?" + body "{name} will be removed and stop receiving events. This cannot be undone." Footer (px-5 py-3, bg `#131727`, border-t `#252b48`): ghost Cancel + red Delete button.

## Components

These are the reusable primitives the design depends on. Each should map to (or extend) the existing Svelte component vocabulary in `frontend/src/lib/components/`.

### `Field` — labeled wrapper

12px medium slate-300 label, optional red `*`, optional 11px slate-500 hint below.

### `TextInput`, `TextArea`

bg `#1c1f37`, border `#2d3458`, rounded-md, padding `8px 12px`, 13px slate-100. Placeholder slate-500. Focus: border violet-500, bg `#221f47`. Textarea is font-mono with min-height 72px.

### `Checkbox`

Custom 16×16 box (not native). Unchecked: bg `#1c1f37`, border `#3a4170`, hover border violet-500. Checked: bg violet-500, white tick (2px stroke). Label 13px slate-200; description 11px slate-500.

### `Toggle`

36×20 pill. Off: bg `#2d3458`. On: bg violet-500. Knob: 14×14 white circle, translateX from 3px to 19px, transition transform 150ms.

### `Button` (variants)

- `primary`: violet-500 bg, hover violet-600, white text, shadow `0 4px 14px -4px rgba(139,92,246,0.6)`
- `secondary`: bg `#222845` border `#2d3458`, slate-200
- `ghost`: transparent, hover bg `#222845`, slate-300
- `danger`: transparent red-400, hover red-500/10 bg + red-500/40 border
- `chip`: violet-500/10 bg, violet-500/30 border, violet-300 text, font-mono 11px

All sizes: padding `6px 12px`, 12.5px weight 500, rounded-md, whitespace-nowrap.

### `StatusDot`

8×8 round. Variants with matching colored box-shadow glow: ok (emerald-400), warn (amber-400), error (red-400), off (slate-600 — no glow).

### `Pill`

Inline-flex, padding `2px 8px`, rounded, text 10.5px weight 500, border. Tones: default (slate), violet, blue, amber, green.

### `ServiceGlyph`

Generated colored monogram square (default 32×32, configurable). Hash the service id to derive an OKLCH hue (0.45 0.13 hue). Background = darker hue, text = lighter accent (0.78 0.16 hue). Show the first letter, weight 700, 13px, rounded-md, border `border-white/5`.

**This is deliberately a placeholder** — we don't have the real Discord/Slack/etc. logos and shouldn't fake them. When the codebase has real SVG marks for the popular services, swap them in by id; fall back to the generated monogram for the long tail.

### `ServiceDropdown`

Custom combobox (not a `<select>`). Trigger: full-width button, bg `#1c1f37`, border `#2d3458`, padding `10px 12px`, rounded-md, hover border violet-500/60, open border violet-500. Shows the selected service's glyph + name + category, with a chevron on the right (rotates 180° when open).

Open panel: absolute, z-20, mt-1, bg `#161b2d`, border `#2d3458`, rounded-md, shadow-2xl. Sticky search input at top (padding 8px, with magnifier icon). Body max-height 280px, scrollable.

Sections in order:
1. **Featured** — services with `featured: true`. Group header: 10px violet-400 uppercase tracking-[0.12em] weight 600, with a small filled star icon. Items in `data.js`: discord, slack, telegram, pushover, ntfy, gotify.
2. **By category** — remaining services grouped by `category` (Chat, Push, Email, SMS, Automation). Group header same style but slate-500 (no icon).

Each option (button): bg hover `#1c1f37`, active (selected) bg violet-500/15. Layout: glyph 22×22 + name (13px slate-100) + `scheme://` (10.5px font-mono slate-500) + selected check (12×12 violet-400) on the right.

Closes on outside click (mousedown listener on document).

### `Stepper`

Defined in primitives but **no longer used** after the wizard was unified. Leave the component in place — it's useful for any future multi-step flows — but the Add Channel form does not invoke it.

### `FormBlock`

Numbered section wrapper for the unified Add Channel form. 20×20 round chip (violet-500/15 bg, violet-500/30 border, violet-300 text) with the step number + 13px section title + 11.5px slate-500 subtitle prefixed by `·`.

## Interactions & Behavior

### Channel list

- Click any cell of a row (except toggle/actions) → expand the inline editor; click again to collapse. Only one row expanded at a time.
- Toggle "Enabled" → updates immediately, shows info toast "Enabled / Paused {name}".
- Click paper-plane icon → fires test; see "Test send" below.
- Filter pills filter the list client-side. Counts in the pill labels stay live.

### Add Channel form

- Opening: click "Add channel" → form mounts above filter bar; the "Add channel" button hides until form closes.
- Closing: "Cancel" or the header X → form unmounts without saving.
- Type selection: clicking a delivery card swaps `type`. **Side effect: reset `config` to `{}`** (different field schema). The configuration card re-renders.
- Service dropdown: changing service also resets `config`. Featured services pinned, search filters by name or category, click anywhere outside to close.
- Events grid: each checkbox toggles a key in/out of the `events` array. "Select all" sets all 6, "Clear" empties.
- Templates: each event row collapses/expands independently. Only one open at a time within a single form instance. Variable chips append to body (with a leading space if body is non-empty). "Reset to default" removes the event entry from the `templates` object.
- Footer readiness:
  - Compute `missing = { name: !name.trim(), config: !allRequiredFieldsFilled, events: events.length === 0 }`.
  - If none missing → emerald "Ready to save".
  - Else → amber "Needs: " followed by a comma-joined list of the labels above.
  - The Save button is disabled (40% opacity, pointer-events-none) until all three are clear.
- Save: build channel object with `id: Date.now()` (in production: server-issued id), insert at the **top** of the channels array, close form, show success toast `"Channel added — {name} is now listening for events."`.

### Channel editor (expanded row)

- Same form sections, wrapped in collapsible `CollapseSection`s (Configuration open, Events open, Templates closed by default).
- The form tracks a `dirty` flag set by any state change. "Save changes" disabled until dirty.
- "Send test" fires the test (see below) without saving.
- "Delete" opens the confirm dialog.

### Test send

1. Show info toast "Sending test to {name}…".
2. After 900ms (simulating an API call), show success toast "Test delivered — Sample 'job.started' event sent at {time}.".
3. Bump `lastSentAt = Date.now()`, `lastStatus = 'ok'`, clear `lastError`, increment `sent24h`.

In production: actually POST `/api/notifications/channels/:id/test` and use the response to drive the toast and state update.

### Delete

1. Click Delete in editor → confirm dialog.
2. Confirm → remove channel from state, close dialog, info toast "Deleted {name}".
3. Cancel → close dialog, no state change.

### Animations

- Hover transitions: `transition-colors`, 150ms (set in CSS via `button, input, textarea, a { transition-duration: 150ms; }`).
- Chevrons: `transition-transform`, default 150ms, rotate 90° for inline collapsibles, 180° for the row collapse and dropdown chevron.
- No page-level animations needed. Toast appears instantly — could add a 180ms fade-in (the prototype defines a `.fadein` class but doesn't use it on toasts; feel free to apply it).

## State Management

For a Svelte 5 implementation, use `$state` runes:

```ts
let channels = $state<Channel[]>([]);
let wizardOpen = $state(false);
let expandedChannelId = $state<number | null>(null);
let filter = $state<'all' | 'enabled' | 'disabled' | 'issues'>('all');
let toast = $state<Toast | null>(null);
let deleteTarget = $state<Channel | null>(null);
```

Derived counts:

```ts
const counts = $derived({
  total: channels.length,
  enabled: channels.filter(c => c.enabled).length,
  issues: channels.filter(c => c.lastError).length,
  sent24h: channels.reduce((s, c) => s + c.sent24h, 0),
});
```

Data fetching: use the existing `apiFetch` client from `frontend/src/lib/api/client.ts` and the channels endpoints from `frontend/src/lib/api/channels.ts`. The existing `channels.ts` already exposes the shapes (`Channel`, `ChannelCreate`, `ChannelUpdate`, `Catalog`, etc.) — extend if needed.

The events catalog, template variables, and service catalog should ideally come from a backend `Catalog` endpoint so the frontend stays in sync with whatever ARM actually emits. The `data.js` in this handoff defines these for prototype purposes; treat its shapes as the contract.

## Type definitions (informal — derive from existing TS types)

```ts
type ChannelType = 'apprise' | 'webhook' | 'bash';

interface Channel {
  id: number;
  name: string;
  type: ChannelType;
  serviceId: string | null;       // only set when type === 'apprise'
  enabled: boolean;
  config: Record<string, string>;
  events: string[];               // subset of EVENT keys
  templates: Record<string, { title?: string; body?: string }>;
  lastSentAt: number | null;
  lastStatus: 'ok' | 'warn' | 'error' | 'off';
  lastError: string | null;
  sent24h: number;
  failed24h: number;
}

interface EventDef {
  key: string;
  label: string;
  description: string;
  defaults: { title: string; body: string };
}

interface Service {
  id: string;
  name: string;
  category: 'Chat' | 'Push' | 'Email' | 'SMS' | 'Automation';
  featured?: boolean;
  scheme: string;
  fields: ServiceField[];
}

interface ServiceField {
  key: string;
  label: string;
  required?: boolean;
  secret?: boolean;
  placeholder?: string;
  help?: string;
}
```

## Design Tokens

Map these to existing ARM Tailwind theme tokens during implementation. Hardcoded values shown approximate the Synthwave theme.

**Surfaces**
- App background: `#0a0d18` → `bg-base-100`
- Page chrome (sidebar, header): `#0c0f1c` → `bg-base-200`
- Card / panel: `#161b2d` → `bg-base-100` with `border-base-300`
- Secondary panel (form sub-cards, footers): `#131727` / `#13162a`
- Input background: `#1c1f37` → `bg-base-200`
- Input focus background: `#221f47`

**Borders**
- Default: `#252b48` → `border-base-300`
- Subtle / input: `#2d3458`
- Hover: `#3a4170`

**Brand / accents**
- Primary (violet): `violet-500` `#8b5cf6` → `text-primary` / `bg-primary`. Hover: violet-600. Tinted surface: `violet-500/10`. Tinted border: `violet-500/30`. Glow shadow: `0 4px 14px -4px rgba(139,92,246,0.6)`.
- Secondary (blue): `blue-400` `#60a5fa` → used on the active Settings tab and stat accents
- Tab indicator (Settings tabs): `blue-400`

**Status colors**
- Success / OK: `emerald-400` `#34d399`. Glow `0 0 8px rgba(52,211,153,0.6)`
- Warning: `amber-400` `#fbbf24`. Glow `0 0 8px rgba(251,191,36,0.6)`
- Error: `red-400` `#f87171`. Glow `0 0 8px rgba(248,113,113,0.6)`
- Off / disabled: `slate-600`

**Text**
- Primary (headings, key values): `text-white` / `text-slate-100`
- Body: `text-slate-200` / `text-slate-300`
- Secondary / helper: `text-slate-400`
- Muted: `text-slate-500`
- Disabled / footnote: `text-slate-600`

**Typography**

- Sans: Inter (400/500/600/700). Existing app uses Rajdhani for display in some places — defer to existing theme.
- Mono: JetBrains Mono.
- Sizes used (all rem-equivalent, but stated in px for clarity):
  - 22px / 600 / tracking-tight — page title ("Settings")
  - 18px / 600 — section title ("Notifications")
  - 14px / 600 — card titles (Add channel header, dialog title)
  - 13.5px / 500–600 — channel name, card heading
  - 13px / 500–600 — section labels, dropdown option label
  - 12.5px / 400–500 — tabs, body copy, button text
  - 12px / 400–500 — field labels, helper text
  - 11.5px / 400 — small helper text, secondary row line, footer text
  - 11px / 400–500 — pill text, hint text, chip text
  - 10.5px / 600 / uppercase / tracking-[0.12em] — column headers, group labels

**Spacing**
- Page side padding: 24px
- Card padding: 16–20px (form sub-cards 16px, top-level cards 20px)
- Section gaps in unified form: 20px (`space-y-5`)
- Grid gaps: 12px (stat strip), 12–16px (form rows), 4–6px (button group)

**Radii**
- Buttons / inputs / small cards: `rounded-md` (6px)
- Larger panels: `rounded-lg` (8px)
- Top-level form / list container: `rounded-xl` (12px)
- Chips / status pills: `rounded` (4px) or `rounded-full`

**Shadows**
- Primary button: `0 4px 14px -4px rgba(139,92,246,0.6)`
- Add Channel form panel: `0 8px 40px -12px rgba(0,0,0,0.5)`
- Dropdown panel: `shadow-2xl shadow-black/60`
- Toast: `shadow-2xl shadow-black/60`

**Background accent (subtle vignette)**

```css
body::before {
  content: "";
  position: fixed;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(900px 500px at 80% -10%, rgba(139, 92, 246, 0.08), transparent 60%),
    radial-gradient(700px 400px at 0% 110%, rgba(59, 130, 246, 0.06), transparent 60%);
}
```

## Assets

No image/icon assets. All icons in the prototype are inline SVG paths defined in the components — copy these paths directly into Svelte components. Specifically used:

- `+` plus / add (Add channel button, empty-state CTA, wizard header)
- `×` close (Cancel, toast dismiss)
- Chevron down/up (dropdown trigger, row expand)
- Chevron right (collapsible section header)
- Bell / notification (delivery type icon for Apprise, empty state)
- Webhook glyph (custom path)
- Terminal (Bash type)
- Paper-plane / send arrow (test send action)
- Magnifier (dropdown search)
- Star (Featured group header in dropdown)
- Check (selected indicator, success toast)
- Info `i` circle (info toast)
- Warning `!` triangle (delete dialog, error toast)
- Trash (Delete button in editor)

Service logos: **deliberately monogram placeholders** (`ServiceGlyph` component). When real SVG marks are available in the codebase, swap by service id; fall back to the monogram.

## Files

The HTML prototype and source files included in this handoff:

- `Notifications Settings.html` — entry point; loads React 18 + Tailwind Play CDN, mounts the app
- `data.js` — events catalog, template variables, services catalog, and 4 seeded sample channels
- `primitives.jsx` — `Field`, `TextInput`, `TextArea`, `Checkbox`, `Radio`, `Toggle`, `Button`, `StatusDot`, `Pill`, `ServiceGlyph`, `Stepper` (unused), `ServiceDropdown`
- `wizard.jsx` — `AddChannelWizard` (unified single-screen form), `ConfigureSection`, `EventsSection`, `TemplatesSection`, `ReviewSummary`, `ChannelEditor`, `CollapseSection`, `FormBlock`, `StepType`
- `app.jsx` — `App` (root), `Sidebar`, `Header`, `SettingsTabs`, `ChannelRow`, `ChannelsList`, `Toast`, `ConfirmDialog`, `StatCard`, helpers (`formatAgo`, `channelStatus`, `channelDescription`)

Open `Notifications Settings.html` directly in any modern browser — no build step required.

## Implementation suggestions

- The existing `frontend/src/routes/settings/+page.svelte` is currently one large file. Consider extracting:
  - `frontend/src/lib/components/notifications/ChannelList.svelte`
  - `frontend/src/lib/components/notifications/ChannelRow.svelte`
  - `frontend/src/lib/components/notifications/ChannelEditor.svelte`
  - `frontend/src/lib/components/notifications/AddChannelForm.svelte`
  - `frontend/src/lib/components/notifications/ServiceDropdown.svelte`
  - `frontend/src/lib/components/notifications/sections/{Configure,Events,Templates}.svelte`
- The `Configure / Events / Templates` sections are used in **both** the Add form and the inline editor — extract them as Svelte components and re-use.
- Keep the existing API surface in `channels.ts` and extend with `testChannel`, `updateChannel`, `deleteChannel` if not already present.
- Persist `expandedChannelId` and `filter` to the URL (search params) so deep-linking works and refresh preserves state — optional polish, not in the prototype.
- The `ServiceDropdown` outside-click handler in the prototype uses a `mousedown` listener — match that in Svelte with an action or `clickOutside` util.
- Toasts: if the codebase already has a toast/notification store, route through that instead of the per-instance `Toast` component. The prototype shows what a single visible toast should look like.

## Out of scope / future work

These were intentionally **not** designed in the prototype but came up in the conversation. Surface them to the team if they come up later:

- Dispatch history view (recent sends, failures, retry log)
- Per-event "mute during X" rule / quiet hours
- Channel groups / tags
- Drag-to-reorder channels (the filter bar mentions "coming soon")
- Bulk actions (enable/disable/delete multiple channels)
- Per-channel rate limits

---

Questions during implementation — ping the design owner. The prototype is the source of truth for visual treatment; the live `apiFetch` channel API + existing ARM theme tokens are the source of truth for engineering integration.
