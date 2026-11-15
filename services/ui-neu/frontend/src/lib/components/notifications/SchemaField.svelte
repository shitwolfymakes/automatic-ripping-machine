<script lang="ts">
	import type { CatalogField } from '$lib/types/notifications';
	import FieldLabel from '$lib/components/shared/FieldLabel.svelte';

	let {
		field,
		value = $bindable(),
		docsId,
		onchange
	}: {
		field: CatalogField;
		value: unknown;
		// Registry id of the field's docs (notify.<service>.<field>); none for a
		// service whose docs are one link for the whole form.
		docsId?: string;
		onchange?: (v: unknown) => void;
	} = $props();

	const controlId = $props.id();
	const inputType = $derived(field.private ? 'password' : 'text');
	const label = $derived(`${field.label}${field.required ? ' *' : ''}`);

	let boolValue = $derived(Boolean(value));

	const HIDDEN = '<hidden>';
	const isPrivateHidden = $derived(field.private && value === HIDDEN);
	const displayValue = $derived(isPrivateHidden ? '' : (value ?? ''));
	const placeholder = $derived(isPrivateHidden ? '******** (set, leave blank to keep)' : '');

	function setValue(v: unknown) {
		value = v;
		onchange?.(v);
	}

	function onInput(e: Event) {
		setValue((e.currentTarget as HTMLInputElement).value);
	}
</script>

{#if field.type === 'bool'}
	<div class="field field-row">
		<input
			id={controlId}
			type="checkbox"
			aria-label={field.label}
			checked={boolValue}
			onchange={(e) => setValue(e.currentTarget.checked)}
		/>
		<FieldLabel for={controlId} {label} {docsId} />
	</div>
{:else}
	<div class="field">
		<FieldLabel for={controlId} {label} {docsId} />
		{#if field.type === 'choice'}
			<select
				id={controlId}
				aria-label={field.label}
				value={displayValue}
				onchange={(e) => setValue((e.currentTarget as HTMLSelectElement).value)}
				required={field.required}
			>
				{#if !field.required}
					<option value="">(not set)</option>
				{/if}
				{#each field.values ?? [] as opt (opt)}
					<option value={opt}>{opt}</option>
				{/each}
			</select>
		{:else if field.type === 'int' || field.type === 'float'}
			<input
				id={controlId}
				type="number"
				aria-label={field.label}
				step={field.type === 'float' ? 'any' : '1'}
				value={displayValue}
				oninput={onInput}
				required={field.required}
			/>
		{:else}
			<input
				id={controlId}
				type={inputType}
				aria-label={field.label}
				value={displayValue}
				{placeholder}
				oninput={onInput}
				required={field.required}
			/>
		{/if}
	</div>
{/if}
