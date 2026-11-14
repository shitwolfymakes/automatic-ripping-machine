<script lang="ts" generics="T">
	import type { Snippet } from 'svelte';
	import { fade } from 'svelte/transition';
	import { fadeIn } from '$lib/transitions';
	import { loadPhase } from '$lib/utils/load-state';

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

	let { data, loading, error = null, isEmpty, minDelay = 150, loadingSlot, ready, empty, errorSlot }: Props = $props();

	let delayElapsed = $state(false);
	let timer: ReturnType<typeof setTimeout> | null = null;

	$effect(() => {
		if (loading) {
			if (minDelay === 0) {
				delayElapsed = true;
			} else {
				timer = setTimeout(() => {
					delayElapsed = true;
				}, minDelay);
			}
		} else {
			if (timer) clearTimeout(timer);
			timer = null;
			delayElapsed = false;
		}
		return () => {
			if (timer) clearTimeout(timer);
		};
	});

	const phase = $derived(loadPhase({ data, loading, error, delayElapsed, isEmpty }));
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
