# ARM UI Theme Generation Template

Generate new color themes for the ARM (Automatic Ripping Machine) dashboard UI. The UI is a SvelteKit app using Tailwind CSS v4 with a CSS custom property-based theming system.

## How Themes Work

There are two kinds of themes, with different formats:

- **Built-in themes** ship with the frontend as a pair: a token entry in
  `frontend/src/lib/stores/colorScheme.ts` (`COLOR_SCHEMES`) plus an optional
  static CSS sidecar at `frontend/static/themes/<id>.css`. The sidecar is
  served same-origin at `/themes/<id>.css` and fetched at runtime when the
  theme activates. The backend is not involved.
- **User-uploaded themes** are a single **JSON file** uploaded via the
  Settings page and served by the backend theme API. Their custom CSS lives in
  the JSON's `"css"` string field.

Both kinds define the same token set, applied to `:root` at runtime. Dark-only
themes set `mode: 'dark'`. All custom CSS rules are scoped with a
`[data-scheme="<id>"]` selector prefix.

## Built-in Theme Format (new themes go here)

### 1. Registry entry — `colorScheme.ts`

Append a `ColorScheme` object to `COLOR_SCHEMES`:

```ts
{
	id: 'winamp-classic',
	label: 'Winamp',
	swatch: '#d4b02f',
	mode: 'dark', // omit for dual light/dark themes
	author: 'Claude',
	description: 'Classic MP3-player skin — charcoal chrome, gold titlebars, spectrum-analyzer progress',
	tokens: {
		'--color-primary': 'rgb(214, 178, 54)',
		'--color-primary-hover': 'rgb(232, 199, 84)',
		'--color-primary-dark': 'rgb(150, 122, 30)',
		'--color-primary-light-bg': 'rgb(44, 44, 60)',
		'--color-primary-light-bg-dark': 'rgb(36, 36, 50)',
		'--color-primary-text': 'rgb(222, 189, 84)',
		'--color-primary-text-dark': 'rgb(222, 189, 84)',
		'--color-primary-border': 'rgb(150, 122, 30)',
		'--color-on-primary': 'rgb(18, 18, 24)',
		'--color-page': 'rgb(20, 20, 30)',
		'--color-page-dark': 'rgb(20, 20, 30)',
		'--color-surface': 'rgb(34, 34, 48)',
		'--color-surface-dark': 'rgb(34, 34, 48)',
		'--radius': '0.25rem'
	}
}
```

Built-in entries include `--radius` in `tokens` (corner rounding — `0px` for
hard-edged retro themes, `0.5rem` typical otherwise). Do **not** set the `css`
field on new built-in entries — custom CSS belongs in the static sidecar
(older entries with inline `css` strings are legacy).

### 2. CSS sidecar — `static/themes/<id>.css` (optional)

Plain CSS (no JSON escaping), every rule prefixed with
`[data-scheme="<id>"]`. Omit the file entirely for pure color-swap themes.

Status-color token overrides use `:root`-level blocks — the sidecar is the
only place a theme can scope them per mode:

```css
:root[data-scheme='my-theme'] {
	/* light-mode status palette */
	--color-status-success: rgb(152, 151, 26);
}
:root[data-scheme='my-theme'].dark {
	/* brighter variants on dark backgrounds */
	--color-status-success: rgb(184, 187, 38);
}
```

## User-Uploaded Theme JSON Format

Each theme is a single `.json` file named `<id>.json`:

```json
{
  "id": "<unique_kebab_id>",
  "label": "<Display Name>",
  "version": 1,
  "author": "<Author Name>",
  "description": "<Short description of the theme>",
  "swatch": "<hex_color>",
  "mode": "dark",
  "tokens": {
    "--color-primary":            "rgb(R, G, B)",
    "--color-primary-hover":      "rgb(R, G, B)",
    "--color-primary-dark":       "rgb(R, G, B)",
    "--color-primary-light-bg":      "rgb(R, G, B)",
    "--color-primary-light-bg-dark": "rgb(R, G, B)",
    "--color-primary-text":      "rgb(R, G, B)",
    "--color-primary-text-dark": "rgb(R, G, B)",
    "--color-primary-border":    "rgb(R, G, B)",
    "--color-on-primary":        "rgb(R, G, B)",
    "--color-page":         "rgb(R, G, B)",
    "--color-page-dark":    "rgb(R, G, B)",
    "--color-surface":      "rgb(R, G, B)",
    "--color-surface-dark": "rgb(R, G, B)"
  },
  "css": ""
}
```

### Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| `id` | Yes | URL-safe, lowercase, kebab-case. Used as filename and `[data-scheme]` value |
| `label` | Yes | Short display name (1-2 words) shown under the swatch |
| `version` | No | Integer version number (default: 1). JSON themes only |
| `author` | No | Theme author name |
| `description` | No | Short description of the theme |
| `swatch` | Yes | Hex color for the preview circle (e.g. `"#3b82f6"`) |
| `mode` | No | `"dark"` or `"light"` locks that mode on while the theme is active. Omit for dual light/dark themes |
| `tokens` | Yes | Object with 13 required CSS custom properties (plus 7 optional status colors - see below) |
| `css` | No | JSON themes only: custom CSS string scoped under `[data-scheme="<id>"]` (default: `""`). Built-ins use the static sidecar instead |

### Token Reference

```
Primary accent color (buttons, active states, links):
  --color-primary              Main accent — 500-600 range
  --color-primary-hover        Hovered accent — one shade darker (600-700)
  --color-primary-dark         Deep accent for borders/outlines (700-800)

Backgrounds with accent tint:
  --color-primary-light-bg      Light mode: highlighted row/card bg (100 range)
  --color-primary-light-bg-dark Dark mode: highlighted row/card bg (900 range, muted)

Text colored with accent:
  --color-primary-text          Light mode: links, headings (700 range)
  --color-primary-text-dark     Dark mode: links, headings (300-400 range)

Misc:
  --color-primary-border        Borders on focused/active elements (500 range)
  --color-on-primary            Text ON primary bg (white or black for contrast)

Page & surface backgrounds:
  --color-page                  Light mode: full page bg (very light, accent-tinted)
  --color-page-dark             Dark mode: full page bg (very dark, accent-tinted)
  --color-surface               Light mode: card/panel bg (slightly lighter than page)
  --color-surface-dark          Dark mode: card/panel bg (slightly lighter than page-dark)

Built-in registry entries only:
  --radius                      Corner rounding (0px for hard-edged themes)
```

#### Optional status-color tokens

The 7 status-color tokens below paint job-state badges, lifecycle nodes,
progress bars, and dashboard chips. They default to a sensible palette in
`frontend/src/app.css` and themes don't need to override them - omit the
keys to inherit defaults. Set them only when the default palette clashes
with your theme accent. Built-in themes override them in the CSS sidecar
(scoped `:root[data-scheme]` blocks, per-mode — see above); JSON themes may
set them in `tokens`.

```
  --color-status-ripping      Active rip / "Ripping" lifecycle node (default: blue)
  --color-status-transcoding  Active transcode / "Transcoding" lifecycle (default: violet)
  --color-status-finishing    Copy/eject phase, "Finishing" badge (default: amber)
  --color-status-waiting      Pre-rip "Waiting" lifecycle node (default: yellow)
  --color-status-scanning     Disc scan / metadata fetch in progress (default: cyan)
  --color-status-success      Completed jobs (default: green)
  --color-status-error        Failed jobs (default: red)
```

Pick contrasting hues so users can distinguish "ripping" from "transcoding"
at a glance, and keep `--color-status-finishing` distinct from
`--color-status-waiting` (the dashboard's `.status-warning` class also uses
the waiting token).

#### Optional appearance tokens

Beyond colors, four appearance tokens cover the most common customizations
that previously required custom CSS. All are optional with no-op defaults,
and all work in both built-in entries and uploaded JSON `tokens`:

```
  --radius        Corner rounding for cards/controls (e.g. "0px" hard-edged,
                  "0.5rem" default). Also drives the derived radius scale.
  --font-family   App-wide font stack (e.g. "'Trebuchet MS', Tahoma, sans-serif").
                  Falls back to the Tailwind sans stack. Embedding an actual
                  webfont still requires an @font-face rule in custom CSS.
  --frame-accent  Theme-level default accent for section frames. Per-instance
                  accents set by pages (e.g. the dashboard's per-panel colors)
                  take precedence; frames without an explicit accent fall back
                  to this token, then to the historical #f90.
  --logo-filter   CSS filter applied to the sidebar logo image
                  (e.g. "sepia(1) hue-rotate(65deg) saturate(2.5)").
  --logo-url      Replaces the logo image entirely via CSS content replacement,
                  e.g. "url(data:image/svg+xml;base64,...)". Chromium/Safari;
                  browsers without img content support keep the stock logo.
```

## Custom CSS

For themes with distinctive visual styles beyond color tokens. Built-in
themes: plain CSS in `static/themes/<id>.css`. JSON themes: a CSS string in
the `"css"` field — stored as a JSON string value, so all double quotes
within the CSS must be escaped as `\"`. Either way, every rule is prefixed
with `[data-scheme="<id>"]`.

### Available Selectors

```css
[data-scheme="<id>"] { }                                /* Root — font-family, etc. */
[data-scheme="<id>"] body { }                           /* Body — gradients, bg images */
[data-scheme="<id>"] aside { }                          /* Sidebar container */
[data-scheme="<id>"] aside nav a { }                    /* Nav links */
[data-scheme="<id>"] aside nav a:hover { }              /* Nav link hover */
[data-scheme="<id>"] aside nav a[data-active="true"] { }/* Active nav link */
[data-scheme="<id>"] aside nav a svg { }                /* Nav icons */
[data-scheme="<id>"] aside [data-logo] img { }          /* Logo image — filters */
[data-scheme="<id>"] aside [data-stats] { }             /* Sidebar stats panel */
[data-scheme="<id>"] aside hr { }                       /* Sidebar dividers */
[data-scheme="<id>"] header { }                         /* Top header bar */
[data-scheme="<id>"] [data-progress-track] { }          /* Progress bar track */
[data-scheme="<id>"] [data-progress-fill] { }           /* Progress bar fill */
[data-scheme="<id>"] aside::before { }                  /* Pseudo-element for decorative lines */
/* Status-token overrides (sidecar only): */
:root[data-scheme="<id>"] { }                           /* Light-mode --color-status-* values */
:root[data-scheme="<id>"].dark { }                      /* Dark-mode --color-status-* values */

/* Section frames (dashboard panels like "WAITING FOR REVIEW", "ACTIVE RIPS") */
[data-scheme="<id>"] .section-frame { }                 /* Frame container */
[data-scheme="<id>"] .section-frame-bar-top { }         /* Accent bar with label */
[data-scheme="<id>"] .section-frame-bar-bottom { }      /* Bottom accent bar */
[data-scheme="<id>"] .section-frame-sidebar { }         /* Side blocks (full variant) */
[data-scheme="<id>"] .section-frame-block-a { }         /* Top sidebar block */
[data-scheme="<id>"] .section-frame-block-b { }         /* Middle sidebar block */
[data-scheme="<id>"] .section-frame-block-c { }         /* Bottom sidebar block */
[data-scheme="<id>"] .section-frame-body { }            /* Content area */
/* Frame variant attribute: [data-frame-variant="full"] or [data-frame-variant="compact"] */
/* Frame accent variable: --frame-accent (set per-instance, e.g. #f90, #99f) */
```

## Design Guidelines

1. **All RGB values must use `rgb(R, G, B)` format** — not hex, not hsl. The Tailwind v4 `color-mix()` system requires this.
2. **Light/dark dual-mode themes** (no `mode` field): Need visually distinct light AND dark variants. Light-mode backgrounds should be very light (pastel), dark-mode backgrounds very dark. Both must have good text contrast.
3. **Dark-only themes** (`"mode": "dark"`): Set matching values for light/dark token pairs (e.g., `--color-page` = `--color-page-dark`). These are often more stylized/dramatic.
4. **Swatch** must be a hex color string (e.g. `"#3b82f6"`).
5. **`--color-on-primary`**: Use `rgb(255, 255, 255)` (white) for dark accents, `rgb(0, 0, 0)` (black) for light/bright accents. This is the text color shown ON TOP of the primary color.
6. **Contrast**: Ensure `--color-primary-text` is readable on white/light-gray (#f9fafb). Ensure `--color-primary-text-dark` is readable on dark backgrounds (#111827).
7. **Custom CSS is optional** — simple color-swap themes don't need it. Use it for font changes, animations, gradients, glow effects, clip-paths, etc.

## Existing Theme IDs (do NOT reuse)

`blue`, `sunset`, `stealth-ops`, `library-archive`, `synth-retro`,
`synth-retro-v2`, `research-outpost`, `lcars`, `coffee`, `cinema`,
`royal-archive`, `royale`, `craft`, `terminal`, `forest`, `ocean`,
`tactical`, `deep-sea-abyss`, `nordic-frost`, `solarized-dark`,
`blockbuster`, `vcr-osd`, `glass`, `tokyo-night`, `violet`,
`retro-console`, `hollywood-video-v2`, `dracula-pro`, `gaming`, `rose`,
`winamp-classic`, `winamp-shade`

## Example — stylized dark-only built-in (registry entry above + sidecar)

`static/themes/winamp-classic.css`:

```css
[data-scheme='winamp-classic'] {
	font-family: Tahoma, 'MS Sans Serif', Verdana, sans-serif;
}
[data-scheme='winamp-classic'] aside nav a[data-active='true'] {
	color: #d6b236 !important;
	background: #1a1a28 !important;
	border-top-color: #14141e;
	border-left-color: #14141e;
	border-bottom-color: #4a4a68;
	border-right-color: #4a4a68;
}
[data-scheme='winamp-classic'] [data-progress-fill] {
	background:
		repeating-linear-gradient(90deg, transparent 0 2px, rgba(0, 0, 0, 0.4) 2px 4px),
		linear-gradient(90deg, #00c010, #a8c000 65%, #c03000) !important;
	border-radius: 0 !important;
	box-shadow: 0 0 6px rgba(0, 192, 16, 0.35);
}
```

## Example — simple dual-mode JSON upload (color swap only, no custom CSS)

```json
{
  "id": "forest",
  "label": "Forest",
  "version": 1,
  "author": "ARM Team",
  "description": "Emerald green nature theme",
  "swatch": "#10b981",
  "tokens": {
    "--color-primary": "rgb(5, 150, 105)",
    "--color-primary-hover": "rgb(4, 120, 87)",
    "--color-primary-dark": "rgb(6, 95, 70)",
    "--color-primary-light-bg": "rgb(209, 250, 229)",
    "--color-primary-light-bg-dark": "rgb(6, 78, 59)",
    "--color-primary-text": "rgb(4, 120, 87)",
    "--color-primary-text-dark": "rgb(110, 231, 183)",
    "--color-primary-border": "rgb(16, 185, 129)",
    "--color-on-primary": "rgb(255, 255, 255)",
    "--color-page": "rgb(228, 248, 238)",
    "--color-page-dark": "rgb(12, 19, 15)",
    "--color-surface": "rgb(237, 252, 244)",
    "--color-surface-dark": "rgb(21, 54, 37)"
  },
  "css": ""
}
```
