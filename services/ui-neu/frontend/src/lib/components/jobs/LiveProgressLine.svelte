<script lang="ts">
	import type { LiveSample } from '$lib/live/feeds';
	import { formatDuration, formatTransfer } from '$lib/utils/format';
	import ProgressBar from '$lib/components/shared/ProgressBar.svelte';

	interface Props {
		sample: LiveSample | null;
		colorVar?: string | null;
		waitingText?: string;
	}

	let { sample, colorVar = null, waitingText = 'Waiting for the first progress report' }: Props = $props();

	let transfer = $derived(
		sample
			? formatTransfer({ bytes_done: sample.bytesDone, bytes_total: sample.bytesTotal, rate_bps: sample.rateBps })
			: null
	);
</script>

{#if sample && sample.pct !== null}
	<div class="stack-tight" data-testid="live-progress-line">
		<div class="flex items-center gap-2">
			<div class="flex-1"><ProgressBar value={sample.pct} {colorVar} /></div>
			{#if sample.etaSeconds !== null}
				<span class="live-progress-meta shrink-0">{formatDuration(sample.etaSeconds, { coarse: true })} left</span>
			{/if}
		</div>
		{#if transfer}
			<div class="live-progress-meta mono">{transfer}</div>
		{/if}
	</div>
{:else}
	<p class="live-progress-meta">{waitingText}</p>
{/if}

<style>
	.live-progress-meta {
		font-size: 0.8125rem;
		color: var(--color-text-muted);
	}
</style>
