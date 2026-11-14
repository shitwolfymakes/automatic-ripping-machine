<script lang="ts">
	import type { Snippet } from 'svelte';
	import type { ConfigFieldMeta } from '$lib/types/api.gen';
	import Glyph from '$lib/components/shared/Glyph.svelte';
	import { HIDDEN_SECRET } from '$lib/api/config';
	import { readOnlyValue } from '$lib/settings/config-field';
	import RankedListField from './RankedListField.svelte';
	import MakemkvKeyField from './MakemkvKeyField.svelte';
	import DiscHandlingField from './DiscHandlingField.svelte';
	import SecretStatus from './SecretStatus.svelte';
	import SecretInput from './SecretInput.svelte';

	// `config` (the live form values, keyed by field key) lets a field type
	// read a sibling's value - the `ranked` branch below uses it to flag a
	// source whose required API key isn't set, and widgets write their
	// `part_of` siblings through it. `context` is the full saved config, for
	// widgets that read a value outside the form (setup steps render a subset).
	// `onclear` reports that a saved secret was removed (the form sends null).
	let {
		field,
		value = $bindable(),
		action,
		config = {},
		context = {},
		onclear,
		keyTab,
		disabled = false,
		hideHelp = false,
		describedBy
	}: {
		field: ConfigFieldMeta;
		value: unknown;
		action?: Snippet;
		config?: Record<string, unknown>;
		context?: Record<string, unknown>;
		onclear?: () => void;
		/** Settings tab holding a required key's field, for ranked-list deep links. */
		keyTab?: (key: string) => string | undefined;
		/** The editable control rendered but disabled (a guest's view of a bespoke card). */
		disabled?: boolean;
		/** Skip the field's own help paragraph (a section note covers it). */
		hideHelp?: boolean;
		/** Id of the element describing the control, instead of the field's own help. */
		describedBy?: string;
	} = $props();

	const isSecret = $derived(field.tier === 'secret');
	const isHiddenSecret = $derived(isSecret && value === HIDDEN_SECRET);
	let removed = $state(false);

	function removeSecret() {
		value = null;
		removed = true;
		onclear?.();
	}
	const boolValue = $derived(Boolean(value));
	const helpId = $derived(field.help ? `setting-help-${field.key}` : undefined);
</script>

<div class="config-schema-field stack" id="setting-{field.key}" data-testid="setting-{field.key}">
	{#if field.widget === 'makemkv_key' && field.editable}
		<MakemkvKeyField {field} bind:value {onclear} />
	{:else if field.widget === 'disc_handling' && field.editable}
		<DiscHandlingField values={config} {context} />
	{:else if !field.editable}
		<!-- A read-only field is a plain muted value under the label, not a
		     disabled control, so every non-editable field in this
		     schema-driven form reads the same regardless of type. -->
		<div class="field-label">{field.label}</div>
		<div class="mono config-schema-field-value">{readOnlyValue(field, value)}</div>
	{:else if field.type === 'bool'}
		<label class="field field-row">
			<input
				type="checkbox"
				aria-label={field.label}
				checked={boolValue}
				{disabled}
				onchange={(e) => (value = (e.currentTarget as HTMLInputElement).checked)}
			/>
			<span class="field-label">{field.label}</span>
		</label>
	{:else if field.type === 'ranked'}
		<div class="field-label">{field.label}</div>
		<RankedListField {field} bind:value {config} {helpId} {keyTab} {disabled} />
	{:else}
		<div class="field-label">{field.label}</div>
		<!-- The control and an optional trailing action (e.g. a Check button)
		     share one row so they align regardless of the help text below. -->
		<div class="flex items-center gap-2">
			{#if field.type === 'enum'}
				<select
					aria-label={field.label}
					aria-describedby={describedBy}
					value={value ?? ''}
					{disabled}
					onchange={(e) => (value = (e.currentTarget as HTMLSelectElement).value)}
					class="field-control w-full"
				>
					{#each field.enum_values ?? [] as opt (opt)}
						<option value={opt}>{field.enum_labels?.[opt] ?? opt}</option>
					{/each}
				</select>
			{:else if field.type === 'int'}
				<!-- Compact: an int field reads as a short number, not a full-width
				     text box. Emits a number (or null when emptied), never a string -
				     no min/max here, the backend's 400 on an out-of-range value is
				     the validation (see SchemaConfigForm's save-error alert). -->
				<input
					type="number"
					step="1"
					inputmode="numeric"
					aria-label={field.label}
					aria-describedby={describedBy}
					value={value ?? ''}
					{disabled}
					oninput={(e) => {
						const raw = (e.currentTarget as HTMLInputElement).value;
						value = raw === '' ? null : Number(raw);
					}}
					class="field-control config-schema-field-number"
				/>
			{:else if isSecret}
				<SecretInput
					bind:value
					aria-label={field.label}
					aria-describedby={describedBy}
					revealLabel="Show hidden value"
					oninput={() => (removed = false)}
					class="field-control w-full"
				/>
			{:else}
				<input
					type="text"
					aria-label={field.label}
					aria-describedby={describedBy}
					value={value ?? ''}
					oninput={(e) => (value = (e.currentTarget as HTMLInputElement).value)}
					class="field-control w-full"
				/>
			{/if}
			{#if action}{@render action()}{/if}
		</div>
		{#if field.signup_url}
			<a class="config-schema-field-signup" href={field.signup_url} target="_blank" rel="noopener noreferrer">
				Get a free key <Glyph name="external-link" class="h-3.5 w-3.5" />
			</a>
		{/if}
		<SecretStatus saved={isHiddenSecret} {removed} onremove={removeSecret} />
	{/if}
	{#if field.help && field.widget == null && !hideHelp}
		<p class="field-help" id={helpId}>{field.help}</p>
	{/if}
</div>

<style>
	/* scroll-mt-24 (the settings page scrolls a field to the top with an
	   offset for the sticky header) and the highlight-flash transition aren't
	   covered by any block. gap: the original was space-y-1 (0.25rem), tighter
	   than the stack-sm modifier (0.5rem). */
	.config-schema-field {
		gap: 0.25rem;
		scroll-margin-top: 6rem;
		border-radius: var(--radius-lg);
		transition: box-shadow var(--motion-base) var(--ease);
	}
	/* the read-only value was font-mono text-sm text-gray-500 (0.875rem/1.25rem);
	   .mono is size-neutral, so this component supplies its own original size. */
	.config-schema-field-value {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	.config-schema-field-signup {
		display: inline-flex;
		align-self: flex-start;
		align-items: center;
		gap: 0.25rem;
		font-size: 0.8125rem;
	}
	/* an int field is a short number, not a full-width text box. */
	.config-schema-field-number {
		width: 8rem;
	}
</style>
