<script lang="ts">
	import type { ConfigFieldMeta } from '$lib/types/api.gen';
	import IdentityCard from '../IdentityCard.svelte';

	// Holds the card's bound values in real $state, as SchemaConfigForm does,
	// so a test can read back what the card wrote.
	let {
		initial,
		fields,
		disabled = false
	}: { initial: Record<string, unknown>; fields: ConfigFieldMeta[]; disabled?: boolean } = $props();

	let values = $state<Record<string, unknown>>(structuredClone(initial));

	export function getValues(): Record<string, unknown> {
		return $state.snapshot(values);
	}
</script>

<IdentityCard bind:values {fields} config={initial} {disabled} />
