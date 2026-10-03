<script lang="ts">
	import type { JobView } from '$lib/types/api.gen';
	import StatusBadge from './StatusBadge.svelte';
	import ProgressBar from './ProgressBar.svelte';
	import { statusAccentVar } from '$lib/utils/format';
	import { getVideoTypeConfig, isJobActive, discTypeLabel } from '$lib/utils/job-type';
	import { effectiveJobStatus, isPartialComplete } from '$lib/utils/job-status';
	import DiscTypeIcon from './DiscTypeIcon.svelte';
	import PosterImage from './PosterImage.svelte';
	import { jobPoster } from '$lib/utils/poster';
	import SkeletonCard from './SkeletonCard.svelte';
	import { formatEta } from '$lib/stores/rips.svelte';
	import { slide } from 'svelte/transition';

	interface Props {
		job?: JobView;
		progress?: number | null;
		progressStage?: string | null;
		tracksRipped?: number | null;
		tracksTotal?: number | null;
		eta?: number | null;
	}

	let { job, progress = null, progressStage = null, tracksRipped = null, tracksTotal = null, eta = null }: Props = $props();

	function formatStage(s: string): string {
		if (s === 'scratch-to-media') return 'Copying to shared storage';
		if (s === 'work-to-completed') return 'Moving to completed';
		return s;
	}

	// Use progress-polled counts when available (real-time), fall back to
	// the rip-progress summary surfaced on JobView.
	let displayRipped = $derived(tracksRipped ?? job?.rip_progress?.tracks_done ?? 0);
	let displayTotal = $derived(tracksTotal ?? job?.rip_progress?.tracks_total ?? 0);
	let expanded = $state(false);

	let typeConfig = $derived(getVideoTypeConfig(null, job?.disc_type ?? null));
	// Gate the progress row on the EFFECTIVE status so it shows while the job
	// is genuinely in-flight (ripping OR transcoding) and disappears once it is
	// terminal (complete/failed). A done job (raw `ripped` + transcode_progress
	// 'done') reads effective 'complete' → not active → no progress bar.
	let active = $derived(job ? isJobActive(effectiveJobStatus(job)) : false);
	let accentVar = $derived(statusAccentVar(job?.status));

	function toggle(e: MouseEvent) {
		// Don't toggle when clicking links/buttons inside
		if ((e.target as HTMLElement).closest('a, button:not(.row-toggle)')) return;
		expanded = !expanded;
	}

</script>

<style>
	/* card-status colours its accent stripe from data-status (job/drive/
	   transcode statuses); the original's left accent was the video-type hue
	   instead, a different axis, so this overrides the accent colour. */
	.job-active-row { border-left-color: var(--jt-accent); cursor: pointer; }
	.job-active-row-collapsed { cursor: pointer; padding: 0.625rem 1rem 0; }
	.job-active-row-collapsed[data-inactive="true"] { padding-bottom: 0.625rem; }
	/* :global: forwarded through PosterImage's class prop */
	:global(.job-active-row-poster) { height: 2.5rem; width: 1.75rem; flex-shrink: 0; border-radius: var(--radius-sm); object-fit: cover; }
	/* :global: forwarded through PosterImage's class prop */
	:global(.job-active-row-poster-square) { width: 2.5rem; }
	.job-active-row-title { font-size: 0.875rem; line-height: 1.25rem; font-weight: 600; color: var(--color-text); }
	.job-active-row-meta { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
	.job-active-row-type-pill { border-radius: var(--radius-sm); padding: 0.125rem 0.375rem; font-size: 0.75rem; line-height: 1rem; font-weight: 500; background: var(--jt-bg); color: var(--jt-text); }
	.job-active-row-disc-pill { border-radius: var(--radius-sm); padding: 0.125rem 0.375rem; font-size: 0.75rem; line-height: 1rem; background: var(--color-primary-tint-2); }
	.job-active-row-details {
		border-radius: var(--radius-md);
		border: 1px solid var(--color-border-strong);
		background: var(--color-primary-tint-3);
		padding: 0.375rem 1rem;
		font-size: 0.875rem; line-height: 1.25rem;
		font-weight: 500;
		color: var(--color-primary);
		transition: background-color var(--motion-fast) var(--ease);
	}
	.job-active-row-details:hover { background: color-mix(in srgb, var(--color-primary) 25%, transparent); }
	.job-active-row-chevron-btn { padding: 0.125rem; color: var(--color-text-faint); transition: color var(--motion-fast) var(--ease); }
	.job-active-row-chevron-btn:hover { color: var(--color-text-secondary); }
	.job-active-row-chevron { transition: transform var(--motion-fast) var(--ease); }
	.job-active-row-chevron-btn[aria-expanded="true"] .job-active-row-chevron { transform: rotate(180deg); }
	.job-active-row-progress { margin-top: 0.5rem; border-top: 1px solid var(--color-border); padding: 0.625rem 1rem 0.625rem 4rem; }
	.job-active-row-indeterminate-track { height: 0.625rem; flex: 1 1 0%; overflow: hidden; border-radius: 9999px; background: var(--color-primary-tint-3); }
	.job-active-row-indeterminate-fill { height: 100%; width: 33.3333%; border-radius: 9999px; background: var(--jt-progress-color); opacity: 0.6; animation: var(--animate-indeterminate); }
	.job-active-row-ellipsis { min-width: 3ch; text-align: right; }
	.job-active-row-expanded-title { font-size: 0.875rem; line-height: 1.25rem; font-weight: 600; color: var(--color-primary); }
	.job-active-row-expanded-title:hover { text-decoration: underline; }
	.job-active-row-expanded { border-top: 1px solid var(--color-border); padding: 0.75rem 1rem; }
	/* :global: forwarded through PosterImage's class prop */
	:global(.job-active-row-poster-lg) { height: 8rem; width: 5.5rem; flex-shrink: 0; border-radius: var(--radius-sm); object-fit: cover; }
	/* :global: forwarded through PosterImage's class prop */
	:global(.job-active-row-poster-lg-square) { width: 8rem; }
	.job-active-row-detail-table { font-size: 0.75rem; line-height: 1rem; }
	.job-active-row-detail-table tbody tr:not(:last-child) { border-bottom: 1px solid var(--color-border); }
	.job-active-row-detail-label { padding: 0.25rem 1rem 0.25rem 0; white-space: nowrap; color: var(--color-text-muted); }
	.job-active-row-detail-label-2 { padding-left: 1.5rem; }
	.job-active-row-detail-value { padding: 0.25rem 0; color: var(--color-text); }
</style>

{#if !job}
	<SkeletonCard lines={3} />
{:else}
<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
<div
	class="card card-status job-active-row"
	data-status={effectiveJobStatus(job)}
	style:--jt-accent={typeConfig.accent}
	onclick={toggle}
	role="button"
	tabindex="0"
>
	<!-- Collapsed row -->
	<div class="job-active-row-collapsed" data-inactive={!active}>
		<div class="flex items-center gap-3">
			<!-- Poster thumbnail -->
			<PosterImage url={jobPoster(job)} alt="" class="job-active-row-poster {job.disc_type === 'cd' ? 'job-active-row-poster-square' : ''}" />

			<!-- Title -->
			<h3 class="min-w-0 flex-shrink truncate job-active-row-title">
				{job.title || 'Untitled'}
			</h3>

			<!-- Year -->
			{#if job.year}
				<span class="shrink-0 job-active-row-meta">{job.year}</span>
			{/if}

			<!-- Status badge -->
			<div class="shrink-0 flex items-center gap-1.5">
				<StatusBadge status={effectiveJobStatus(job)} />
				{#if isPartialComplete(job)}
					<span class="badge badge-sm badge-warning"
						>Done {job.transcode_progress?.tasks_done}/{job.transcode_progress?.tasks_total}</span
					>
				{/if}
			</div>

			<!-- Type + disc badges -->
			<div class="hidden sm:flex shrink-0 items-center gap-1.5">
				<span class="job-active-row-type-pill" style:--jt-bg={typeConfig.badgeBg} style:--jt-text={typeConfig.badgeText}>{typeConfig.label}</span>
				{#if job.disc_type}
					<span class="inline-flex items-center gap-0.5 job-active-row-disc-pill">
						<DiscTypeIcon disctype={job.disc_type} size="h-3 w-3" />
						{discTypeLabel(job.disc_type)}
					</span>
				{/if}
			</div>

			<!-- Spacer -->
			<span class="flex-1"></span>

			<!-- Track counts -->
			{#if active && displayTotal > 0}
				<span class="shrink-0 job-active-row-meta">
					{displayRipped}/{displayTotal}
				</span>
			{/if}

			<!-- Details -->
			<a
				href="/jobs/{job.id}"
				class="shrink-0 job-active-row-details"
			>Details</a>

			<!-- Expand chevron -->
			<button class="row-toggle shrink-0 job-active-row-chevron-btn" aria-expanded={expanded} title={expanded ? 'Collapse' : 'Expand'}>
				<svg class="h-4 w-4 job-active-row-chevron" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
				</svg>
			</button>
		</div>
	</div>

	<!-- Progress row: own line below a divider, indented under content -->
	{#if active}
		<div class="job-active-row-progress">
			{#if progress != null}
				<!-- Render the bar even at 0%. The MakeMKV prelude (libredrive
				     init, key ingest) can sit at 0 for several seconds and
				     "ripping 0%" is more honest than an indeterminate spinner. -->
				<div class="flex items-center gap-2">
					<div class="flex-1"><ProgressBar value={progress} colorVar={accentVar} /></div>
					{#if eta != null}
						<span class="shrink-0 job-active-row-meta">{formatEta(eta)} left</span>
					{/if}
				</div>
			{:else}
				<div class="flex items-center gap-2">
					<!-- data-indeterminate: the progress vocabulary's state hook,
					     so themes reach this shimmer without scoped class names. -->
					<div data-indeterminate="true" class="job-active-row-indeterminate-track">
						<div
							class="job-active-row-indeterminate-fill"
							style:--jt-progress-color={accentVar}
						></div>
					</div>
					<span class="job-active-row-meta job-active-row-ellipsis">...</span>
				</div>
			{/if}
		</div>
	{/if}

	<!-- Expanded detail -->
	{#if expanded}
		<div transition:slide={{ duration: 200 }} class="job-active-row-expanded">
			<div class="flex gap-4">
				<!-- Poster (larger) -->
				<PosterImage url={jobPoster(job)} alt={job.title ?? 'Poster'} class="job-active-row-poster-lg {job.disc_type === 'cd' ? 'job-active-row-poster-lg-square' : ''}" />

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
								<td class="job-active-row-detail-value"><span class="job-active-row-type-pill" style:--jt-bg={typeConfig.badgeBg} style:--jt-text={typeConfig.badgeText}>{typeConfig.label}</span></td>
								<td class="job-active-row-detail-label job-active-row-detail-label-2">Disc</td>
								<td class="job-active-row-detail-value">
									{#if job.disc_type}
										<span class="inline-flex items-center gap-1"><DiscTypeIcon disctype={job.disc_type} size="h-3.5 w-3.5" />{discTypeLabel(job.disc_type)}</span>
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
									{#if displayTotal > 0}
										{displayRipped} / {displayTotal} ripped
									{:else}
										-
									{/if}
								</td>
							</tr>
							<tr>
								<td class="job-active-row-detail-label">Progress</td>
								<td class="job-active-row-detail-value" colspan="3">
									{#if active && progressStage}
										{formatStage(progressStage)}
									{:else}
										-
									{/if}
								</td>
							</tr>
						</tbody>
					</table>

				</div>
			</div>
		</div>
	{/if}
</div>
{/if}
