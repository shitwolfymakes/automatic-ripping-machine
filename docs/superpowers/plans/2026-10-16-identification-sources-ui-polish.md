# Identification Sources UI Polish: Preview Panel and Design Details — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the Identification tab in line with the owner's design mock (the "metadata screen" PDF, 2026-10-15): a Preview panel with ranked pills instead of the four-cell strip, numbered step headings, the mock's labels and sub-lines, and the MakeMKV key first on the Keys tab.

**Architecture:** UI only (no backend or arm_common change, so hifi can take it as a UI-only deploy). `IdentityStrip.svelte` becomes `IdentityPreview.svelte`, a bordered panel of labelled rows derived from the same `identity-card.ts` helpers (new `previewRows(kind, values, fields)` replaces `stripCells`). `IdentityCard.svelte` keeps its structure and changes headings, labels, the Step 4 layout and the Advanced sub-lines; the tolerance field's displayed label is overridden in the card (the metadata label stays). `settings-sections.ts` reorders the Keys sections and changes the Identification blurb.

**Tech Stack:** SvelteKit / Svelte 5, vitest, ESLint/Prettier, svelte-check.

**Spec:** the design mock (PDF, described verbatim below); `docs/superpowers/specs/2026-10-14-identification-sources-design.md` §9 still wins where it adds to the mock (Step 1 "Disc ID (track layout)" row, Step 2 CRC64 row and the "ARM confirms the title…" clause, D-10 trust help naming Review first, D-11 tolerance help). Branch: `feat/identification-sources-ui-polish` from `feat/identification-sources-docs` (PR #369).

## Global Constraints (the mock, verbatim where quoted)

- **Identification tab blurb:** `How ARM works out what a disc is, and where it looks titles up.`
- **Search card:** unchanged, plus one card-level help line under the three selects: `The service the job page's search box uses for each media type.` The three selects' own help lines are hidden inside this section (the card-level line replaces them).
- **Identity card order:** blurb, then a `Preview` block, then steps 1–4, then Advanced. One Save per tab (unchanged).
- **Preview block:** a `label-caps`-style caption `Preview`, the segmented control `Blu-ray | DVD | CD` (radiogroup, unchanged behaviour), then a bordered panel (`role="group"`, `aria-label="Identity preview"`) of rows. Each row: a muted label on the left, content on the right.
  - Row `Disc`: a sentence. Blu-ray: `Disc title metadata and volume label, then TheDiscDB`. DVD: `Volume label, then TheDiscDB and the ARM community database` (each database only when its switch is on; both off → `Volume label` alone; a hint ignored in Advanced drops out; no hint left → `Disc text ignored`). CD: `Volume label and disc ID (track layout)` (label ignored → `Disc ID (track layout)`).
  - Rows `Movies` and `TV shows` (Blu-ray and DVD views) and `Music` (CD view): numbered rank pills for the enabled sources in order (`1 TMDb` `2 OMDb`; the number in a small badge, the name beside it), then the trust text right-aligned: `Applies confident matches` when the type's switch is on, `Waits for review` when off. An empty list shows `No sources on` in place of the pills.
- **Step headings:** a small numbered badge and the title in sentence case: `1` `On the disc`, `2` `Disc database`, `3` `Online lookup`, `4` `Trust`; `Advanced` has no badge. The badge is text (`aria-hidden` with the number also in the heading's accessible name, or simply visible text) and uses the primary tint.
- **Step 1:** rows unchanged (`Disc title metadata` [Blu-ray] [UHD]; `Volume label` [All discs]; `Disc ID (track layout)` [CD]; `CD-TEXT` [CD] [Planned] muted with `Album, artist and track names. Not built yet.`); footer unchanged.
- **Step 2:** unchanged rows and descriptions (the spec's TheDiscDB clause stays).
- **Step 3:** sub-line unchanged; the tolerance field under the TV column shows the label `Episode match tolerance (seconds)` (card-level override of the displayed label; the metadata label is untouched) with its existing help.
- **Step 4:** no separate caption; three checkboxes stacked, labelled `Apply confident matches · Movies`, `Apply confident matches · TV shows`, `Apply confident matches · Music`; the existing description below.
- **Advanced:** `Ignore the disc title metadata` with the sub-line `Blu-ray and UHD only. ARM won't use the title stored on the disc and identifies it from the volume label, TheDiscDB and online lookup instead.`; `Ignore the volume label` with the sub-line `ARM won't use the volume label and identifies the disc from its title metadata, TheDiscDB and online lookup instead. A DVD with no title metadata then gets no automatic title search.`; the footer line stays `For collections where the disc's own text is usually wrong. Fix a single disc from its job page instead.`
- **Keys tab:** section order `MakeMKV`, `API keys`, `TheDiscDB`.
- Deep-link ids (`setting-<key>`) and every `data-testid` the existing tests use stay. No attribution trailers.

## Review Focus

1. Switching the segmented control to CD must change the preview rows to `Disc` and `Music` only; back to Blu-ray restores `Movies` and `TV shows` (Task 1 test).
2. Unticking OMDb under Movies must drop its pill and renumber nothing else wrongly (`1 TMDb` only) (Task 1 test).
3. Turning off `Apply confident matches · Movies` must flip the Movies row's trust text to `Waits for review` (Task 1 test).
4. The Search card's per-field help must be hidden only there; the Ripping tab's fields keep their help (Task 2 test).
5. The Keys tab renders MakeMKV first and the deep link `#Keys/makemkv_key` still focuses the field (Task 2 test).

---

### Task 1: Preview panel, headings, labels, Advanced sub-lines

**Files:**
- Modify: `services/ui-neu/frontend/src/lib/utils/identity-card.ts` (add `previewRows`; keep `stripCells` only if something else imports it, else remove it and its tests)
- Create: `services/ui-neu/frontend/src/lib/components/settings/IdentityPreview.svelte`
- Delete: `services/ui-neu/frontend/src/lib/components/settings/IdentityStrip.svelte`
- Modify: `services/ui-neu/frontend/src/lib/components/settings/IdentityCard.svelte`
- Test: `lib/utils/__tests__/identity-card.test.ts`, `lib/components/settings/__tests__/IdentityCard.test.ts`, a new `IdentityPreview.test.ts`

**Interfaces:**
```ts
export interface PreviewSource { rank: number; label: string }
export interface PreviewRow {
  key: 'disc' | 'movie' | 'tv' | 'music';
  label: 'Disc' | 'Movies' | 'TV shows' | 'Music';
  sentence?: string;            // Disc row
  sources?: PreviewSource[];    // ranked pills; [] with `empty: 'No sources on'`
  empty?: string;
  trust?: 'Applies confident matches' | 'Waits for review';
}
export function previewRows(kind: DiscKind, values: Record<string, unknown>, fields: ConfigFieldMeta[]): PreviewRow[];
```
`IdentityPreview.svelte` props `{ kind: DiscKind; values; fields }`, root `data-testid="identity-preview"`, each row `data-testid="identity-preview-<key>"`, pills `data-testid="identity-preview-pill"` with the number in `<span class="identity-preview-rank">`.

- [ ] **Step 1: helper tests first.** `previewRows('bluray', defaults)` → rows disc/movie/tv with the sentence `Disc title metadata and volume label, then TheDiscDB`, movie pills `[{1,'TMDb'},{2,'OMDb'}]`, tv pills TMDb/TVmaze/TVDB, trust `Applies confident matches`; `'dvd'` with CRC64 on → `Volume label, then TheDiscDB and the ARM community database`; both databases off → `Volume label`; `'cd'` → disc `Volume label and disc ID (track layout)` and a single `music` row with `[{1,'MusicBrainz'}]`; `disc_hint_sources: []` on Blu-ray → `Disc text ignored`; `movie_sources: []` → `sources: []`, `empty: 'No sources on'`; `movie_auto_apply: false` → movie trust `Waits for review`. Run → fail.
- [ ] **Step 2: implement `previewRows`**; remove `stripCells` and its tests if unused.
- [ ] **Step 3: component tests first.** `IdentityPreview` renders the three rows with pills and trust for Blu-ray; `IdentityCard`: the `Preview` caption exists; selecting CD leaves rows `Disc` and `Music` only; unticking OMDb in Step 3 removes its pill; unticking `Apply confident matches · Movies` flips the trust text; headings read `1 On the disc` … `4 Trust` (query by heading role with the accessible name); Step 4 has no separate caption; the tolerance label reads `Episode match tolerance (seconds)`; Advanced sub-lines present. Update existing tests that asserted the old `Step 1 · …` headings, the caption, or strip text. Run → fail.
- [ ] **Step 4: implement.** Preview panel markup and scoped CSS (bordered panel, rows as a two-column grid with the label in muted small caps, pills as `chip chip-sm` with a tinted rank badge, trust text right-aligned and muted, stacking on phone). Headings: `<h4 class="identity-card-heading"><span class="identity-card-badge" aria-hidden="true">1</span>On the disc</h4>` with `aria-label="1 On the disc"` on the heading if the badge is hidden from AT. Step 4 labels and the removed caption. Tolerance label override: `field={{ ...tolerance, label: 'Episode match tolerance (seconds)' }}`. Advanced sub-lines as `field-help` under each box.
- [ ] **Step 5:** `npm run check && npx vitest run && npm run lint`; pre-commit eslint/prettier on touched files. Commit `style(ui): Identity card preview panel, numbered steps, design labels` (no trailers).

---

### Task 2: Search help line, tab blurb, Keys order

**Files:**
- Modify: `services/ui-neu/frontend/src/lib/utils/settings-sections.ts` (`GROUP_BLURBS.Identification`; `SECTIONS.Keys` order; a `note?: string` on `SettingsSection`/`SectionFieldGroups` for the Search card and a `hideFieldHelp?: true` flag honoured by `SchemaConfigForm`)
- Modify: `services/ui-neu/frontend/src/lib/components/settings/SchemaConfigForm.svelte` (render `section.note` under the columns; pass `hideHelp` into `ConfigSchemaField` for sections with `hideFieldHelp`)
- Modify: `services/ui-neu/frontend/src/lib/components/settings/ConfigSchemaField.svelte` (`hideHelp?: boolean` prop; when true, skip the `field-help` paragraph but keep `aria-describedby` pointing at the section note's id)
- Test: `lib/utils/__tests__/settings-sections.test.ts`, `lib/components/settings/__tests__/SchemaConfigForm.test.ts`, `routes/settings/__tests__/settings-page.test.ts`

- [ ] **Step 1: tests first.** Keys sections order `MakeMKV, API keys, TheDiscDB`; `sectionFields('Identification', …)` Search section has `note` = the help line and `hideFieldHelp` true; `SchemaConfigForm` renders the note once and no per-field help for the Search fields, while a Ripping group still shows field help; settings page: `#Keys/makemkv_key` focuses the MakeMKV field with MakeMKV as the first section heading. Run → fail.
- [ ] **Step 2: implement**; blurb `How ARM works out what a disc is, and where it looks titles up.`
- [ ] **Step 3:** `npm run check && npx vitest run && npm run lint`; pre-commit hooks. Commit `style(ui): Keys tab leads with MakeMKV; Search card help line; Identification blurb` (no trailers).

---

## Self-review notes

- Every mock string is quoted in Global Constraints; the spec's additions (Disc ID row, CRC64 row and clause, trust help naming Review first, tolerance help) stay because the spec postdates the mock.
- UI-only by design so hifi takes a `docker compose build arm-ui` deploy; the tolerance label is overridden in the card for that reason.
- Review Focus 1–3 → Task 1 tests; 4–5 → Task 2 tests.
