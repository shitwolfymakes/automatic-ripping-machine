<script lang="ts">
	import SettingsTabs from '../SettingsTabs.svelte';
	let props: Record<string, unknown> = $props();
</script>

<SettingsTabs {...props as any}>
	{#snippet children({ text, changedOnly })}<p>body {text}|{changedOnly}</p>{/snippet}
</SettingsTabs>
