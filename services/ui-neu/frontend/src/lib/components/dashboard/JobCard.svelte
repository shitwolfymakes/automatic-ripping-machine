<script lang="ts">
	import type { JobView } from '$lib/types/api.gen';
	import PosterImage from '../shared/PosterImage.svelte';
	import StatusBadge from '../shared/StatusBadge.svelte';
	import { jobPoster } from '$lib/match/poster';
	import { getVideoTypeConfig, discTypeLabel } from '$lib/jobs/type';
	import { effectiveJobStatus } from '$lib/jobs/status';
	import DiscTypeIcon from '../shared/DiscTypeIcon.svelte';
	import SkeletonCard from '../shared/SkeletonCard.svelte';
	import StageRail from '../jobs/StageRail.svelte';

	interface Props {
		job?: JobView;
	}

	let { job }: Props = $props();

	let typeConfig = $derived(getVideoTypeConfig(null, job?.disc_type ?? null));
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
			<PosterImage
				url={jobPoster(job)}
				alt={job.title ?? 'Poster'}
				class="job-card-poster {job.disc_type === 'cd' ? 'job-card-poster-square' : ''}"
			/>
			<div class="min-w-0 flex-1">
				<!-- Row 1: Title + Status -->
				<div class="flex items-start justify-between gap-2">
					<h3 class="truncate job-card-title">
						{job.title || 'Untitled'}
					</h3>
					<div class="flex shrink-0 items-center gap-1.5">
						<StatusBadge status={effectiveJobStatus(job)} />
					</div>
				</div>

				<!-- Row 2: Year -->
				<div class="mt-0.5 flex items-center gap-2 job-card-meta job-card-meta-lg">
					{#if job.year}
						<span>{job.year}</span>
					{/if}
				</div>

				<!-- Row 3: Type badge, disc type -->
				<div class="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 job-card-meta">
					<span class="job-card-type-pill" style:--jt-bg={typeConfig.badgeBg} style:--jt-text={typeConfig.badgeText}
						>{typeConfig.label}</span
					>
					{#if job.disc_type}
						<span class="inline-flex items-center gap-1 job-card-disc-pill">
							<DiscTypeIcon disctype={job.disc_type} size="h-3.5 w-3.5" decorative />
							{discTypeLabel(job.disc_type)}
						</span>
					{/if}
				</div>
			</div>
		</div>
		<div class="job-card-rail">
			<StageRail {job} />
		</div>
	</a>
{/if}

<style>
	/* card-status colours its left accent from data-status (job/drive/transcode
	   statuses in card.css); the JobCard accent is the video-type hue (movie/series/music/...), a
	   different axis, so this overrides the accent colour on top of card-status's own state
	   selectors. */
	.job-card {
		border-left-color: var(--jt-accent);
		padding: 1rem;
	}
	.job-card-body {
		display: flex;
		gap: 1rem;
	}
	/* :global: forwarded through PosterImage's class prop */
	:global(.job-card-poster) {
		height: 6rem;
		width: 4rem;
		border-radius: var(--radius-sm);
		object-fit: cover;
	}
	/* :global: forwarded through PosterImage's class prop */
	:global(.job-card-poster-square) {
		width: 6rem;
	}
	/* card-title is 0.875rem (a card HEADER size); this h3 sets no text size, so it inherits the
	   ambient 1rem body size */
	.job-card-title {
		font-weight: 600;
		color: var(--color-text);
	}
	.job-card-meta {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-muted);
	}
	/* the year row under the title is 0.875rem; the tag rows below it are 0.75rem. */
	.job-card-meta-lg {
		font-size: 0.875rem;
		line-height: calc(1.25 / 0.875);
	}
	.job-card-disc-pill {
		border-radius: var(--radius-sm);
		padding: 0.125rem 0.375rem;
		background: var(--color-primary-tint-2);
	}
	.job-card-type-pill {
		border-radius: var(--radius-sm);
		padding: 0.125rem 0.375rem;
		font-weight: 500;
		background: var(--jt-bg);
		color: var(--jt-text);
	}
	.job-card-rail {
		margin-top: 0.875rem;
		border-top: 1px solid var(--color-border);
		padding-top: 0.75rem;
	}
</style>
