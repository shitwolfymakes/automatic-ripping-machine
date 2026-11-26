<script lang="ts">
	import PageReveal from '$lib/components/layout/PageReveal.svelte';
	import HoldUntil from '../HoldUntil.svelte';

	// A PageReveal around one HoldUntil block whose readiness the test drives.
	let { ready }: { ready: boolean } = $props();
</script>

<PageReveal>
	<h1>Page</h1>
	<HoldUntil {ready}>
		<p>held content</p>
	</HoldUntil>
</PageReveal>
