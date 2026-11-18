<script lang="ts" generics="T">
	import { untrack, type Snippet } from 'svelte';
	import { fade } from 'svelte/transition';
	import { fadeIn } from '$lib/ui/transitions';
	import { isPending, loadPhase } from '$lib/utils/load-state';
	import { SKELETON_DELAY_MS, SKELETON_MIN_SHOW_MS, SkeletonGate } from '$lib/stores/skeleton-gate.svelte';
	import { trackPending } from '$lib/stores/page-reveal.svelte';

	interface Props {
		data: T | null | undefined;
		loading: boolean;
		error?: Error | null;
		isEmpty?: (data: T) => boolean;
		minDelay?: number;
		loadingSlot: Snippet;
		ready: Snippet<[T]>;
		empty?: Snippet;
		errorSlot?: Snippet<[Error]>;
	}

	let {
		data,
		loading,
		error = null,
		isEmpty,
		minDelay = SKELETON_DELAY_MS,
		loadingSlot,
		ready,
		empty,
		errorSlot
	}: Props = $props();

	// A load faster than minDelay never shows the skeleton; one that does show
	// it keeps it for at least SKELETON_MIN_SHOW_MS so it cannot flash. A
	// caller that opts out with minDelay=0 (an in-place browser such as the ISO
	// picker) wants the swap immediate both ways, so it gets no hold either.
	const delay = untrack(() => minDelay);
	const gate = new SkeletonGate(delay, delay === 0 ? 0 : SKELETON_MIN_SHOW_MS);
	$effect(() => {
		const pending = isPending({ data, loading, error });
		untrack(() => gate.update(pending));
	});
	$effect(() => () => gate.dispose());
	// Hold the page reveal until this panel has something to show.
	trackPending(() => isPending({ data, loading, error }));

	const phase = $derived(loadPhase({ data, loading, error, skeletonShown: gate.shown, isEmpty }));
</script>

{#if phase === 'error'}
	<div in:fade|local={fadeIn}>
		{#if errorSlot}
			{@render errorSlot(error!)}
		{:else}
			<p class="load-state-error">Failed to load: {error!.message}</p>
		{/if}
	</div>
{:else if phase === 'waiting'}
	<!-- Anti-flicker window: the skeleton is already in flow (space reserved)
         but invisible, so a fast load fades content in without a jump and a
         slow one reveals the skeleton without one either. -->
	<div data-phase="waiting" aria-hidden="true">
		{@render loadingSlot()}
	</div>
{:else if phase === 'loading'}
	<div in:fade|local={fadeIn}>
		{@render loadingSlot()}
	</div>
{:else if phase === 'empty'}
	<div in:fade|local={fadeIn}>
		{#if empty}
			{@render empty()}
		{:else}
			{@render loadingSlot()}
		{/if}
	</div>
{:else}
	<div in:fade|local={fadeIn}>
		{@render ready(data!)}
	</div>
{/if}

<style>
	.load-state-error {
		color: var(--color-danger);
	}
	/* The waiting phase renders the loading slot in flow (so its layout
       space is reserved) but hidden - see the anti-flicker comment above. */
	[data-phase='waiting'] {
		visibility: hidden;
	}
</style>
