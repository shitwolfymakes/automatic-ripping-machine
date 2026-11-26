<script lang="ts">
	// The active job row's expanded panel: the large poster, the title link and
	// the job's facts in a table.
	import type { JobView } from '$lib/types/api.gen';
	import StatusBadge from '../../shared/StatusBadge.svelte';
	import DiscTypeIcon from '../../shared/DiscTypeIcon.svelte';
	import PosterImage from '../../shared/PosterImage.svelte';
	import { jobPoster } from '$lib/match/poster';
	import { effectiveJobStatus } from '$lib/jobs/status';
	import { discTypeLabel, type VideoTypeConfig } from '$lib/jobs/type';
	import { formatRipStage } from '$lib/jobs/status-format';

	interface Props {
		/** The job the panel describes. */
		job: JobView;
		/** The type pill's label and colours. */
		typeConfig: VideoTypeConfig;
		/** Tracks ripped so far. */
		tracksRipped: number;
		/** Tracks the disc holds in total; 0 hides the count. */
		tracksTotal: number;
		/** Whether the job is in progress, which gates the Progress cell. */
		active: boolean;
		/** The ripper's current stage, if it reported one. */
		progressStage: string | null;
	}

	let { job, typeConfig, tracksRipped, tracksTotal, active, progressStage }: Props = $props();
</script>

<div class="flex gap-4">
	<!-- Poster (larger) -->
	<PosterImage
		url={jobPoster(job)}
		alt={job.title ?? 'Poster'}
		class="job-active-row-poster-lg {job.disc_type === 'cd' ? 'job-active-row-poster-lg-square' : ''}"
	/>

	<div class="min-w-0 flex-1">
		<!-- Title -->
		<div class="mb-2">
			<a href="/jobs/{job.id}" class="job-active-row-expanded-title">{job.title || 'Untitled'}</a>
		</div>

		<!-- Data table -->
		<table class="table job-active-row-detail-table">
			<tbody>
				<tr>
					<td class="job-active-row-detail-label">Job ID</td>
					<td class="job-active-row-detail-value">{job.id}</td>
					<td class="job-active-row-detail-label job-active-row-detail-label-2">Status</td>
					<td class="job-active-row-detail-value"><StatusBadge status={effectiveJobStatus(job)} /></td>
				</tr>
				<tr>
					<td class="job-active-row-detail-label">Type</td>
					<td class="job-active-row-detail-value"
						><span
							class="job-active-row-type-pill"
							style:--jt-bg={typeConfig.badgeBg}
							style:--jt-text={typeConfig.badgeText}>{typeConfig.label}</span
						></td
					>
					<td class="job-active-row-detail-label job-active-row-detail-label-2">Disc</td>
					<td class="job-active-row-detail-value">
						{#if job.disc_type}
							<span class="inline-flex items-center gap-1"
								><DiscTypeIcon disctype={job.disc_type} size="h-3.5 w-3.5" />{discTypeLabel(job.disc_type)}</span
							>
						{:else}
							-
						{/if}
					</td>
				</tr>
				<tr>
					<td class="job-active-row-detail-label">Year</td>
					<td class="job-active-row-detail-value">{job.year || '-'}</td>
					<td class="job-active-row-detail-label job-active-row-detail-label-2">Tracks</td>
					<td class="job-active-row-detail-value">
						{#if tracksTotal > 0}
							{tracksRipped} / {tracksTotal} ripped
						{:else}
							-
						{/if}
					</td>
				</tr>
				<tr>
					<td class="job-active-row-detail-label">Progress</td>
					<td class="job-active-row-detail-value" colspan="3">
						{#if active && progressStage}
							{formatRipStage(progressStage)}
						{:else}
							-
						{/if}
					</td>
				</tr>
			</tbody>
		</table>
	</div>
</div>

<style>
	.job-active-row-type-pill {
		border-radius: var(--radius-sm);
		padding: 0.125rem 0.375rem;
		font-size: 0.75rem;
		line-height: 1rem;
		font-weight: 500;
		background: var(--jt-bg);
		color: var(--jt-text);
	}
	.job-active-row-expanded-title {
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 600;
		color: var(--color-primary);
	}
	.job-active-row-expanded-title:hover {
		text-decoration: underline;
	}
	/* :global: forwarded through PosterImage's class prop */
	:global(.job-active-row-poster-lg) {
		height: 8rem;
		width: 5.5rem;
		flex-shrink: 0;
		border-radius: var(--radius-sm);
		object-fit: cover;
	}
	/* :global: forwarded through PosterImage's class prop */
	:global(.job-active-row-poster-lg-square) {
		width: 8rem;
	}
	.job-active-row-detail-table {
		font-size: 0.75rem;
		line-height: 1rem;
	}
	.job-active-row-detail-table tbody tr:not(:last-child) {
		border-bottom: 1px solid var(--color-border);
	}
	.job-active-row-detail-label {
		padding: 0.25rem 1rem 0.25rem 0;
		white-space: nowrap;
		color: var(--color-text-muted);
	}
	.job-active-row-detail-label-2 {
		padding-left: 1.5rem;
	}
	.job-active-row-detail-value {
		padding: 0.25rem 0;
		color: var(--color-text);
	}
</style>
