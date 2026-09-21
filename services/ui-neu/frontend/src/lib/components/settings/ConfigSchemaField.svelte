<script lang="ts">
	import type { ConfigFieldMeta } from '$lib/types/api.gen';

	let { field, value = $bindable() }: { field: ConfigFieldMeta; value: unknown } = $props();

	const HIDDEN = '<hidden>';
	const isSecret = $derived(field.tier === 'secret');
	const isHiddenSecret = $derived(isSecret && value === HIDDEN);
	const boolValue = $derived(Boolean(value));
	const displayValue = $derived(isHiddenSecret ? '' : (value ?? ''));
	const placeholder = $derived(isHiddenSecret ? '******** (set, leave blank to keep)' : '');

	const inputClass =
		'w-full rounded-lg border border-primary/25 bg-primary/5 px-3 py-2 text-sm dark:border-primary/30 dark:bg-primary/10 dark:text-white';
</script>

<div class="space-y-1">
	{#if field.type === 'bool'}
		<label class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
			<input
				type="checkbox"
				aria-label={field.label}
				checked={boolValue}
				onchange={(e) => (value = (e.currentTarget as HTMLInputElement).checked)}
			/>
			<span class="font-medium">{field.label}</span>
		</label>
	{:else}
		<div class="text-sm font-medium text-gray-700 dark:text-gray-300">{field.label}</div>
		{#if !field.editable}
			<div class="font-mono text-sm text-gray-500 dark:text-gray-400">{value ?? '-'}</div>
		{:else if field.type === 'enum'}
			<select
				aria-label={field.label}
				value={value ?? ''}
				onchange={(e) => (value = (e.currentTarget as HTMLSelectElement).value)}
				class={inputClass}
			>
				{#each field.enum_values ?? [] as opt}
					<option value={opt}>{opt}</option>
				{/each}
			</select>
		{:else}
			<input
				type={isSecret ? 'password' : 'text'}
				aria-label={field.label}
				value={displayValue}
				{placeholder}
				oninput={(e) => (value = (e.currentTarget as HTMLInputElement).value)}
				class={inputClass}
			/>
		{/if}
	{/if}
	{#if field.help}
		<p class="text-xs text-gray-500 dark:text-gray-400">{field.help}</p>
	{/if}
</div>
