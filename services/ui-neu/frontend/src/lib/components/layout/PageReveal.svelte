<script lang="ts">
	import type { Snippet } from 'svelte';
	import { onNavigate } from '$app/navigation';
	import { PageRevealState, providePageReveal } from '$lib/ui/page-reveal.svelte';

	// Wraps the routed page: hidden until its panels have data, then one fade
	// in (see page-reveal.svelte.ts). A move to another route starts over; a
	// param change on the same route (another job, another help page) keeps
	// the page on screen.
	let { children }: { children: Snippet } = $props();

	const reveal = new PageRevealState();
	providePageReveal(reveal);
	reveal.begin();

	onNavigate((nav) => {
		if (nav.from?.route.id !== nav.to?.route.id) reveal.begin();
	});
	$effect(() => () => reveal.dispose());
</script>

<div class="page-reveal" data-revealed={reveal.revealed} aria-busy={!reveal.revealed}>
	{@render children()}
</div>

<style>
	/* Hide instantly, reveal with a short fade. Opacity only: the page is
	   already laid out underneath, so nothing moves. The motion tokens drop
	   to 0ms under reduced motion. */
	.page-reveal {
		opacity: 0;
	}
	.page-reveal[data-revealed='true'] {
		opacity: 1;
		transition: opacity var(--motion-fast) var(--ease);
	}
</style>
