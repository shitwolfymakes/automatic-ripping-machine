<script lang="ts">
	import { trackPending } from '$lib/ui/page-reveal.svelte';

	// A panel that holds the page reveal while `pending` is true.
	let { pending }: { pending: boolean } = $props();
	trackPending(() => pending);
</script>

<p>probe</p>
