<script lang="ts">
	// One schema-rendered field: label row with its docs link (hover names the
	// HandBrake key), a Changed mark and Reset (once the preset stores a value),
	// the control for the key's kind, and its issue. An unstored text or number
	// field shows the inherited value as a placeholder.
	import type { SettingIssue, SlimKey } from '$lib/types/api.gen';
	import ChipPicker from './ChipPicker.svelte';
	import FieldLabel from '$lib/components/shared/FieldLabel.svelte';
	import { handbrakeDocsIds } from '$lib/docs/field-docs';
	import { errorId, invalidAttrs } from '$lib/ui/form-validation';
	import { fieldView, optionLabel, scalarText } from '$lib/handbrake/fields';
	import { languageChoices } from '$lib/handbrake/languages';
	import { PAD_CUSTOM, padColorView } from '$lib/handbrake/pad-color';
	import { formatRotate, parseRotate, ROTATE_ANGLES, type RotateAngle } from '$lib/handbrake/rotate';

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
		// Registry id of the docs for the key's input values (an encoder family);
		// defaults to the key's own entry, else its tab group's.
		docsId?: string;
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
		docsId,
		onchange,
		onreset
	}: Props = $props();

	const view = $derived(fieldView(key, { value, inherited, stored, options, range }));
	const id = $derived(`${idPrefix}tunable-${key.name}`);
	// Marks the control invalid and points it at the issue line while there is an issue.
	const invalid = $derived(invalidAttrs(id, issue?.message));
	const docs = $derived(handbrakeDocsIds(key));

	const choices = $derived(languageChoices(key.name));
	const rotate = $derived(parseRotate(scalarText(view.shown)));
	let padCustomOpen = $state(false);
	const pad = $derived(padColorView(scalarText(view.shown), (options ?? []).map(String), padCustomOpen));

	function onResetField() {
		padCustomOpen = false;
		onreset();
	}
	function onAngle(e: Event) {
		const angle = Number((e.currentTarget as HTMLSelectElement).value) as RotateAngle;
		onchange(formatRotate({ ...rotate, angle }));
	}
	function onFlip(e: Event) {
		onchange(formatRotate({ ...rotate, hflip: (e.currentTarget as HTMLInputElement).checked }));
	}
	function onPadSelect(e: Event) {
		const raw = (e.currentTarget as HTMLSelectElement).value;
		padCustomOpen = raw === PAD_CUSTOM;
		if (!padCustomOpen) onchange(raw);
	}
	function onPadText(e: Event) {
		const text = (e.currentTarget as HTMLInputElement).value;
		if (text !== '') onchange(text);
	}
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
	<div class="tunable-field" data-changed={view.stored || undefined}>
		<FieldLabel
			for={id}
			label={key.label}
			docsId={docsId ?? docs.id}
			docsFallbackId={docs.fallbackId}
			docsTitle={`HandBrake key: ${key.name}`}
		>
			{#if view.stored}<span class="changed-chip">Changed</span>{/if}
			{@render resetLink()}
		</FieldLabel>
		{#if view.kind === 'checkbox'}
			{@render checkboxControl()}
		{:else if view.kind === 'select'}
			{@render selectControl()}
		{:else if view.kind === 'rotate'}
			{@render rotateControl()}
		{:else if view.kind === 'pad-color'}
			{@render padColorControl()}
		{:else if view.kind === 'number'}
			{@render numberControl()}
		{:else if view.kind === 'chips'}
			<ChipPicker
				{id}
				values={view.chipValues}
				{options}
				{choices}
				{disabled}
				{invalid}
				onchange={(v) => onchange(v)}
			/>
		{:else}
			{@render textControl()}
		{/if}
		{#if issue}<p class="field-error" id={errorId(id)} role="alert">{issue.message}</p>{/if}
	</div>
{/if}

{#snippet resetLink()}
	{#if view.stored}
		<button type="button" class="btn-link tunable-field-reset" {disabled} onclick={onResetField}>Reset</button>
	{/if}
{/snippet}

{#snippet checkboxControl()}
	<div class="field-control-line">
		<input
			{id}
			type="checkbox"
			checked={view.shown === true}
			{disabled}
			onchange={(e) => onchange(e.currentTarget.checked)}
			{...invalid}
		/>
	</div>
{/snippet}

{#snippet selectControl()}
	<select {id} class="field-control" {disabled} onchange={onSelect} {...invalid}>
		{#if view.shown == null}<option value="" selected></option>{/if}
		{#each view.options as option (option.raw)}
			<option value={option.value} selected={option.selected}>{option.label}</option>
		{/each}
	</select>
{/snippet}

{#snippet rotateControl()}
	<div class="tunable-field-rotate">
		<select {id} class="field-control" {disabled} onchange={onAngle} {...invalid}>
			{#each ROTATE_ANGLES as angle (angle)}
				<option value={angle} selected={angle === rotate.angle}>{angle}&deg;</option>
			{/each}
		</select>
		<label class="tunable-field-inline">
			<input type="checkbox" checked={rotate.hflip} {disabled} onchange={onFlip} />
			Flip horizontally
		</label>
	</div>
{/snippet}

{#snippet padColorControl()}
	<select {id} class="field-control" value={pad.selected} {disabled} onchange={onPadSelect} {...invalid}>
		{#each options ?? [] as name (name)}
			<option value={String(name)}>{optionLabel(key, name)}</option>
		{/each}
		<option value={PAD_CUSTOM}>Custom...</option>
	</select>
	{#if pad.custom}
		<!-- With Custom chosen the rejected value sits here, so an issue marks this input too. -->
		<input
			type="text"
			class="field-control"
			aria-label="Custom padding color"
			placeholder="#rrggbb"
			value={pad.text}
			{disabled}
			onchange={onPadText}
			{...invalid}
		/>
	{/if}
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
		{...invalid}
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
		{...invalid}
	/>
{/snippet}

<style>
	.tunable-field {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		min-width: 0;
	}
	.tunable-field-inline {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.tunable-field-rotate {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}
	/* Reset sits at the end of the label row. */
	.tunable-field-reset {
		margin-left: auto;
		font-size: 0.75rem;
	}
</style>
