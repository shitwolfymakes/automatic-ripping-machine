# Identification Sources UI: Identification and Keys Tabs, Identity Card, Suggestion Review — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Settings › Metadata with the v4.2 **Identification** tab (Search card plus the four-step Identity card with a Blu-ray | DVD | CD summary strip) and a **Keys** tab, rename the wizard's "Find titles" step to Identification, and let the operator confirm a held identity suggestion (PR 3) from the review card and the job page.

**Architecture:** The settings tabs are schema-group driven, so the move is mostly a backend regrouping (`group="Identification"` / `group="Keys"` in `config_metadata.py`) plus the presentation map in `settings-sections.ts`. The Identity card is one bespoke section component (`IdentityCard.svelte`) rendered by `SchemaConfigForm` in place of its field loops; it binds the form's `values` object and reuses `ConfigSchemaField` / `RankedListField` for every real control, so Save, change detection and guest gating stay in the form. A pure helper module (`identity-card.ts`) derives the strip text per disc kind and maps the two "Ignore" boxes onto `disc_hint_sources` set semantics. The "Needs … key" chips learn the key's tab from a schema getter set as Svelte context by the settings page (design doc Part 4). The review card and the job page gain an `IdentitySuggestionBanner` that calls the new `POST /api/jobs/{id}/identity/accept`. No migration, no wire-contract change except none expected (verify by regen).

**Tech Stack:** Python 3.14 (`arm_common` metadata, backend settings router tests), SvelteKit / Svelte 5 runes, vitest + @testing-library/svelte, ESLint/Prettier via pre-commit, svelte-check.

**Spec:** `docs/superpowers/specs/2026-10-14-identification-sources-design.md` (D-2, D-3, D-5, D-9, D-10, D-11, §8 criteria 6–7, §9 "Design changes for v4.2", §10) and the design doc mirrored outside the tree at `/home/upb/src/automatic-ripping-machine/docs/superpowers/specs/2026-10-12-identity-settings-design.md` Part 5 (Design v4: cards, strip table, steps, states, accessibility, acceptance criteria) and Part 4 (chip deep links). Issue #258 body ("The card, as built"). Branch: `feat/identification-sources-ui` from `feat/identification-sources-pr3` (PR #366).

## Global Constraints

- **Tabs:** `Identification · Keys · Ripping · Sessions · Transcoding · Notifications · Interface · Themes · Drives · Users · System`. Backend `_GROUP_ORDER = ["Identification", "Keys", "Ripping", "Transcoding", "Notifications", "System"]`. One Save per tab. A legacy `#Metadata` or `#Metadata/<key>` hash opens Identification (and, for a key field, the Keys tab via the deep link).
- **Group membership.** `Identification`: `search_provider_movie`, `search_provider_tv`, `search_provider_music`, `thediscdb_enabled`, `crc64service_enabled`, `movie_sources`, `episode_sources`, `music_sources`, `episode_match_tolerance_seconds`, `movie_auto_apply`, `episode_auto_apply`, `music_auto_apply`, `disc_hint_sources`. `Keys`: `tmdb_api_key`, `omdb_api_key`, `tvdb_api_key`, `makemkv_key`, `thediscdb_refresh_days`. Nothing else moves.
- **Wizard (D-9, ruled).** The step keeps its wire id `metadata` (`SetupStep` enum, stored progress, route) and its position; its visible label and title become `Identification`; its fields are the three API keys only (`thediscdb_enabled` loses its `setup_step`); MakeMKV keeps its own step. Intro: `ARM looks up what is on each disc so your files get the right names. TVmaze and MusicBrainz need no key; the others do.`
- **Search card** (title `Search`, blurb `What the job page's search box uses when you look a title up by hand.`): the three selects side by side, labels from the field metadata (`Search movies with` etc.).
- **Identity card** (title `Identity`, blurb `How ARM works out what a disc is before it rips, and when it trusts the answer.`), in this order: segmented control `Blu-ray | DVD | CD` (radiogroup, `aria-label="Disc kind"`, view state only, default Blu-ray); the summary strip (four cells joined by chevrons, `RecipeStrip` tone `info`); Step 1 `On the disc`; Step 2 `Disc database`; Step 3 `Online lookup`; Step 4 `Trust`; `Advanced`.
- **Step 1 (no controls):** rows `Disc title metadata` [`Blu-ray` `UHD`], `Volume label` [`All discs`], `Disc ID (track layout)` [`CD`], `CD-TEXT` [`CD` `Planned`] (muted, `aria-disabled="true"`, description `Album, artist and track names. Not built yet.`). A hint ignored in Advanced shows `Ignored (see Advanced)` on its row. Footer: `ARM reads all of these. When they disagree, the disc's own metadata beats its label.`
- **Step 2:** checkbox `TheDiscDB disc map` [`Blu-ray` `UHD` `DVD`] → `thediscdb_enabled`, description `Matches the disc itself and names its titles before any online lookup. When it matches, it wins over the disc's labels, and ARM confirms the title with the first online source below.`; checkbox `ARM community database (CRC64)` [`DVD`] → `crc64service_enabled`, description from the field's help.
- **Step 3:** sub-line `Tried top to bottom; the first confident match wins.`; three ranked lists side by side headed `Movies` (`movie_sources`), `TV shows` (`episode_sources`), `Music` (`music_sources`), each rendered with `RankedListField` (chips for missing keys come from `enum_requires`); under the TV column the `Match tolerance (seconds)` int field (its existing help text, D-11); under the Music list a disabled `Planned` row `CDDB` (`aria-disabled="true"`, `Not built yet, so never ranked`). An empty list shows `No sources on` under its heading.
- **Step 4:** three checkboxes in one row labelled `Movies`, `TV shows`, `Music` → `movie_auto_apply`, `episode_auto_apply`, `music_auto_apply`, under the caption `Apply confident matches`; shared description `When off, a match waits on the job page for you to confirm it and the disc is held with no countdown. Ripping › Review first still holds every disc.`
- **Advanced** (always open): `Ignore the disc title metadata` ↔ `bd_title` absent from `disc_hint_sources`; `Ignore the volume label` ↔ `label` absent. Toggling preserves the other entry and restores the default order (`bd_title`, `label`) when re-enabling. Line: `For collections where the disc's own text is usually wrong. Fix a single disc from its job page instead. With the volume label ignored, a DVD with no disc title metadata gets no automatic title search.`
- **Strip text** (derived live from the form's values; `labelOf` uses `enum_labels`):

  | Cell | Blu-ray | DVD | CD |
  |---|---|---|---|
  | `On the disc` | enabled hints in order among `Disc title metadata`, `Volume label`; sub `ARM reads all of these` | `Volume label` only (plus nothing else) | `Volume label, Disc ID (track layout)`; sub `CD-TEXT planned` |
  | `Disc database` | `TheDiscDB disc map` or `Off`; sub `A match wins over the disc's labels` | enabled among `TheDiscDB disc map`, `ARM community database (CRC64)`, joined `, `, else `Off` | value `Not used for CDs`, no sub |
  | `Online lookup` | `Movies: TMDb, OMDb · TV shows: TMDb, TVmaze, TVDB` (enabled, in order; an empty list reads `No sources on`); sub `Tried top to bottom; the first confident match wins` | same | `Music: MusicBrainz` (or `No sources on`); same sub |
  | `Trust` | `Movies: Apply confident matches · TV shows: Waits for review` per switch; sub `Others wait for review on the job page` | same | `Music: …` |

  When every hint is ignored, cell 1 reads `Disc text ignored` (value) with sub `See Advanced`.
- **Chips:** `chip chip-sm` text chips, never colour alone. Chevrons keep `RankedListField`'s accessible names. The segmented control follows `InterfaceSettings`'s `role="radiogroup"` / `role="radio"` / `aria-checked` pattern.
- **Keys tab sections:** `API keys` (blurb `Stored on the server. A key that is already set shows as hidden; leave it blank to keep it. Environment variables seed a key once at first boot; after that only what is saved here is used.`) with `tmdb_api_key`, `omdb_api_key`, `tvdb_api_key`; `TheDiscDB` (blurb `The local snapshot ARM matches discs against.`) with `thediscdb_refresh_days`; `MakeMKV` with `makemkv_key`. Group blurb for Keys: `Keys and the service snapshots ARM uses to identify discs.`; for Identification: `Where ARM looks up titles and disc data, and when it trusts the answer.`
- **Chip deep links (Part 4):** `SETTINGS_SCHEMA_CONTEXT` getter set by the settings page; `settingsFieldHref(key, groups)` returns `#<group>/<key>` when the key's field is in a loaded group, else `#setting-<key>`; `RankedListField` uses it (context first, `keyTab` prop second, same-page anchor last) with `title="Open <key label>"`; the header and mobile stats links point at `/settings#Keys/makemkv_key`.
- **Suggestion review (PR 3 contract):** a job whose `metadata_json.identity_suggestion` is set (typed `IdentitySuggestion` in `api.gen.ts`) shows an `IdentitySuggestionBanner` on the review card and the job page header: `ARM found a match` / `<title> (<year>)` / `from <provider label>` with the poster when present, buttons `Use this title` (calls `acceptIdentitySuggestion(job.id)` → `POST /api/jobs/{id}/identity/accept`, then refreshes) and `Search instead` (opens the card's title or music search). Status label `Confirm the title: use it or search`; phase badge `CONFIRM TITLE` (accent `var(--color-accent-4)`), ranked after the previously-ripped check. Provider labels: tmdb `TMDb`, omdb `OMDb`, tvmaze `TVmaze`, tvdb `TVDB`, musicbrainz `MusicBrainz`, arm_server `ARM community database`, thediscdb `TheDiscDB`, else the id. Guests see the banner text, no buttons. `Start rip` stays available (a placeholder rip).
- **Language rule:** say "disc" unless kind-specific; `Blu-ray`, `UHD`, `DVD`, `CD` only on chips and the segmented control; `Movies`, `TV shows`, `Music` for media types.
- No new backend endpoints. OpenAPI snapshot regenerated only if the regen script changes it (expected: no change). Playwright visual specs under `services/ui-neu/frontend/tests/visual` are not run in this plan (they need the stack); any settings snapshot they hold is refreshed by the owner. Commits carry no attribution trailers. UI checks: `npm run check`, `npx vitest run`, `npm run lint`.

## Review Focus

1. Toggling `Ignore the volume label` on then off must restore `disc_hint_sources` to `['bd_title', 'label']` (default order), never `['label', 'bd_title']`, or the hint tie-break silently flips (Task 3 helper test).
2. A legacy bookmark `#Metadata/tmdb_api_key` must land on the Keys tab with the TMDb field focused, not on a blank pane (Task 2 settings-page test).
3. Guests must see the Identity card fully rendered with every control disabled and no Save, same as the other schema tabs (Task 3 test).
4. Accepting a suggestion whose request fails must keep the banner and show the error inline, never drop the operator into a blank card (Task 5 test).
5. The `Needs TVDb API key` chip rendered on the Identification tab must link to `#Keys/tvdb_api_key` (cross-group), and in the wizard to `#setting-tvdb_api_key` (Task 2 RankedListField test).

---

### Task 1: Backend groups and wizard tags

**Files:**
- Modify: `packages/arm_common/arm_common/config_metadata.py`
- Modify: `services/backend/arm_backend/routers/settings.py` (`_GROUP_ORDER`)
- Test: `packages/arm_common/tests/test_config_metadata.py`, `services/backend/tests/test_settings_router.py`

**Interfaces:**
- Produces: schema groups named `Identification` and `Keys` (no `Metadata` group anywhere); `thediscdb_enabled` has no `setup_step`.

- [ ] **Step 1: Flip the tests**

In `test_config_metadata.py`: every assertion of `"Metadata"` as a group becomes `"Identification"` for the pipeline fields (`episode_sources` line ~87, `movie_sources` ~98, the two auto-apply toggles ~120). Add:

```python
def test_groups_split_identification_and_keys() -> None:
    by_key = {m.key: m for m in CONFIG_FIELD_META}
    keys = {"tmdb_api_key", "omdb_api_key", "tvdb_api_key", "makemkv_key", "thediscdb_refresh_days"}
    identification = {
        "search_provider_movie", "search_provider_tv", "search_provider_music", "thediscdb_enabled",
        "crc64service_enabled", "movie_sources", "episode_sources", "music_sources",
        "episode_match_tolerance_seconds", "movie_auto_apply", "episode_auto_apply", "music_auto_apply",
        "disc_hint_sources",
    }
    assert {k for k, m in by_key.items() if m.group == "Keys"} == keys
    assert {k for k, m in by_key.items() if m.group == "Identification"} == identification
    assert not any(m.group == "Metadata" for m in CONFIG_FIELD_META)
```

`test_setup_step_tagging_matches_spec`: `assert keys("metadata") == ["tmdb_api_key", "omdb_api_key", "tvdb_api_key"]`.

`test_settings_router.py` line ~59: the expected set becomes `{"Identification", "Keys", "Ripping", "Transcoding", "Notifications", "System"}`; add an order assertion that `Identification` precedes `Keys` precedes `Ripping` in the response.

Run: `uv run pytest packages/arm_common/tests/test_config_metadata.py services/backend/tests/test_settings_router.py -q` → failures on the group names.

- [ ] **Step 2: Regroup**

In `config_metadata.py` set `group="Identification"` on the thirteen pipeline fields and `group="Keys"` on the five key/service fields; remove `setup_step` and `setup_order` from `thediscdb_enabled`. In `settings.py` set `_GROUP_ORDER = ["Identification", "Keys", "Ripping", "Transcoding", "Notifications", "System"]`.

- [ ] **Step 3: Verify, including the wire contract**

```bash
uv run pytest packages/arm_common services/backend/tests/test_settings_router.py services/backend/tests/test_config_identification_settings.py -q
bash devtools/regen-openapi-snapshot.sh && git status --short services/ui-neu/openapi.snapshot.json
```

Expected: tests pass; the snapshot is unchanged (group names are data, not schema). If it changed, include it and `bash services/ui-neu/scripts/codegen.sh` output in the commit.

- [ ] **Step 4: Commit**

```bash
git add packages/arm_common services/backend/arm_backend/routers/settings.py services/backend/tests/test_settings_router.py
git commit -m "feat(settings): Identification and Keys config groups; wizard step shows the keys only"
```

---

### Task 2: Settings plumbing: sections, tabs, legacy hash, chip deep links

**Files:**
- Modify: `services/ui-neu/frontend/src/lib/utils/settings-sections.ts`
- Modify: `services/ui-neu/frontend/src/routes/settings/+page.svelte`
- Modify: `services/ui-neu/frontend/src/lib/components/settings/RankedListField.svelte`
- Modify: `services/ui-neu/frontend/src/lib/components/settings/SchemaConfigForm.svelte` (only `keyTab`)
- Modify: `services/ui-neu/frontend/src/routes/+layout.svelte`, `services/ui-neu/frontend/src/lib/components/MobileStatsPanel.svelte`
- Test: `lib/utils/__tests__/settings-sections.test.ts`, `routes/settings/__tests__/settings-page.test.ts`, `lib/components/settings/__tests__/RankedListField.test.ts`, `lib/components/__tests__/MobileStatsPanel.test.ts`

**Interfaces:**
- Produces: `SECTIONS.Identification` = `[{ title: 'Search', blurb, keys: [the three selects], columns: [[movie],[tv],[music]] }, { title: 'Identity', blurb, keys: [the ten Identity keys], custom: 'identity' }]`; `SECTIONS.Keys` = the three sections in Global Constraints; `SettingsSection.custom?: 'identity'` and `SectionFieldGroups.custom?: 'identity'` (a custom section keeps `columns: []`, `fields: []`, `advanced: []` and the form renders the named component with all of the group's fields); `GROUP_BLURBS` for both groups; `settingsTabFor` returns the name for `Identification`, `Keys`, `Ripping`; `export const SETTINGS_SCHEMA_CONTEXT = Symbol('settings-schema')`; `export function settingsFieldHref(key: string, groups: SettingsGroup[] | undefined): string`; `export function legacyTab(tab: string): string` mapping `Metadata` → `Identification`, `appearance` → `themes`, else identity.
- Consumed by Task 3 (`custom: 'identity'`), Task 4 (nothing), Task 5 (nothing).

- [ ] **Step 1: Write the failing tests**

`settings-sections.test.ts`: (a) `sectionFields('Identification', fields)` with metas for every Identification key yields `Search` with three single-field columns and `Identity` with `custom === 'identity'`, no field in `fields`/`columns`, and no trailing unmapped section; (b) `sectionFields('Keys', …)` yields `API keys`, `TheDiscDB`, `MakeMKV` in that order; (c) `settingsFieldHref('tvdb_api_key', [{ name: 'Keys', fields: [{ key: 'tvdb_api_key', … }] }])` is `#Keys/tvdb_api_key` and `settingsFieldHref('tvdb_api_key', undefined)` is `#setting-tvdb_api_key`; (d) `settingsTabFor('Keys') === 'Keys'`; (e) `legacyTab('Metadata') === 'Identification'`. Replace the old `Metadata` layout cases (the TV episodes section no longer exists; delete those cases).

`settings-page.test.ts`: rename the mock schema's `Metadata` group to `Identification` and add a `Keys` group holding `tmdb_api_key`; assert the tab strip order `Identification, Keys, Ripping, Sessions, …`; `window.location.hash = '#Metadata'` renders the Identification tab; `'#Metadata/tmdb_api_key'` and `'#Keys/tmdb_api_key'` both focus the TMDb field on the Keys tab (adapt the existing deep-link test); the readiness signal stays the movie search `combobox` (now on Identification).

`RankedListField.test.ts` "flags a missing key": render with `context: new Map([[SETTINGS_SCHEMA_CONTEXT, () => [{ name: 'Keys', fields: [{ key: 'tvdb_api_key', label: 'TVDb API key' }] }]]])` → chip `href="#Keys/tvdb_api_key"`, `title="Open TVDb API key"`; render without context and without `keyTab` → `href="#setting-tvdb_api_key"`.

`MobileStatsPanel.test.ts` ~line 84: expected href `/settings#Keys/makemkv_key`.

Run: `cd services/ui-neu/frontend && npx vitest run src/lib/utils src/routes/settings src/lib/components/settings/__tests__/RankedListField.test.ts src/lib/components/__tests__/MobileStatsPanel.test.ts` → failures.

- [ ] **Step 2: Implement**

`settings-sections.ts`: add `custom?: 'identity'` to both interfaces; in `sectionFields`, a section with `custom` pushes `{ title, blurb, custom, columns: [], fields: [], advanced: [] }` after marking its keys placed. Replace `SECTIONS.Metadata` with `Identification` and `Keys` per the interfaces above. `GROUP_BLURBS`: drop `Metadata`, add `Identification` and `Keys` (Global Constraints). `settingsTabFor`: `['Identification', 'Keys', 'Ripping'].includes(groupName) ? groupName : groupName.toLowerCase()`. Add `SETTINGS_SCHEMA_CONTEXT`, `settingsFieldHref`, `legacyTab`.

`+page.svelte`: `configGroupNames = ['Identification', 'Keys', 'Ripping']`; `parseHash` applies `legacyTab` before validating and falls back to `'Identification'`; `setContext(SETTINGS_SCHEMA_CONTEXT, () => settings?.schema?.groups)` at script top level; render `SchemaConfigForm` for `group('Identification')` and `group('Keys')` like the Ripping block; update the comment citing `#Metadata/makemkv_key`.

`RankedListField.svelte`: `const schemaGroups = getContext<(() => SettingsGroup[] | undefined) | undefined>(SETTINGS_SCHEMA_CONTEXT)`; `keyHref(key)` = `schemaGroups ? settingsFieldHref(key, schemaGroups()) : keyTab ? `#${keyTab(key)}/${key}` : `#setting-${key}``; `keyTab` prop default becomes `undefined`; chip gets `title={`Open ${keyLabel(missing)}`}` where `keyLabel` reads the field label from the schema groups, else `${key} key`.

`SchemaConfigForm.svelte`: `keyTab` stays for the wizard (no context there) but its fallback becomes `undefined` instead of `'Metadata'`.

`+layout.svelte` and `MobileStatsPanel.svelte`: `/settings#Keys/makemkv_key` (use `settingsFieldHref('makemkv_key', $settingsSchemaGroups)` only if a schema store already exists in the layout; otherwise the literal is fine).

- [ ] **Step 3: Verify**

```bash
cd services/ui-neu/frontend && npm run check && npx vitest run && npm run lint
```

Expected: green. (The Identity custom section renders nothing until Task 3; the settings-page test must not depend on Identity card content yet.)

- [ ] **Step 4: Commit**

```bash
git add services/ui-neu/frontend/src
git commit -m "feat(ui): Identification and Keys tabs; chips deep-link to the key's tab; legacy #Metadata hash"
```

---

### Task 3: The Identity card

**Files:**
- Create: `services/ui-neu/frontend/src/lib/utils/identity-card.ts`
- Create: `services/ui-neu/frontend/src/lib/components/settings/IdentityCard.svelte`
- Create: `services/ui-neu/frontend/src/lib/components/settings/IdentityStrip.svelte`
- Modify: `services/ui-neu/frontend/src/lib/components/settings/SchemaConfigForm.svelte` (render the custom section; drop the TV summary)
- Delete: `services/ui-neu/frontend/src/lib/components/settings/TvEpisodesSummary.svelte` and its test
- Test: `lib/utils/__tests__/identity-card.test.ts`, `lib/components/settings/__tests__/IdentityCard.test.ts`, update `SchemaConfigForm.test.ts` (remove the `tv-episodes` summary cases; add one that a `custom: 'identity'` section renders the card with `data-testid="identity-card"`)

**Interfaces:**
- `identity-card.ts`:
  ```ts
  export type DiscKind = 'bluray' | 'dvd' | 'cd';
  export const DISC_KIND_LABELS: Record<DiscKind, string> = { bluray: 'Blu-ray', dvd: 'DVD', cd: 'CD' };
  export const HINT_LABELS = { bd_title: 'Disc title metadata', label: 'Volume label' } as const;
  export const HINT_DEFAULT_ORDER = ['bd_title', 'label'] as const;
  export function hintIgnored(values: Record<string, unknown>, hint: 'bd_title' | 'label'): boolean;
  /** Returns the new disc_hint_sources with `hint` present (ignored=false) or absent, keeping the other entry and the default order. */
  export function withHintIgnored(values: Record<string, unknown>, hint: 'bd_title' | 'label', ignored: boolean): string[];
  export function enabledLabels(values: Record<string, unknown>, key: string, fields: ConfigFieldMeta[]): string[];
  export function stripCells(kind: DiscKind, values: Record<string, unknown>, fields: ConfigFieldMeta[]): RecipeCell[];  // exactly the Global Constraints table
  ```
- `IdentityCard.svelte` props: `{ values: Record<string, unknown> (bindable); fields: ConfigFieldMeta[]; config: Record<string, unknown>; keyTab?: (key: string) => string; disabled?: boolean }`. Renders the segmented control, `IdentityStrip`, Steps 1–4, Advanced. Real controls: `ConfigSchemaField` for `thediscdb_enabled`, `crc64service_enabled`, `episode_match_tolerance_seconds`, the three `*_auto_apply` (bound to `values[key]`) and `RankedListField` for the three lists (`bind:value={values[key]}`, `config={values}`, `helpId`). The Advanced boxes are plain checkboxes that call `withHintIgnored`. Root `data-testid="identity-card"`.
- `IdentityStrip.svelte` props: `{ kind: DiscKind; values; fields }` → `<RecipeStrip tone="info" cells={stripCells(kind, values, fields)} />` inside `role="group" aria-label="Identity summary"`.
- `SchemaConfigForm`: a section with `custom === 'identity'` renders `<IdentityCard bind:values fields={group.fields} config={config} {keyTab} disabled={!editable.length} />` in the panel instead of the column/field/advanced loops. `SECTION_SUMMARIES`, `TvEpisodesSummary` and `tvEpisodesEmptyNote` are removed.

- [ ] **Step 1: Helper tests (write first)**

`identity-card.test.ts` covers: `withHintIgnored` on `['bd_title','label']` ignoring `label` → `['bd_title']`; then un-ignoring → `['bd_title','label']`; on `['label']` un-ignoring `bd_title` → `['bd_title','label']`; on `[]` → `[]` stays when ignoring; a non-array value treated as the default. `stripCells` for each kind with the defaults (every switch on, default lists and labels from metas) matches the table verbatim; with `episode_sources: []` the TV part reads `No sources on`; with `thediscdb_enabled: false, crc64service_enabled: false` DVD cell 2 is `Off`; with `disc_hint_sources: []` Blu-ray cell 1 is `Disc text ignored` / `See Advanced`; with `movie_auto_apply: false` cell 4 reads `Movies: Waits for review · TV shows: Apply confident matches`; CD cell 2 is `Not used for CDs`.

Run: `npx vitest run src/lib/utils/__tests__/identity-card.test.ts` → module not found.

- [ ] **Step 2: Implement the helpers** so the tests pass.

- [ ] **Step 3: Component tests (write first)**

`IdentityCard.test.ts` (render with the thirteen metas and default values; use `renderComponent`): the radiogroup `Disc kind` has three radios with Blu-ray checked; clicking `CD` changes the strip's `Online lookup` cell to `Music: MusicBrainz`; Step 1 renders the four rows with their chips and no `input` elements; Step 2 has checkboxes `TheDiscDB disc map` and `ARM community database (CRC64)`; Step 3 shows three lists (`role="list"` named `Movie sources`, `Episode sources`/the TV field's label, `Music sources`), `Rank 1` only inside Step 3, the CDDB row `aria-disabled="true"`, and the tolerance input under TV; Step 4 three checkboxes `Movies`, `TV shows`, `Music`; Advanced: ticking `Ignore the volume label` makes the `Volume label` row read `Ignored (see Advanced)` and the bound `values.disc_hint_sources` equal `['bd_title']`; `disabled` renders every control disabled. `SchemaConfigForm.test.ts`: a group with the Identity keys and `name: 'Identification'` renders `identity-card` inside the `Identity` panel and Save still submits a changed `movie_auto_apply`.

Run → failures (component missing).

- [ ] **Step 4: Build the components and wire the form**

Layout: desktop Step 3 columns via the form's existing `schema-config-form-columns` grid class; phone stacks (the grid already collapses at the 18rem fit width). Chips: `<span class="chip chip-sm">Blu-ray</span>`. The segmented control copies `InterfaceSettings`'s `.interface-settings-segment` styles into the card's own scoped classes (`identity-card-segment`, `identity-card-segment-btn`). Step headings: `<h4 class="label-caps">Step 1 · On the disc</h4>` etc. Keep each step in its own `div.identity-card-step` with `data-step="1"`.

Delete `TvEpisodesSummary.svelte` and `__tests__/TvEpisodesSummary.test.ts`; remove its import, `SECTION_SUMMARIES`, the `summary` rendering and the `tv-episodes` empty note from `SchemaConfigForm.svelte`; drop `summary` from the `settings-sections.ts` interfaces (Task 2 may have left it; remove now and fix its tests).

- [ ] **Step 5: Verify**

```bash
cd services/ui-neu/frontend && npm run check && npx vitest run && npm run lint
```

- [ ] **Step 6: Commit**

```bash
git add services/ui-neu/frontend/src
git commit -m "feat(ui): Identity card with the four pipeline steps and the disc-kind summary strip"
```

---

### Task 4: Wizard step copy

**Files:**
- Modify: `services/ui-neu/frontend/src/lib/components/setup/steps.ts` (the `metadata` entry: `label: 'Identification'`, `title: 'Identification'`, intro per Global Constraints)
- Modify: `services/ui-neu/frontend/src/lib/components/setup/steps/MetadataStep.svelte` (copy that names services: keep the keys-only framing; the help line becomes `If you skip this step, ARM still identifies discs with TVmaze and MusicBrainz, which need no key, and you confirm the rest by hand.`)
- Test: `lib/components/setup/__tests__/steps.test.ts` and any test asserting `Find titles` (grep `Find titles` under `src`; update to `Identification`)

- [ ] **Step 1:** update the tests to the new label/title; run `npx vitest run src/lib/components/setup` → failures.
- [ ] **Step 2:** apply the copy changes; `MetadataStep.svelte`'s `commit()` keeps returning `'done'` when a TMDb or OMDb key is set, else `'attention'`.
- [ ] **Step 3:** `npm run check && npx vitest run src/lib/components/setup && npm run lint`.
- [ ] **Step 4:** `git commit -m "feat(ui): the wizard's title step is Identification"`.

---

### Task 5: Suggestion review: banner, Accept, badges

**Files:**
- Modify: `services/ui-neu/frontend/src/lib/api/jobs.ts` (`acceptIdentitySuggestion`)
- Modify: `services/ui-neu/frontend/src/lib/utils/job-status.ts` (`identitySuggestionOf`, `reviewPhaseBadge`)
- Create: `services/ui-neu/frontend/src/lib/components/IdentitySuggestionBanner.svelte`
- Modify: `services/ui-neu/frontend/src/lib/components/DiscReviewWidget.svelte`
- Modify: `services/ui-neu/frontend/src/routes/jobs/[id]/+page.svelte`
- Test: `lib/utils/__tests__/job-status.test.ts` (or the file that tests `reviewPhaseBadge`), `lib/components/__tests__/IdentitySuggestionBanner.test.ts` (new), `lib/components/__tests__/DiscReviewWidget.test.ts`, `routes/jobs/[id]/__tests__/*` (the job page test file; find it with `ls`)

**Interfaces:**
- `acceptIdentitySuggestion(jobId: string): Promise<ResolveResponse>` → `post('/api/jobs/${jobId}/identity/accept')`.
- `identitySuggestionOf(job: { metadata_json?: JobView['metadata_json'] } | null | undefined): IdentitySuggestion | null`.
- `reviewPhaseBadge`: `awaiting_review` + suggestion (and not previously ripped) → `{ label: 'CONFIRM TITLE', accent: 'var(--color-accent-4)' }`; `awaiting_user_id`/`ripped_awaiting_identify` + suggestion → same label.
- `IdentitySuggestionBanner` props: `{ job: JobView; canAct: boolean; onaccepted?: () => void; onsearch?: () => void }`; renders nothing when no suggestion; `data-testid="identity-suggestion"`; `Use this title` and `Search instead` buttons only when `canAct`; shows `errorMessage` inline when accept fails (`ApiError` detail, else `NETWORK_ERROR_MESSAGE`); disables `Use this title` while in flight.
- `PROVIDER_LABELS` lives in `job-status.ts` (exported) per Global Constraints.

- [ ] **Step 1: Tests first**

Banner: renders title, year, provider label and poster `img` from a suggestion; `Use this title` calls the mocked `acceptIdentitySuggestion` with the job id and then `onaccepted`; a rejected accept (mock throws `new ApiError(409, 'job x has no identity suggestion to accept')`) shows that detail and keeps the banner; `canAct=false` hides both buttons; no suggestion → renders nothing. Badge: the three new mappings plus previously-ripped still wins. `DiscReviewWidget`: a held job with a suggestion (fixture: `status: 'awaiting_review'`, `title: 'MY_DISC'`, `wait_start_time: null`, `metadata_json: { identity_suggestion: { provider: 'tmdb', title: 'Iron Man', year: 2008, kind: 'movie', poster_url: 'https://…/abc.jpg', external_ids: {}, payload: {}, suggested_at: '…' }, flags: { unidentified: true } }`) shows the status label `Confirm the title: use it or search`, the `CONFIRM TITLE` badge, the banner, `Start rip` still present; `Use this title` calls accept and `onrefresh`; `Search instead` opens the title search section (for a `cd` fixture, the music search). Job page: with a suggestion and an admin, the banner renders in the header area and accept reloads the detail.

- [ ] **Step 2: Implement**

`DiscReviewWidget.svelte`: `let suggestion = $derived(identitySuggestionOf(displayJob))`; status label branch `suggestion && !previousId ? 'Confirm the title: use it or search' : …` placed before the `isReviewGate` branch; render `<IdentitySuggestionBanner job={displayJob} canAct={$isAdmin} onaccepted={() => { loadDetail(); onrefresh?.(); }} onsearch={() => (isMusic ? (showMusicSearch = true) : (showTitleSearch = true))} />` after the previously-ripped block. Job page: render the banner under the header title row when `detail` has a suggestion, `canAct={$isAdmin && canResolve}`, `onaccepted={handleIdentified}`-equivalent reload, `onsearch={() => (showIdentify = true)}`.

- [ ] **Step 3: Verify**

```bash
cd services/ui-neu/frontend && npm run check && npx vitest run && npm run lint
```

- [ ] **Step 4: Commit**

```bash
git add services/ui-neu/frontend/src
git commit -m "feat(ui): confirm a held identity suggestion from the review card and the job page"
```

---

### Task 6: Spec note

**Files:**
- Modify: `docs/superpowers/specs/2026-10-14-identification-sources-design.md` (§9: mark each v4.2 item as landed in the UI PR; §10: add `- Resolved in the UI PR: the wizard step keeps its wire id "metadata" with the visible label Identification (D-9's literal setup_step rename would have changed stored progress keys); MakeMKV keeps its own step. The Playwright visual snapshots for Settings are refreshed by the owner.`)

- [ ] **Step 1:** make the two edits. **Step 2:** `git commit -m "docs(identity): v4.2 UI landed; wizard step id ruling"`.

---

## Self-review notes

- **Spec coverage.** §9 bullets: Step 2 CRC64 row (Task 3), Step 1 CD "Disc ID (track layout)" (Task 3), Step 2 copy ending (Task 3), Keys tab env-var help (Task 2), Trust help naming Ripping › Review (Task 3), tolerance help kept (Task 3 reuses the field's help). D-9 wizard (Task 4 + Task 1 tag change, with the id ruling). D-10 surfaced to the operator: Task 5 banner. Part 4 chip links: Task 2. Part 5 acceptance criteria: tab rename + Keys tab (Tasks 1–2), three selects (Task 2), Step 1 no inputs (Task 3), only Step 3 ranks (Task 3), strip per kind (Task 3), phone/wizard/dark/guest (Task 3 layout notes + guest test; dark uses tokens).
- **Why a bespoke card rather than sections.** Steps 1 and the Planned rows have no field; Step 4's three switches share one caption; Advanced inverts and sets-manipulates one ranked field. None of that fits `SectionFieldGroups`.
- **Why the wire id stays `metadata`.** `SetupStep` is a VARCHAR key in `Config.setup_progress`; renaming it means a data migration for a label.
- **Type consistency.** `custom: 'identity'` (Tasks 2, 3); `SETTINGS_SCHEMA_CONTEXT`, `settingsFieldHref` (Task 2, used by RankedListField); `stripCells`, `withHintIgnored` (Task 3); `identitySuggestionOf`, `acceptIdentitySuggestion` (Task 5).
- **Review Focus** 1 → Task 3 helper test; 2 → Task 2 settings-page test; 3 → Task 3 disabled test; 4 → Task 5 banner error test; 5 → Task 2 RankedListField test.
