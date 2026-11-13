<script lang="ts">
	import type { JobView } from '$lib/types/api.gen';
	import StatusBadge from '$lib/components/StatusBadge.svelte';
	import PosterImage from '$lib/components/PosterImage.svelte';
	import { effectiveJobStatus } from '$lib/jobs/status';
	import { driveLabel } from '$lib/drives/name';
	import { jobPoster } from '$lib/match/poster';
	import { discKindLabel, discPosition, jobTypeConfig, shortJobId } from '$lib/logs/list';
	import { calendarTimeAgo, formatShortDateTime } from '$lib/utils/format';
	import { dashboard } from '$lib/stores/dashboard';

	interface Props {
		job: JobView;
		/** The log file's modified time, when the job has a log. */
		logAt: string | undefined;
	}

	let { job, logAt }: Props = $props();

	const type = $derived(jobTypeConfig(job));
	const drive = $derived(driveLabel(job.drive_id, $dashboard.drive_names));
</script>

<tr class="table-row">
	<td class="table-cell" data-label="Title">
		<div class="logs-panel-title-cell">
			<PosterImage
				url={jobPoster(job)}
				alt=""
				class="logs-panel-poster {job.disc_type === 'cd' ? 'logs-panel-poster-square' : ''}"
			/>
			<div class="min-w-0">
				<a href="/logs/{job.id}" class="logs-panel-title-link">{job.title || job.id}</a>
				<div class="logs-panel-id" title={job.id}>{shortJobId(job.id)}</div>
			</div>
		</div>
	</td>
	<td class="table-cell" data-label="Status">
		<StatusBadge status={effectiveJobStatus(job)} />
	</td>
	<td class="table-cell" data-label="Type">
		<span class="logs-panel-chips">
			<span class="logs-panel-chip" style:--jt-bg={type.badgeBg} style:--jt-text={type.badgeText}>{type.label}</span>
			<span class="logs-panel-chip logs-panel-chip-neutral">{discKindLabel(job, $dashboard.drive_source_kinds)}</span>
		</span>
	</td>
	<td class="table-cell logs-panel-nowrap" data-label="Disc">{discPosition(job)}</td>
	<td class="table-cell" data-label="Drive">
		{#if drive}
			<span class="logs-panel-drive" title={drive}>{drive}</span>
		{:else}
			-
		{/if}
	</td>
	<td class="table-cell logs-panel-nowrap" data-label="Last modified">
		{#if logAt}
			{@const relative = calendarTimeAgo(logAt)}
			{#if relative}
				<div>{relative}</div>
				<div class="logs-panel-muted logs-panel-small">{formatShortDateTime(logAt)}</div>
			{:else}
				<div>{formatShortDateTime(logAt)}</div>
			{/if}
		{:else}
			<span class="logs-panel-muted">No log yet</span>
		{/if}
	</td>
</tr>

<style>
	.logs-panel-muted {
		color: var(--color-text-muted);
	}
	.logs-panel-small {
		font-size: 0.75rem;
		line-height: 1rem;
	}
	.logs-panel-nowrap {
		white-space: nowrap;
	}
	.logs-panel-title-cell {
		display: flex;
		align-items: center;
		gap: 0.625rem;
	}
	/* :global: forwarded through PosterImage's class prop */
	:global(.logs-panel-poster) {
		height: 2.5rem;
		width: 1.75rem;
		flex-shrink: 0;
		border-radius: var(--radius-sm);
		object-fit: cover;
	}
	/* :global: forwarded through PosterImage's class prop; CD covers are square */
	:global(.logs-panel-poster-square) {
		width: 2.5rem;
	}
	.logs-panel-title-link {
		font-weight: 500;
		color: var(--color-primary-text);
	}
	.logs-panel-id {
		font-family: var(--font-mono);
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-muted);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.logs-panel-chips {
		display: inline-flex;
		flex-wrap: wrap;
		gap: 0.25rem;
	}
	/* the type pill matches JobRow's .job-row-type-pill */
	.logs-panel-chip {
		border-radius: var(--radius-sm);
		padding: 0.125rem 0.375rem;
		font-size: 0.75rem;
		line-height: 1rem;
		font-weight: 500;
		white-space: nowrap;
		background: var(--jt-bg);
		color: var(--jt-text);
	}
	.logs-panel-chip-neutral {
		background: none;
		border: 1px solid var(--color-border);
		color: var(--color-text-secondary);
	}
	.logs-panel-drive {
		display: inline-block;
		max-width: 12rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		vertical-align: bottom;
	}
</style>
