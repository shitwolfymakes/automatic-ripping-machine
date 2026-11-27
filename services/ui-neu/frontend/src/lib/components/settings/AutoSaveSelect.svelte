<script lang="ts">
	// A choice setting as a select that saves on change (no Save button), such as
	// Defaults' unidentified-disc media type. The caller saves.
	import AutoSaveRow from './AutoSaveRow.svelte';
	import FieldLabel from '$lib/components/shared/FieldLabel.svelte';

	let {
		key,
		label,
		help,
		value,
		options,
		onchange
	}: {
		key: string;
		label: string;
		help?: string | null;
		value: string;
		options: { value: string; label: string }[];
		onchange: (value: string) => void;
	} = $props();
</script>

<AutoSaveRow {key} {help}>
	<FieldLabel for="auto-save-{key}" {label} docsId={`config.${key}`} />
	<select
		id="auto-save-{key}"
		class="field-control auto-save-select"
		{value}
		onchange={(e) => onchange((e.target as HTMLSelectElement).value)}
	>
		{#each options as option (option.value)}
			<option value={option.value}>{option.label}</option>
		{/each}
	</select>
</AutoSaveRow>

<style>
	/* the shared .field-control forces width: 100%; this select sits inline in its row */
	.auto-save-select {
		width: auto;
	}
</style>
