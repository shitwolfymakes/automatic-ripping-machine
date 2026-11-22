<script lang="ts">
	import CheckListField from '../CheckListField.svelte';

	// Holds the field's bound value in real $state, as a form does, so a test
	// can read back what the field wrote.
	let {
		initial,
		options,
		disabled = false,
		helpId
	}: {
		initial: string[];
		options: { value: string; label: string }[];
		disabled?: boolean;
		helpId?: string;
	} = $props();

	let value = $state<string[]>(structuredClone(initial));

	export function getValue(): string[] {
		return $state.snapshot(value);
	}
</script>

<CheckListField {options} bind:value legend="Music file tags" idPrefix="tags" {helpId} {disabled} />
