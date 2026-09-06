<script lang="ts">
	import type { CatalogField } from '$lib/types/notifications';
	import { FIELD_INPUT_CLASS } from '$lib/types/notifications';

	let {
		field,
		value = $bindable(),
		onchange
	}: { field: CatalogField; value: unknown; onchange?: (v: unknown) => void } = $props();

	const inputType = $derived(field.private ? 'password' : 'text');

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
	<label class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
		<input
			type="checkbox"
			aria-label={field.label}
			checked={boolValue}
			onchange={(e) => setValue(e.currentTarget.checked)}
			class="rounded border-primary/40 text-primary focus:ring-primary"
		/>
		<span>{field.label}{field.required ? ' *' : ''}</span>
	</label>
{:else}
	<label class="flex flex-col gap-1">
		<span class="text-sm font-medium text-gray-700 dark:text-gray-300">{field.label}{field.required ? ' *' : ''}</span>
		{#if field.type === 'choice'}
			<select
				aria-label={field.label}
				value={displayValue}
				onchange={(e) => setValue((e.currentTarget as HTMLSelectElement).value)}
				required={field.required}
				class={FIELD_INPUT_CLASS}
			>
				{#each field.values ?? [] as opt}
					<option value={opt}>{opt}</option>
				{/each}
			</select>
		{:else if field.type === 'int' || field.type === 'float'}
			<input
				type="number"
				aria-label={field.label}
				step={field.type === 'float' ? 'any' : '1'}
				value={displayValue}
				oninput={onInput}
				required={field.required}
				class={FIELD_INPUT_CLASS}
			/>
		{:else}
			<input
				type={inputType}
				aria-label={field.label}
				value={displayValue}
				{placeholder}
				oninput={onInput}
				required={field.required}
				class={FIELD_INPUT_CLASS}
			/>
		{/if}
	</label>
{/if}
