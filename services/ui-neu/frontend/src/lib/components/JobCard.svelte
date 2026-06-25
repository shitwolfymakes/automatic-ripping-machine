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
	let active = $derived(isJobActive(job?.status ?? null));
</script>

{#if !job}
	<SkeletonCard />
{:else}
<a
	href="/jobs/{job.id}"
	class="block rounded-lg border border-primary/20 border-l-4 {typeConfig.accentBorder} bg-surface p-4 shadow-xs transition hover:shadow-md dark:border-primary/20 dark:bg-surface-dark"
>
	<div class="flex gap-4">
		<PosterImage url={jobPoster(job)} alt={job.title ?? 'Poster'} class="h-24 {job.disc_type === 'cd' ? 'w-24' : 'w-16'} rounded-sm object-cover" />
		<div class="min-w-0 flex-1">
			<!-- Row 1: Title + Status -->
			<div class="flex items-start justify-between gap-2">
				<h3 class="truncate font-semibold text-gray-900 dark:text-white">
					{job.title || 'Untitled'}
				</h3>
				<StatusBadge status={effectiveJobStatus(job)} />
				{#if isPartialComplete(job)}
					<span class="rounded-sm bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
						>Done {job.transcode_progress?.tasks_done}/{job.transcode_progress?.tasks_total}</span
					>
				{/if}
			</div>

			<!-- Row 2: Year -->
			<div class="mt-0.5 flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
				{#if job.year}
					<span>{job.year}</span>
				{/if}
			</div>

			<!-- Row 3: Active → lifecycle/track counts -->
			<div class="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
				{#if active}
					<JobLifecycle status={job.status} sourceType={null} size="sm" />
					{#if job.rip_progress && job.rip_progress.tracks_total > 0}
						<span>{job.rip_progress.tracks_done} / {job.rip_progress.tracks_total} titles</span>
					{/if}
				{/if}
			</div>

			<!-- Row 4: Type badge, disc type -->
			<div class="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
				<span class="rounded-sm px-1.5 py-0.5 font-medium {typeConfig.badgeClasses}">{typeConfig.label}</span>
				{#if job.disc_type}
					<span class="inline-flex items-center gap-1 rounded-sm bg-primary/10 px-1.5 py-0.5 dark:bg-primary/15">
						<DiscTypeIcon disctype={job.disc_type} size="h-3.5 w-3.5" />
						{discTypeLabel(job.disc_type)}
					</span>
				{/if}
			</div>
		</div>
	</div>
	{#if active}
		<div class="mt-3">
			{#if progress != null && progress > 0}
				<ProgressBar value={progress} color="bg-primary" />
				{#if progressStage}
					<p class="mt-0.5 text-xs text-gray-400 dark:text-gray-500">{progressStage}</p>
				{/if}
			{:else}
				<div class="h-2.5 overflow-hidden rounded-full bg-primary/15 dark:bg-primary/15">
					<div class="h-full w-1/3 animate-indeterminate rounded-full bg-primary/60"></div>
				</div>
			{/if}
		</div>
	{/if}
</a>
{/if}
