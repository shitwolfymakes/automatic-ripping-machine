<script lang="ts">
	import type { TranscodeStatsView } from '$lib/types/api.gen';
	import { taskCount } from '$lib/transcode/stats';

	interface Props {
		stats: TranscodeStatsView;
	}

	let { stats }: Props = $props();
</script>

<div class="grid grid-cols-2 gap-4 lg:grid-cols-5">
	<div class="stat transcoder-page-stat">
		<p class="stat-label">Queued</p>
		<p class="stat-value transcoder-page-stat-value">{taskCount(stats, 'queued')}</p>
	</div>
	<div class="stat transcoder-page-stat">
		<p class="stat-label">In Progress</p>
		<p class="stat-value transcoder-page-stat-value transcoder-page-stat-value-progress">
			{taskCount(stats, 'in_progress')}
		</p>
	</div>
	<div class="stat transcoder-page-stat">
		<p class="stat-label">Done</p>
		<p class="stat-value transcoder-page-stat-value transcoder-page-stat-value-success">
			{taskCount(stats, 'done')}
		</p>
	</div>
	<div class="stat transcoder-page-stat">
		<p class="stat-label">Failed</p>
		<p class="stat-value transcoder-page-stat-value transcoder-page-stat-value-danger">
			{taskCount(stats, 'failed')}
		</p>
	</div>
	<div class="stat transcoder-page-stat">
		<p class="stat-label">Total</p>
		<p class="stat-value transcoder-page-stat-value transcoder-page-stat-value-muted">{stats.total_tasks}</p>
	</div>
</div>

<style>
	/* the original stat cards were text-3xl (1.875rem/2.25rem), taller than
	   stat's own 1.5rem/2rem default (tuned for StatStrip) */
	.transcoder-page-stat-value {
		font-size: 1.875rem;
		line-height: 2.25rem;
	}
	/* the original "In Progress" value used a literal indigo hue with no
	   shared token; same transcoder-domain collapse as the worker card and
	   progress-bar tone above */
	.transcoder-page-stat-value-progress {
		color: var(--color-status-transcoding);
	}
	.transcoder-page-stat-value-success {
		color: var(--color-success);
	}
	.transcoder-page-stat-value-danger {
		color: var(--color-danger);
	}
	.transcoder-page-stat-value-muted {
		color: var(--color-text-muted);
	}
</style>
