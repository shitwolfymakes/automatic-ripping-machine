<script lang="ts">
	import PageReveal from '../PageReveal.svelte';
	import PendingProbe from './PendingProbe.svelte';

	// A PageReveal around one panel whose pending flag the test drives.
	let { pending, showProbe = true }: { pending: boolean; showProbe?: boolean } = $props();
</script>

<PageReveal>
	<h1>Page</h1>
	{#if showProbe}
		<PendingProbe {pending} />
	{/if}
</PageReveal>
