<script lang="ts">
	import { ripProgress } from '$lib/stores/rips.svelte';
	import { formatEta, formatTransfer } from '$lib/utils/format';
	import ProgressBar from '$lib/components/shared/ProgressBar.svelte';

	interface Props {
		jobId: string;
	}

	let { jobId }: Props = $props();

	let liveProgress = $derived(ripProgress.value[jobId] ?? null);
	let liveTransfer = $derived(formatTransfer(liveProgress));
</script>

<section class="job-detail-lifecycle-card stack job-detail-rip" data-testid="job-rip-progress">
	<div class="flex items-center justify-between gap-2">
		<h2 class="job-detail-section-title">
			{liveProgress?.phase === 'verifying' ? 'Verifying ripped files' : 'Ripping'}
		</h2>
		{#if liveProgress?.eta_seconds != null}
			<span class="job-detail-rip-meta">{formatEta(liveProgress.eta_seconds)} left</span>
		{/if}
	</div>
	{#if liveProgress}
		<div class="flex items-center gap-2">
			<div class="flex-1"><ProgressBar value={liveProgress.progress_pct} /></div>
		</div>
		{#if liveTransfer}
			<div class="job-detail-rip-meta mono">{liveTransfer}</div>
		{/if}
	{:else}
		<p class="job-detail-rip-meta">Waiting for the first progress report from the ripper.</p>
	{/if}
</section>

<style>
	.job-detail-rip-meta {
		font-size: 0.8125rem;
		color: var(--color-text-muted);
	}
	.job-detail-lifecycle-card {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		background: var(--color-surface);
		padding: 0.75rem 1rem;
		box-shadow: var(--shadow-1);
	}
	.job-detail-section-title {
		font-size: 1.125rem;
		line-height: 1.75rem;
		font-weight: 600;
		color: var(--color-text);
	}
</style>
