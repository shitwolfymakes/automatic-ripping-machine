<script lang="ts">
	import type { Snippet } from 'svelte';
	import { trackPending } from '$lib/ui/page-reveal.svelte';

	// Draws its content only once `ready`, and holds the page reveal until
	// then. For a block whose late arrival would push content below it down
	// (or above it up): it appears with the rest of the page instead.
	// Renders no wrapper element, so it does not disturb a stack's spacing.
	let { ready, children }: { ready: boolean; children: Snippet } = $props();

	trackPending(() => !ready);
</script>

{#if ready}
	{@render children()}
{/if}
