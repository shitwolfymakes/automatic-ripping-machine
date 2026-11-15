<script lang="ts">
	// One schema-rendered field: label row with Reset (once the preset stores a
	// value), the control for the key's kind, the key name, and its issue. An
	// unstored text or number field shows the inherited value as a placeholder.
	import type { SettingIssue, SlimKey } from '$lib/types/api.gen';
	import ChipPicker from './ChipPicker.svelte';
	import { fieldView } from '$lib/handbrake/fields';

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
		onchange,
		onreset
	}: Props = $props();

	const view = $derived(fieldView(key, { value, inherited, stored, options, range }));
	const id = $derived(`${idPrefix}tunable-${key.name}`);

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
	<div class={view.stored ? 'tunable-field tunable-field-stored' : 'tunable-field'}>
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
				</span>
				{@render resetLink()}
			</div>
		{:else}
			<div class="tunable-field-head">
				<label class="field-label" for={id}>{key.label}</label>
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
		<p class="tunable-field-key">{key.name}</p>
		{#if issue}<p class="field-error" role="alert">{issue.message}</p>{/if}
	</div>
{/if}

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
	.tunable-field-key {
		font-size: 0.6875rem;
		color: var(--color-text-faint);
		overflow-wrap: anywhere;
	}
	.tunable-field-reset {
		font-size: 0.75rem;
	}
</style>
