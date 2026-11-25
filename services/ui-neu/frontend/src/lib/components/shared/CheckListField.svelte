<script lang="ts">
	import { checkedEntries, setChecked } from '$lib/utils/check-list';

	interface Props {
		/** The entries, in the order they show and are written. */
		options: readonly { value: string; label: string }[];
		/** The ticked values; written back in the options' order. */
		value: string[];
		/** The group's accessible name; the visible label is the caller's FieldLabel. */
		legend: string;
		/** Prefix for each checkbox's id, unique on the page. */
		idPrefix: string;
		helpId?: string;
		/** Every checkbox disabled (a read-only view). */
		disabled?: boolean;
	}

	let { options, value = $bindable(), legend, idPrefix, helpId, disabled = false }: Props = $props();

	const known = $derived(options.map((o) => o.value));
	const ticked = $derived(checkedEntries(value, known));
	const boxId = (entry: string) => `${idPrefix}-${entry}`;
</script>

<fieldset class="check-list-field" aria-describedby={helpId} {disabled}>
	<legend class="sr-only">{legend}</legend>
	{#each options as option (option.value)}
		<div class="field field-row">
			<input
				id={boxId(option.value)}
				type="checkbox"
				checked={ticked.includes(option.value)}
				onchange={(e) =>
					(value = setChecked(value, known, option.value, (e.currentTarget as HTMLInputElement).checked))}
			/>
			<label class="check-list-field-option" for={boxId(option.value)}>{option.label}</label>
		</div>
	{/each}
</fieldset>

<style>
	/* a fieldset only for grouping: no frame, the options in as many
	   columns as fit, up to a readable width. */
	.check-list-field {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr));
		gap: 0.25rem 1rem;
		max-width: 36rem;
		min-width: 0;
		margin: 0;
		padding: 0;
		border: 0;
	}
</style>
