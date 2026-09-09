<script lang="ts">
	import Skeleton from './Skeleton.svelte';

	interface Props {
		class?: string;
		lines?: number;
	}
	let { class: cls = '', lines = 3 }: Props = $props();
</script>

<div
	class="panel {cls}"
	aria-busy="true"
	aria-live="polite"
>
	<div class="stack stack-sm skeleton-card-lines">
		<Skeleton variant="line" width="60%" height="1.25rem" />
		{#each { length: Math.max(0, lines - 1) } as _}
			<Skeleton variant="line" width="100%" height="0.875rem" />
		{/each}
	</div>
</div>

<style>
	/* .stack-sm is 0.5rem; the original space-y-3 wrapper here was 0.75rem. */
	.skeleton-card-lines {
		gap: 0.75rem;
	}
</style>
