<script lang="ts">
	import type { GpuView, TranscodeStatsView, TranscodeWorkerView } from '$lib/types/api.gen';
	import GpuInventoryRow from '$lib/components/shared/GpuInventoryRow.svelte';
	import { formatElapsed } from '$lib/utils/format';
	import { taskCount } from '$lib/transcode/stats';

	interface Props {
		workers: TranscodeWorkerView[];
		stats: TranscodeStatsView;
		gpus: GpuView[];
	}

	let { workers, stats, gpus }: Props = $props();
</script>

<div class="panel">
	<div class="mb-3 flex items-center justify-between">
		<div class="flex items-center gap-2">
			<div class="transcoder-page-worker-dot" data-active={workers.length > 0}></div>
			<span class="transcoder-page-worker-title">
				Workers {workers.length}/{stats.max_parallel} active
			</span>
		</div>
		<span class="transcoder-page-worker-summary">
			GPUs: {stats.gpus_available}/{stats.gpus_total} available &middot; Queue: {taskCount(stats, 'queued')} queued
		</span>
	</div>
	{#if gpus.length > 0}
		<!-- Per-device inventory rows: live status per GPU,
				     with the management card one link away in Settings. -->
		<div class="stack stack-sm transcoder-page-gpu-rows" data-testid="gpu-rows">
			{#each gpus as g (g.id)}
				<GpuInventoryRow gpu={g} />
			{/each}
			<a href="/settings#transcoding" class="transcoder-page-gpu-manage">Manage GPUs in Settings</a>
		</div>
	{/if}
	{#if workers.length > 0}
		<div class="grid gap-2 {stats.max_parallel > 1 ? 'sm:grid-cols-2 lg:grid-cols-3' : ''}">
			{#each workers as worker (worker.task_id)}
				<div class="flex items-center gap-3 transcoder-page-worker-card">
					<div class="transcoder-page-worker-pulse"></div>
					<div class="min-w-0 flex-1">
						<p class="truncate transcoder-page-worker-task" title={worker.output_path ?? worker.source_track_id}>
							Task #{worker.task_id}
							{#if worker.claimed_by}
								<span class="transcoder-page-worker-claimed"> &mdash; {worker.claimed_by}</span>
							{/if}
						</p>
						{#if worker.claim_heartbeat_at}
							{@const dur = formatElapsed(worker.claim_heartbeat_at)}
							<p class="transcoder-page-worker-heartbeat">
								{worker.progress_pct}%{#if dur}
									&middot; {dur} since heartbeat{/if}
							</p>
						{:else}
							<p class="transcoder-page-worker-heartbeat-idle">{worker.progress_pct}%</p>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.transcoder-page-worker-dot {
		height: 0.625rem;
		width: 0.625rem;
		border-radius: 9999px;
		background: var(--color-warning);
	}
	.transcoder-page-worker-dot[data-active='true'] {
		background: var(--color-success);
	}
	.transcoder-page-worker-title {
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 600;
		color: var(--color-text-secondary);
	}
	.transcoder-page-worker-summary {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-faint);
	}
	/* the worker card has no shared token for its indigo hue (border-indigo-200, bg-indigo-50/50); it
	   uses --color-status-transcoding (violet), the same tone the transcoder
	   domain's progress bar uses */
	.transcoder-page-worker-card {
		border: 1px solid color-mix(in srgb, var(--color-status-transcoding) 30%, transparent);
		border-radius: var(--radius-md);
		background: color-mix(in srgb, var(--color-status-transcoding) 8%, transparent);
		padding: 0.5rem 0.75rem;
	}
	.transcoder-page-worker-pulse {
		height: 0.5rem;
		width: 0.5rem;
		flex-shrink: 0;
		border-radius: 9999px;
		background: var(--color-status-transcoding);
		animation: skeleton-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite;
	}
	.transcoder-page-worker-task {
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 500;
		color: var(--color-text-secondary);
	}
	.transcoder-page-worker-claimed {
		font-weight: 400;
		color: var(--color-text-muted);
	}
	.transcoder-page-worker-heartbeat {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-status-transcoding);
	}
	.transcoder-page-worker-heartbeat-idle {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-faint);
	}

	.transcoder-page-gpu-rows {
		margin-bottom: 0.75rem;
	}
	.transcoder-page-gpu-manage {
		font-size: 0.8125rem;
		color: var(--color-primary);
		text-decoration: none;
	}
	.transcoder-page-gpu-manage:hover {
		text-decoration: underline;
	}
</style>
