<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { ConfigFieldMeta } from '$lib/types/api.gen';

	let {
		field,
		value = $bindable(),
		action
	}: { field: ConfigFieldMeta; value: unknown; action?: Snippet } = $props();

	const HIDDEN = '<hidden>';
	const isSecret = $derived(field.tier === 'secret');
	const isHiddenSecret = $derived(isSecret && value === HIDDEN);
	const boolValue = $derived(Boolean(value));
	const displayValue = $derived(isHiddenSecret ? '' : (value ?? ''));
	const placeholder = $derived(isHiddenSecret ? '******** (set, leave blank to keep)' : '');
</script>

<div class="config-schema-field stack" id="setting-{field.key}" data-testid="setting-{field.key}">
	{#if field.type === 'bool'}
		<label class="field field-row">
			<input
				type="checkbox"
				aria-label={field.label}
				checked={boolValue}
				onchange={(e) => (value = (e.currentTarget as HTMLInputElement).checked)}
			/>
			<span class="field-label">{field.label}</span>
		</label>
	{:else}
		<div class="field-label">{field.label}</div>
		{#if !field.editable}
			<div class="mono config-schema-field-value">{value ?? '-'}</div>
		{:else}
			<!-- The control and an optional trailing action (e.g. a Check button)
			     share one row so they align regardless of the help text below. -->
			<div class="flex items-center gap-2">
				{#if field.type === 'enum'}
					<select
						aria-label={field.label}
						value={value ?? ''}
						onchange={(e) => (value = (e.currentTarget as HTMLSelectElement).value)}
						class="field-control w-full"
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
						class="field-control w-full"
					/>
				{/if}
				{#if action}{@render action()}{/if}
			</div>
		{/if}
	{/if}
	{#if field.help}
		<p class="field-help">{field.help}</p>
	{/if}
</div>

<style>
	/* scroll-mt-24 (the settings page scrolls a field to the top with an
	   offset for the sticky header) and the highlight-flash transition aren't
	   covered by any block. gap: the original was space-y-1 (0.25rem), tighter
	   than the stack-sm modifier (0.5rem). */
	.config-schema-field { gap: 0.25rem; scroll-margin-top: 6rem; border-radius: var(--radius-lg); transition: box-shadow var(--motion-base) var(--ease); }
	/* the read-only value was font-mono text-sm text-gray-500 (0.875rem/1.25rem);
	   .mono is size-neutral, so this component supplies its own original size. */
	.config-schema-field-value { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
</style>
