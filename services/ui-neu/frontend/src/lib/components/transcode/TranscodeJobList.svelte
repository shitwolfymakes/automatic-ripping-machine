<script lang="ts">
	import LoadState from '$lib/components/shared/LoadState.svelte';
	import SkeletonCard from '$lib/components/shared/SkeletonCard.svelte';
	import TranscodeJobCard from '$lib/components/transcode/TranscodeJobCard.svelte';
	import type { TranscodeTaskView } from '$lib/types/api.gen';

	interface Props {
		jobs: TranscodeTaskView[];
		loading: boolean;
		error: Error | null;
		totalTasks: number;
		onretry: (id: string) => unknown;
		ondelete: (id: string) => unknown;
	}

	let { jobs, loading, error, totalTasks, onretry, ondelete }: Props = $props();
</script>

<LoadState data={jobs} {loading} {error} isEmpty={(d) => d.length === 0}>
	{#snippet loadingSlot()}
		<!-- As many placeholders as the stats poll says there are tasks (it
	     lands first), so the list does not grow when the jobs arrive. -->
		<div class="stack stack-sm">
			{#each Array(Math.min(totalTasks || 3, 6)) as _unused, i (i)}
				<SkeletonCard lines={4} class="pb-3" />
			{/each}
		</div>
	{/snippet}
	{#snippet empty()}
		<p class="transcoder-page-empty">No transcode tasks found.</p>
	{/snippet}
	{#snippet ready(jobList)}
		<div class="stack stack-sm">
			{#each jobList as job (job.id)}
				<TranscodeJobCard {job} {onretry} {ondelete} />
			{/each}
		</div>
	{/snippet}
</LoadState>

<style>
	.transcoder-page-empty {
		padding: 2rem 0;
		text-align: center;
		color: var(--color-text-faint);
	}
</style>
