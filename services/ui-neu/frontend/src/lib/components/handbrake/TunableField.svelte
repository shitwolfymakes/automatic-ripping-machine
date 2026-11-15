<script lang="ts">
	// One schema-rendered field: label row with a Changed mark and Reset (once the
	// preset stores a value) and an info link to the HandBrake docs (its title is
	// the HandBrake key), the control for the key's kind, and its issue. An
	// unstored text or number field shows the inherited value as a placeholder.
	import type { SettingIssue, SlimKey } from '$lib/types/api.gen';
	import ChipPicker from './ChipPicker.svelte';
	import Glyph from '$lib/components/Glyph.svelte';
	import { docUrlFor } from '$lib/handbrake/docLinks';
	import { fieldView, type TabId } from '$lib/handbrake/fields';

	interface Props {
		key: SlimKey;
		value: unknown;
		inherited: unknown;
		stored: boolean;
		options: Array<string | number> | null;
		issue?: SettingIssue;
		disabled?: boolean;
		// Prefixes the control id so one key in two cards stays unique.
		idPrefix?: string;
		// A range and step the schema key does not carry (a quality scale).
		range?: { min: number; max: number; step: number };
		// The HandBrake docs page for the key's input values; defaults to its tab group's page.
		docUrl?: string;
		onchange: (v: unknown) => void;
		onreset: () => void;
	}

	let {
		key,
		value,
		inherited,
		stored,
		options,
		issue,
		disabled = false,
		idPrefix = '',
		range,
		docUrl,
		onchange,
		onreset
	}: Props = $props();

	const view = $derived(fieldView(key, { value, inherited, stored, options, range }));
	const id = $derived(`${idPrefix}tunable-${key.name}`);
	const href = $derived(docUrl ?? docUrlFor(key.tab as TabId, key.group));

	function onSelect(e: Event) {
		const raw = (e.currentTarget as HTMLSelectElement).value;
		onchange(view.options.find((o) => o.value === raw)?.raw ?? raw);
	}
	function onNumber(e: Event) {
		const raw = (e.currentTarget as HTMLInputElement).value;
		if (raw !== '' && Number.isFinite(Number(raw))) onchange(Number(raw));
	}
</script>

<!-- The audio track list has its own editor (AudioTrackList); this field draws nothing for it. -->
{#if view.kind !== 'audio-list'}
	<div
		class={view.stored ? 'tunable-field tunable-field-stored' : 'tunable-field'}
		data-changed={view.stored || undefined}
	>
		{#if view.kind === 'checkbox'}
			<div class="tunable-field-head">
				<span class="tunable-field-inline">
					<input
						{id}
						type="checkbox"
						checked={view.shown === true}
						{disabled}
						onchange={(e) => onchange(e.currentTarget.checked)}
					/>
					<label class="field-label" for={id}>{key.label}</label>
					{@render labelExtras()}
				</span>
				{@render resetLink()}
			</div>
		{:else}
			<div class="tunable-field-head">
				<span class="tunable-field-inline">
					<label class="field-label" for={id}>{key.label}</label>
					{@render labelExtras()}
				</span>
				{@render resetLink()}
			</div>
			{#if view.kind === 'select'}
				{@render selectControl()}
			{:else if view.kind === 'number'}
				{@render numberControl()}
			{:else if view.kind === 'chips'}
				<ChipPicker {id} values={view.chipValues} {options} {disabled} onchange={(v) => onchange(v)} />
			{:else}
				{@render textControl()}
			{/if}
		{/if}
		{#if issue}<p class="field-error" role="alert">{issue.message}</p>{/if}
	</div>
{/if}

{#snippet labelExtras()}
	{#if view.stored}<span class="tunable-field-changed">Changed</span>{/if}
	<a
		class="tunable-field-info"
		{href}
		target="_blank"
		rel="noopener noreferrer"
		title={`HandBrake key: ${key.name}`}
		aria-label={`HandBrake docs for ${key.label} (${key.name})`}
	>
		<Glyph name="info" class="h-3 w-3" />
	</a>
{/snippet}

{#snippet resetLink()}
	{#if view.stored}
		<button type="button" class="btn-link tunable-field-reset" {disabled} onclick={onreset}>Reset</button>
	{/if}
{/snippet}

{#snippet selectControl()}
	<select {id} class="field-control" {disabled} onchange={onSelect}>
		{#if view.shown == null}<option value="" selected></option>{/if}
		{#each view.options as option (option.raw)}
			<option value={option.value} selected={option.selected}>{option.label}</option>
		{/each}
	</select>
{/snippet}

<!-- Unstored: the control is empty and the inherited value is its placeholder. -->
{#snippet numberControl()}
	<input
		{id}
		type="number"
		class="field-control"
		value={view.inputValue}
		placeholder={view.placeholder}
		min={view.min}
		max={view.max}
		step={view.step}
		{disabled}
		onchange={onNumber}
	/>
{/snippet}

{#snippet textControl()}
	<input
		{id}
		type="text"
		class="field-control"
		value={view.inputValue}
		placeholder={view.placeholder}
		{disabled}
		onchange={(e) => onchange(e.currentTarget.value)}
	/>
{/snippet}

<style>
	.tunable-field {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		min-width: 0;
	}
	.tunable-field-head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 0.5rem;
	}
	/* :global because the stored border must beat the shared .field-control border. */
	.tunable-field-stored :global(.field-control) {
		border-color: var(--color-border-strong);
	}
	.tunable-field-inline {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.tunable-field-changed {
		padding: 0 0.375rem;
		border-radius: 999px;
		font-size: 0.625rem;
		font-weight: 700;
		background: var(--color-info-soft);
		color: var(--color-on-info-soft);
	}
	.tunable-field-info {
		display: inline-flex;
		color: var(--color-text-faint);
	}
	.tunable-field-info:hover {
		color: var(--color-text);
	}
	.tunable-field-reset {
		font-size: 0.75rem;
	}
</style>
