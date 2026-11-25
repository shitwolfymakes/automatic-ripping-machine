<script lang="ts">
	// An on/off setting as a switch that saves on change (no Save button), such
	// as the notifications master switch or Defaults' auto-apply. The caller saves.
	import Toggle from '$lib/components/shared/Toggle.svelte';
	import FieldLabel from '$lib/components/shared/FieldLabel.svelte';
	import AutoSaveRow from './AutoSaveRow.svelte';

	let {
		key,
		label,
		help,
		checked,
		ontoggle
	}: { key: string; label: string; help?: string | null; checked: boolean; ontoggle: (next: boolean) => void } =
		$props();
</script>

<AutoSaveRow {key} {help}>
	<Toggle id="toggle-{key}" {checked} {label} onchange={ontoggle} />
	<FieldLabel for="toggle-{key}" {label} docsId={`config.${key}`} />
</AutoSaveRow>
