<script lang="ts">
	import { untrack, type Snippet } from 'svelte';
	import type { SettingsGroup, ConfigFieldMeta } from '$lib/types/api.gen';
	import { saveArmConfig } from '$lib/api/settings';
	import { saveErrorMessage } from '$lib/api/client';
	import {
		groupBlurb,
		groupLabel,
		sectionFields,
		settingsTabFor,
		KEY_CHECK_NAMES,
		KEY_SERVICE_LABEL
	} from '$lib/settings/sections';
	import { buildConfigPayload, mergeConfigValues, mergeSavedPayload } from '$lib/settings/config-payload';
	import { KeyChecks, keyToTest } from '../../stores/settings-key-checks.svelte';
	import ConfigSchemaField from './ConfigSchemaField.svelte';
	import KeyCheckResult from './KeyCheckResult.svelte';
	import Glyph from '$lib/components/shared/Glyph.svelte';
	import IdentityCard from './IdentityCard.svelte';
	import SchemaFormSection from './SchemaFormSection.svelte';

	let {
		group,
		config,
		onsaved,
		beforeSave,
		beforeSections,
		deferred = false,
		bare = false
	}: {
		group: SettingsGroup;
		config: Record<string, unknown>;
		onsaved?: (payload: Record<string, unknown>) => void;
		/** Extra content rendered after the sections, above the Save row. */
		beforeSave?: Snippet;
		/** Rendered above the first section card (non-bare forms only). */
		beforeSections?: Snippet;
		/** No Save row: the parent saves through `save()` (setup walkthrough's Continue). */
		deferred?: boolean;
		/** No title, blurb or section panels: the fields in one stack (setup steps). */
		bare?: boolean;
	} = $props();

	const editable = $derived(group.fields.filter((f: ConfigFieldMeta) => f.editable));
	const sections = $derived(sectionFields(group.name, group.fields));
	const blurb = $derived(groupBlurb(group.name));
	// A required key's field lives in this form's group when it has one; otherwise
	// the chip falls back to Settings' schema context, or the field's own anchor.
	// A setup step (`setup:<step>`) is no Settings tab: its chips use the anchor.
	const keyTab = (key: string) =>
		!group.name.startsWith('setup:') && group.fields.some((f) => f.key === key)
			? settingsTabFor(group.name)
			: undefined;

	let values = $state<Record<string, unknown>>({});

	// Each key this form has itself saved, merged over `config` to form the
	// real baseline for change detection (buildConfigPayload). Without this, a
	// revert-then-resave in one visit diffs against the original `config`
	// prop (never refreshed by the parent) and silently drops the second
	// change. Reset whenever `config` itself changes identity (e.g. the
	// parent reloads settings), since the new prop is then the ground truth.
	let savedOverrides = $state<Record<string, unknown>>({});
	let configRef: Record<string, unknown> | null = null;
	let fieldsRef: SettingsGroup['fields'] | null = null;

	$effect(() => {
		const fields = group.fields;
		const prev = configRef;
		const sameFields = fields === fieldsRef;
		const current = untrack(() => values);
		const kept = sameFields && prev ? { config: prev, values: current } : null;
		values = mergeConfigValues(fields, config, kept);
		fieldsRef = fields;
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

	/** Save the changed fields. Resolves false (with the error shown inline) on failure. */
	export async function save(): Promise<boolean> {
		saving = true;
		feedback = null;
		try {
			const payload = buildConfigPayload(editable, values, baseline(), cleared);
			await saveArmConfig(payload as never);
			const merged = mergeSavedPayload(payload, group.fields, savedOverrides, values);
			savedOverrides = merged.overrides;
			values = merged.values;
			cleared = {};
			feedback = { type: 'success', message: 'Saved' };
			onsaved?.(payload);
			return true;
		} catch (e) {
			feedback = { type: 'error', message: saveErrorMessage(e) };
			return false;
		} finally {
			saving = false;
		}
	}

	/** True when Save would send something. */
	export function isDirty(): boolean {
		return Object.keys(buildConfigPayload(editable, values, baseline(), cleared)).length > 0;
	}

	/** True when `key` holds a value after the pending edits (a saved secret counts). */
	export function isSet(key: string): boolean {
		const v = values[key];
		if (cleared[key] && (v === '' || v == null)) return false;
		return v !== null && v !== undefined && v !== '';
	}

	// -------------------------------------------------------------------
	// Per-key API key check (Settings > Metadata > API keys). Fields in
	// KEY_CHECK_NAMES get a Test button and an inline result line.
	// -------------------------------------------------------------------
	const keyChecks = new KeyChecks();
</script>

{#snippet fieldRow(field: ConfigFieldMeta, noteId?: string)}
	{#if field.key in KEY_CHECK_NAMES && field.widget == null}
		{@const result = keyChecks.results[field.key]}
		<ConfigSchemaField
			{field}
			bind:value={values[field.key]}
			config={values}
			context={config}
			hideHelp={noteId !== undefined}
			describedBy={noteId}
			onclear={() => (cleared = { ...cleared, [field.key]: true })}
		>
			{#snippet action()}
				<button
					type="button"
					onclick={() => keyChecks.run(field.key, keyToTest(values[field.key], config[field.key]))}
					disabled={keyChecks.running[field.key] || !isSet(field.key)}
					class="btn schema-config-form-key-check-btn"
				>
					{keyChecks.running[field.key] ? 'Testing...' : 'Test'}
				</button>
			{/snippet}
		</ConfigSchemaField>
		<div class="schema-config-form-key-check" data-testid="key-check-{field.key}" data-empty={!result}>
			{#if result}
				<KeyCheckResult {result} service={KEY_SERVICE_LABEL[KEY_CHECK_NAMES[field.key]]} />
			{/if}
		</div>
	{:else}
		<ConfigSchemaField
			{field}
			bind:value={values[field.key]}
			config={values}
			context={config}
			{keyTab}
			hideHelp={noteId !== undefined}
			describedBy={noteId}
			onclear={() => (cleared = { ...cleared, [field.key]: true })}
		/>
	{/if}
{/snippet}

{#snippet identityCard()}
	<IdentityCard bind:values fields={group.fields} {config} {keyTab} disabled={!editable.length} />
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
			<h2 class="schema-config-form-title" data-page-section-title>{groupLabel(group.name)}</h2>
			{#if blurb}
				<p class="schema-config-form-description mt-1">{blurb}</p>
			{/if}
		</div>

		<section class="stack stack-lg">
			{#if beforeSections}{@render beforeSections()}{/if}
			{#each sections as section (section.title)}
				<SchemaFormSection {section} {fieldRow} {identityCard} />
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
	/* the original group/section blurbs were text-sm (0.875rem/1.25rem),
	   not panel-hint's 0.75rem - panel-hint is sized for a note under a
	   form control, a visibly smaller role. */
	.schema-config-form-description {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
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
	.schema-config-form-bare {
		gap: 1.25rem;
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
