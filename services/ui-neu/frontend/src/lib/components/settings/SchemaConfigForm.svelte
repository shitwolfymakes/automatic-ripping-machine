<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { SettingsGroup, ConfigFieldMeta, KeyCheckResponse } from '$lib/types/api.gen';
	import { saveArmConfig, checkApiKey } from '$lib/api/settings';
	import { ApiError, NETWORK_ERROR_MESSAGE } from '$lib/api/client';
	import { groupBlurb, sectionFields, KEY_CHECK_NAMES, KEY_SERVICE_LABEL } from '$lib/utils/settings-sections';
	import { formatDateTime } from '$lib/utils/format';
	import { unchanged } from '$lib/utils/unchanged';
	import ConfigSchemaField from './ConfigSchemaField.svelte';
	import Glyph from '$lib/components/Glyph.svelte';
	import TvEpisodesSummary, { tvEpisodesEmptyNote } from './TvEpisodesSummary.svelte';

	const SECTION_SUMMARIES = { 'tv-episodes': TvEpisodesSummary };

	let {
		group,
		config,
		onsaved,
		beforeSave,
		deferred = false,
		bare = false
	}: {
		group: SettingsGroup;
		config: Record<string, unknown>;
		onsaved?: (payload: Record<string, unknown>) => void;
		/** Extra content rendered after the sections, above the Save row. */
		beforeSave?: Snippet;
		/** No Save row: the parent saves through `save()` (setup walkthrough's Continue). */
		deferred?: boolean;
		/** No title, blurb or section panels: the fields in one stack (setup steps). */
		bare?: boolean;
	} = $props();

	const HIDDEN = '<hidden>';
	const editable = $derived(group.fields.filter((f: ConfigFieldMeta) => f.editable));
	const sections = $derived(sectionFields(group.name, group.fields));
	const blurb = $derived(groupBlurb(group.name));

	let values = $state<Record<string, unknown>>({});

	// Each key this form has itself saved, merged over `config` to form the
	// real baseline for change detection (buildPayload). Without this, a
	// revert-then-resave in one visit diffs against the original `config`
	// prop (never refreshed by the parent) and silently drops the second
	// change. Reset whenever `config` itself changes identity (e.g. the
	// parent reloads settings), since the new prop is then the ground truth.
	let savedOverrides = $state<Record<string, unknown>>({});
	let configRef: Record<string, unknown> | null = null;

	$effect(() => {
		const next: Record<string, unknown> = {};
		for (const f of group.fields) next[f.key] = config[f.key];
		values = next;
		if (config !== configRef) {
			configRef = config;
			savedOverrides = {};
		}
	});

	let saving = $state(false);
	let feedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);
	// Saved secrets the operator removed: sent as null (an empty secret field
	// otherwise means "keep the stored value").
	let cleared = $state<Record<string, boolean>>({});

	function baseline(): Record<string, unknown> {
		return { ...config, ...savedOverrides };
	}

	function buildPayload(): Record<string, unknown> {
		const base = baseline();
		const out: Record<string, unknown> = {};
		for (const f of editable) {
			const v = values[f.key];
			if (f.tier === 'secret' && cleared[f.key] && (v === '' || v == null)) {
				out[f.key] = null;
				continue;
			}
			if (f.tier === 'secret' && (v === HIDDEN || v === '' || v == null)) continue;
			if (unchanged(v, base[f.key])) continue;
			out[f.key] = v;
		}
		return out;
	}

	/** Save the changed fields. Resolves false (with the error shown inline) on failure. */
	export async function save(): Promise<boolean> {
		saving = true;
		feedback = null;
		try {
			const payload = buildPayload();
			await saveArmConfig(payload as never);
			const mergedOverrides = { ...savedOverrides };
			const mergedValues = { ...values };
			for (const key of Object.keys(payload)) {
				const field = group.fields.find((f) => f.key === key);
				if (field?.tier === 'secret') {
					// Never keep the raw secret around as a comparison baseline (or
					// on screen) once it is saved - both fall back to the masked
					// sentinel, same as an untouched secret on load.
					mergedOverrides[key] = HIDDEN;
					mergedValues[key] = HIDDEN;
				} else {
					mergedOverrides[key] = payload[key];
				}
			}
			savedOverrides = mergedOverrides;
			values = mergedValues;
			cleared = {};
			feedback = { type: 'success', message: 'Saved' };
			onsaved?.(payload);
			return true;
		} catch (e) {
			// An ApiError message is already the 400 backend detail (or a
			// generic "API {status}: {statusText}"); anything else (fetch itself
			// throwing) means the request never reached the server.
			const message = e instanceof ApiError ? e.message : NETWORK_ERROR_MESSAGE;
			feedback = { type: 'error', message };
			return false;
		} finally {
			saving = false;
		}
	}

	/** True when Save would send something. */
	export function isDirty(): boolean {
		return Object.keys(buildPayload()).length > 0;
	}

	/** True when `key` holds a value after the pending edits (a saved secret counts). */
	export function isSet(key: string): boolean {
		const v = values[key];
		if (cleared[key] && (v === '' || v == null)) return false;
		return v !== null && v !== undefined && v !== '';
	}

	// -------------------------------------------------------------------
	// Per-key API key check (Settings > Metadata > API keys). Fields in
	// KEY_CHECK_NAMES get a Check/Status button + inline result line.
	// -------------------------------------------------------------------
	let keyCheckRunning = $state<Record<string, boolean>>({});
	let keyCheckResult = $state<Record<string, KeyCheckResponse | null>>({});

	function unsavedValueFor(fieldKey: string): string | undefined {
		const v = values[fieldKey];
		if (typeof v !== 'string' || v === '' || v === HIDDEN) return undefined;
		if (v === config[fieldKey]) return undefined;
		return v;
	}

	async function runKeyCheck(fieldKey: string) {
		const name = KEY_CHECK_NAMES[fieldKey];
		if (!name) return;
		keyCheckRunning = { ...keyCheckRunning, [fieldKey]: true };
		try {
			const result = await checkApiKey(name, unsavedValueFor(fieldKey));
			keyCheckResult = { ...keyCheckResult, [fieldKey]: result };
		} catch (e) {
			keyCheckResult = {
				...keyCheckResult,
				[fieldKey]: {
					name,
					status: 'error',
					detail: e instanceof Error ? e.message : 'check failed',
					checked_at: null
				}
			};
		} finally {
			keyCheckRunning = { ...keyCheckRunning, [fieldKey]: false };
		}
	}
</script>

{#snippet fieldRow(field: ConfigFieldMeta)}
	{#if field.key in KEY_CHECK_NAMES && field.widget == null}
		<ConfigSchemaField
			{field}
			bind:value={values[field.key]}
			config={values}
			context={config}
			onclear={() => (cleared = { ...cleared, [field.key]: true })}
		>
			{#snippet action()}
				<button
					type="button"
					onclick={() => runKeyCheck(field.key)}
					disabled={keyCheckRunning[field.key] || !isSet(field.key)}
					class="btn schema-config-form-key-check-btn"
				>
					{keyCheckRunning[field.key] ? 'Testing...' : 'Test'}
				</button>
			{/snippet}
		</ConfigSchemaField>
		<div
			class="schema-config-form-key-check"
			data-testid="key-check-{field.key}"
			data-empty={!keyCheckResult[field.key]}
		>
			{#if keyCheckResult[field.key]}
				{@const result = keyCheckResult[field.key]}
				{#if result?.status === 'ok'}
					<span class="flex items-center gap-1.5 schema-config-form-key-check-success">
						<Glyph name="check-circle" class="shrink-0" />
						<strong>Works</strong>{#if result.detail}, {result.detail}{/if}{#if result.checked_at}<span class="mx-1"
								>&middot;</span
							>checked {formatDateTime(result.checked_at)}{/if}
					</span>
				{:else if result?.status === 'invalid'}
					<span class="flex items-center gap-1.5 schema-config-form-key-check-danger">
						<Glyph name="x-circle" class="shrink-0" />
						<strong>Key rejected</strong>
					</span>
					{#if result.detail}<p class="mono schema-config-form-key-check-detail">{result.detail}</p>{/if}
				{:else if result?.status === 'missing'}
					<span class="flex items-center gap-1.5 schema-config-form-key-check-muted">
						<Glyph name="info" class="shrink-0" />
						No key set
					</span>
				{:else if result?.status === 'unknown'}
					<span class="flex items-center gap-1.5 schema-config-form-key-check-warning">
						<Glyph name="question-circle" class="shrink-0" />
						{result.detail}
					</span>
				{:else if result}
					<span class="flex items-center gap-1.5 schema-config-form-key-check-warning">
						<Glyph name="warning" class="shrink-0" />
						<strong>Couldn't reach {KEY_SERVICE_LABEL[KEY_CHECK_NAMES[field.key]]}</strong>
					</span>
					{#if result.detail}<p class="mono schema-config-form-key-check-detail">{result.detail}</p>{/if}
				{/if}
			{/if}
		</div>
	{:else}
		<ConfigSchemaField
			{field}
			bind:value={values[field.key]}
			config={values}
			context={config}
			onclear={() => (cleared = { ...cleared, [field.key]: true })}
		/>
	{/if}
{/snippet}

<div class="flex flex-col gap-6">
	{#if bare}
		<div class="stack schema-config-form-bare">
			{#each sections.flatMap((sec) => [...sec.columns.flat(), ...sec.fields, ...sec.advanced]) as field (field.key)}
				{@render fieldRow(field)}
			{/each}
		</div>
		{#if deferred && feedback?.type === 'error'}
			<div class="alert alert-danger flex items-center gap-1.5" role="alert">
				<Glyph name="x-circle" class="shrink-0" />
				<span><strong>Couldn't save settings.</strong> {feedback.message}</span>
			</div>
		{/if}
	{:else}
		<div>
			<h2 class="schema-config-form-title">{group.name}</h2>
			{#if blurb}
				<p class="schema-config-form-description mt-1">{blurb}</p>
			{/if}
		</div>

		<section class="stack stack-lg">
			{#each sections as section (section.title)}
				<div data-testid="settings-section" class="panel schema-config-form-panel">
					<h3 class="schema-config-form-section-title">{section.title}</h3>
					{#if section.blurb}
						<p class="schema-config-form-description schema-config-form-section-blurb">{section.blurb}</p>
					{:else}
						<div class="schema-config-form-section-blurb"></div>
					{/if}
					{#if section.summary}
						{@const Summary = SECTION_SUMMARIES[section.summary]}
						{#if Summary}
							<Summary {values} fields={group.fields} />
						{/if}
					{/if}
					{#if section.columns.length > 0}
						<div class="schema-config-form-columns" data-testid="settings-section-columns">
							{#each section.columns as columnFields, i (i)}
								<div class="stack">
									{#each columnFields as field (field.key)}
										{@render fieldRow(field)}
									{/each}
								</div>
							{/each}
						</div>
					{/if}
					{#if section.summary === 'tv-episodes'}
						{@const emptyNote = tvEpisodesEmptyNote(values)}
						{#if emptyNote}
							<p class="schema-config-form-description mb-4" data-testid="tv-episodes-empty-note">{emptyNote}</p>
						{/if}
					{/if}
					<div class="stack">
						{#each section.fields as field (field.key)}
							{@render fieldRow(field)}
						{/each}
					</div>
					{#if section.advanced.length > 0}
						<hr class="schema-config-form-advanced-divider" />
						<span class="schema-config-form-advanced-label">Advanced</span>
						<div class="stack">
							{#each section.advanced as field (field.key)}
								{@render fieldRow(field)}
							{/each}
						</div>
					{/if}
				</div>
			{/each}
		</section>
	{/if}

	{#if beforeSave}{@render beforeSave()}{/if}

	{#if editable.length > 0 && !deferred}
		<div class="flex items-center gap-3">
			<button onclick={save} disabled={saving} class="btn btn-primary">
				{saving ? 'Saving...' : 'Save'}
			</button>
			{#if feedback?.type === 'error'}
				<div class="alert alert-danger flex items-center gap-1.5" role="alert">
					<Glyph name="x-circle" class="shrink-0" />
					<span><strong>Couldn't save settings.</strong> {feedback.message}</span>
				</div>
			{:else if feedback}
				<span class="schema-config-form-feedback flex items-center gap-1.5">
					<Glyph name="check-circle" class="shrink-0" />
					{feedback.message}
				</span>
			{/if}
		</div>
	{/if}
</div>

<style>
	.schema-config-form-title {
		font-size: 1.125rem;
		line-height: 1.75rem;
		font-weight: 600;
		color: var(--color-text);
	}
	/* the original settings-section panel was p-6 (1.5rem), not .panel's
	   own p-4 (1rem) default. */
	.schema-config-form-panel {
		padding: 1.5rem;
	}
	/* the original group/section blurbs were text-sm (0.875rem/1.25rem),
	   not panel-hint's 0.75rem - panel-hint is sized for a note under a
	   form control, a visibly smaller role. */
	.schema-config-form-description {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	.schema-config-form-section-title {
		margin-bottom: 0.25rem;
		font-size: 1rem;
		line-height: 1.5rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.schema-config-form-section-blurb {
		margin-bottom: 1rem;
	}
	/* columns: side by side on desktop, stacked on mobile - the fit-width
	   minimum (18rem) is what collapses the grid to one column on a narrow
	   panel without a media query. */
	.schema-config-form-columns {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
		gap: 1.5rem;
		margin-bottom: 1rem;
	}
	.schema-config-form-advanced-divider {
		margin: 0.5rem 0 1rem;
		border: none;
		border-top: 1px solid var(--color-border);
	}
	/* the session-card-recipe-label look (SessionCard.svelte), restated here
	   since this is its only other consumer - not yet a shared block. */
	.schema-config-form-advanced-label {
		display: block;
		margin-bottom: 0.5rem;
		font-size: 0.75rem;
		line-height: calc(1 / 0.75);
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.025em;
		color: var(--color-text-faint);
	}
	.schema-config-form-key-check {
		font-size: 0.875rem;
		line-height: 1.25rem;
	}
	/* .stack's flex gap is unconditional between every child, unlike the
	   original margin-based space-y-4 stack, where this div's own top/bottom
	   margins collapsed through it when it held no content (an empty block
	   box with no border/padding) - display:none removes it from the flex
	   layout entirely so an empty result row costs no gap, matching that
	   collapse instead of adding a second, uncollapsed gap unit. */
	.schema-config-form-key-check[data-empty='true'] {
		display: none;
	}
	.schema-config-form-key-check-success {
		color: var(--color-success);
	}
	.schema-config-form-key-check-danger {
		color: var(--color-danger);
	}
	.schema-config-form-key-check-warning {
		color: var(--color-on-warning-soft);
	}
	.schema-config-form-key-check-detail {
		margin-top: 0.25rem;
		font-size: 0.75rem;
		color: var(--color-text-muted);
		overflow-wrap: anywhere;
	}
	.schema-config-form-bare {
		gap: 1.25rem;
	}
	.schema-config-form-key-check-muted {
		color: var(--color-text-muted);
	}
	/* success only now - a rejected save renders the alert-danger block above
	   instead. */
	.schema-config-form-feedback {
		font-size: 0.875rem;
		color: var(--color-text-muted);
	}
	/* the original was px-3 py-2 text-sm - .btn's own default size, not
	   .btn-sm's compact one, but at a 0.75rem horizontal padding rather
	   than .btn's 1rem. Its border was border-primary/20 (--color-border)
	   with muted text (text-gray-700), not .btn's default
	   border-primary-strong + primary text. It never wrapped, so keep the
	   label on one line at the narrow mobile width. */
	.schema-config-form-key-check-btn {
		white-space: nowrap;
		padding-inline: 0.75rem;
		border-color: var(--color-border);
		color: var(--color-text-secondary);
	}
</style>
