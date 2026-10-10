<script lang="ts">
	import type { JobView } from '$lib/types/api.gen';
	import PosterImage from './PosterImage.svelte';
	import StatusBadge from './StatusBadge.svelte';
	import ProgressBar from './ProgressBar.svelte';
	import { jobPoster } from '$lib/utils/poster';
	import { getVideoTypeConfig, isJobActive, discTypeLabel } from '$lib/utils/job-type';
	import { effectiveJobStatus, isPartialComplete } from '$lib/utils/job-status';
	import DiscTypeIcon from './DiscTypeIcon.svelte';
	import SkeletonCard from './SkeletonCard.svelte';
	import JobLifecycle from './JobLifecycle.svelte';

	interface Props {
		job?: JobView;
		progress?: number | null;
		progressStage?: string | null;
	}

	let { job, progress = null, progressStage = null }: Props = $props();

	let typeConfig = $derived(getVideoTypeConfig(null, job?.disc_type ?? null));
	// Use the EFFECTIVE status so the stepper shows while a job is genuinely
	// in-flight (ripping OR transcoding) and hides once it is terminal. A
	// transcoding job (raw `ripped` + transcode_progress.state 'transcoding')
	// reads effective 'transcoding' (active); a finished one reads 'complete'
	// (not active) so a done job shows no in-progress stepper.
	let active = $derived(job ? isJobActive(effectiveJobStatus(job)) : false);
</script>

{#if !job}
	<SkeletonCard />
{:else}
<a
	href="/jobs/{job.id}"
	class="card card-status job-card"
	data-status={effectiveJobStatus(job)}
	style:--jt-accent={typeConfig.accent}
>
	<div class="job-card-body">
		<PosterImage url={jobPoster(job)} alt={job.title ?? 'Poster'} class="job-card-poster {job.disc_type === 'cd' ? 'job-card-poster-square' : ''}" />
		<div class="min-w-0 flex-1">
			<!-- Row 1: Title + Status -->
			<div class="flex items-start justify-between gap-2">
				<h3 class="truncate job-card-title">
					{job.title || 'Untitled'}
				</h3>
				<div class="flex shrink-0 items-center gap-1.5">
					<StatusBadge status={effectiveJobStatus(job)} />
					{#if isPartialComplete(job)}
						<span class="badge badge-sm badge-warning"
							>Done {job.transcode_progress?.tasks_done}/{job.transcode_progress?.tasks_total}</span
						>
					{/if}
				</div>
			</div>

			<!-- Row 2: Year -->
			<div class="mt-0.5 flex items-center gap-2 job-card-meta job-card-meta-lg">
				{#if job.year}
					<span>{job.year}</span>
				{/if}
			</div>

			<!-- Row 3: Active → lifecycle/track counts -->
			<div class="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 job-card-meta">
				{#if active}
					<JobLifecycle status={effectiveJobStatus(job)} sourceType={null} size="sm" partial={isPartialComplete(job)} />
					{#if job.rip_progress && job.rip_progress.tracks_total > 0}
						<span>{job.rip_progress.tracks_done} / {job.rip_progress.tracks_total} titles</span>
					{/if}
				{/if}
			</div>

			<!-- Row 4: Type badge, disc type -->
			<div class="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 job-card-meta">
				<span class="job-card-type-pill" style:--jt-bg={typeConfig.badgeBg} style:--jt-text={typeConfig.badgeText}>{typeConfig.label}</span>
				{#if job.disc_type}
					<span class="inline-flex items-center gap-1 job-card-disc-pill">
						<DiscTypeIcon disctype={job.disc_type} size="h-3.5 w-3.5" />
						{discTypeLabel(job.disc_type)}
					</span>
				{/if}
			</div>
		</div>
	</div>
	{#if active}
		<div class="mt-3 job-card-progress">
			{#if progress != null && progress > 0}
				<ProgressBar value={progress} />
				{#if progressStage}
					<p class="mt-0.5 job-card-progress-stage">{progressStage}</p>
				{/if}
			{:else}
				<!-- data-indeterminate is the progress vocabulary's state hook;
				     carried here so themes can reach this shimmer the way they
				     reach ProgressBar's, without naming scoped classes. -->
				<div data-indeterminate="true" class="job-card-progress-indeterminate-track">
					<div class="job-card-progress-indeterminate-fill"></div>
				</div>
			{/if}
		</div>
	{/if}
</a>
{/if}

<style>
	/* card-status colours its left accent from data-status (job/drive/transcode
	   statuses in card.css); the ORIGINAL JobCard accent was the video-type hue
	   (movie/series/music/...), a different axis, so this overrides the accent
	   colour on top of card-status's own state selectors. */
	.job-card { border-left-color: var(--jt-accent); padding: 1rem; }
	.job-card-body { display: flex; gap: 1rem; }
	/* :global: forwarded through PosterImage's class prop */
	:global(.job-card-poster) { height: 6rem; width: 4rem; border-radius: var(--radius-sm); object-fit: cover; }
	/* :global: forwarded through PosterImage's class prop */
	:global(.job-card-poster-square) { width: 6rem; }
	/* card-title is 0.875rem (a card HEADER size); the original h3 here had no
	   text-size utility, so it inherited the ambient 1rem body size */
	.job-card-title { font-weight: 600; color: var(--color-text); }
	.job-card-meta { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
	/* the year row under the title was text-sm in the original; the tag rows
	   below it were text-xs. One class had silently served both sizes. */
	.job-card-meta-lg { font-size: 0.875rem; line-height: calc(1.25 / 0.875); }
	.job-card-progress-stage { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-faint); }
	.job-card-disc-pill { border-radius: var(--radius-sm); padding: 0.125rem 0.375rem; background: var(--color-primary-tint-2); }
	.job-card-type-pill { border-radius: var(--radius-sm); padding: 0.125rem 0.375rem; font-weight: 500; background: var(--jt-bg); color: var(--jt-text); }
	.job-card-progress-indeterminate-track { height: 0.625rem; overflow: hidden; border-radius: 9999px; background: var(--color-primary-tint-3); }
	.job-card-progress-indeterminate-fill { height: 100%; width: 33.3333%; border-radius: 9999px; background: color-mix(in srgb, var(--color-primary) 60%, transparent); animation: var(--animate-indeterminate); }
</style>
