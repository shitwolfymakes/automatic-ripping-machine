<script lang="ts">
	import PageReveal from '../PageReveal.svelte';
	import LoadState from '$lib/components/shared/LoadState.svelte';

	// A PageReveal around one LoadState whose data the test drives (null = still loading).
	let { data }: { data: string | null } = $props();
</script>

<PageReveal>
	<LoadState {data} loading={data === null}>
		{#snippet loadingSlot()}<span>LOADING</span>{/snippet}
		{#snippet ready()}<span>READY</span>{/snippet}
	</LoadState>
</PageReveal>
