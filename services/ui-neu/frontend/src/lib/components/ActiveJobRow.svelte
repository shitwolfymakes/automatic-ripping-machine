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

{#if !job}
	<SkeletonCard lines={3} />
{:else}
<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
<div
	class="rounded-lg border border-primary/20 border-l-4 {typeConfig.accentBorder} bg-surface shadow-xs transition dark:border-primary/20 dark:bg-surface-dark"
	onclick={toggle}
	role="button"
	tabindex="0"
>
	<!-- Collapsed row -->
	<div class="cursor-pointer px-4 pt-2.5" class:pb-2.5={!active}>
		<div class="flex items-center gap-3">
			<!-- Poster thumbnail -->
			<PosterImage url={jobPoster(job)} alt="" class="h-10 {job.disc_type === 'cd' ? 'w-10' : 'w-7'} shrink-0 rounded-sm object-cover" />

			<!-- Title -->
			<h3 class="min-w-0 flex-shrink truncate font-semibold text-sm text-gray-900 dark:text-white">
				{job.title || 'Untitled'}
			</h3>

			<!-- Year -->
			{#if job.year}
				<span class="shrink-0 text-xs text-gray-500 dark:text-gray-400">{job.year}</span>
			{/if}

			<!-- Status badge -->
			<div class="shrink-0 flex items-center gap-1.5">
				<StatusBadge status={effectiveJobStatus(job)} />
				{#if isPartialComplete(job)}
					<span class="rounded-sm bg-amber-100 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400"
						>Done {job.transcode_progress?.tasks_done}/{job.transcode_progress?.tasks_total}</span
					>
				{/if}
			</div>

			<!-- Type + disc badges -->
			<div class="hidden sm:flex shrink-0 items-center gap-1.5">
				<span class="rounded-sm px-1.5 py-0.5 text-xs font-medium {typeConfig.badgeClasses}">{typeConfig.label}</span>
				{#if job.disc_type}
					<span class="inline-flex items-center gap-0.5 rounded-sm bg-primary/10 px-1.5 py-0.5 text-xs dark:bg-primary/15">
						<DiscTypeIcon disctype={job.disc_type} size="h-3 w-3" />
						{discTypeLabel(job.disc_type)}
					</span>
				{/if}
			</div>

			<!-- Spacer -->
			<span class="flex-1"></span>

			<!-- Track counts -->
			{#if active && displayTotal > 0}
				<span class="shrink-0 text-xs text-gray-500 dark:text-gray-400">
					{displayRipped}/{displayTotal}
				</span>
			{/if}

			<!-- Details -->
			<a
				href="/jobs/{job.id}"
				class="shrink-0 rounded-md border border-primary/30 bg-primary/15 px-4 py-1.5 text-sm font-medium text-primary hover:bg-primary/25"
			>Details</a>

			<!-- Expand chevron -->
			<button class="row-toggle shrink-0 p-0.5 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 transition-transform" class:rotate-180={expanded} title={expanded ? 'Collapse' : 'Expand'}>
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
				</svg>
			</button>
		</div>
	</div>

	<!-- Progress row: own line below a divider, indented under content -->
	{#if active}
		<div class="mt-2 border-t border-primary/10 dark:border-primary/15 px-4 pl-[64px] pr-4 py-2.5">
			{#if progress != null}
				<!-- Render the bar even at 0%. The MakeMKV prelude (libredrive
				     init, key ingest) can sit at 0 for several seconds and
				     "ripping 0%" is more honest than an indeterminate spinner. -->
				<div class="flex items-center gap-2">
					<div class="flex-1"><ProgressBar value={progress} colorVar={accentVar} /></div>
					{#if eta != null}
						<span class="shrink-0 text-xs text-gray-500 dark:text-gray-400">{formatEta(eta)} left</span>
					{/if}
				</div>
			{:else}
				<div class="flex items-center gap-2">
					<div class="h-2.5 flex-1 overflow-hidden rounded-full bg-primary/15">
						<div
							class="h-full w-1/3 animate-indeterminate rounded-full"
							style="background: {accentVar}; opacity: 0.6"
						></div>
					</div>
					<span class="min-w-[3ch] text-right text-xs text-gray-500 dark:text-gray-400">...</span>
				</div>
			{/if}
		</div>
	{/if}

	<!-- Expanded detail -->
	{#if expanded}
		<div transition:slide={{ duration: 200 }} class="border-t border-primary/10 px-4 py-3 dark:border-primary/15">
			<div class="flex gap-4">
				<!-- Poster (larger) -->
				<PosterImage url={jobPoster(job)} alt={job.title ?? 'Poster'} class="h-32 {job.disc_type === 'cd' ? 'w-32' : 'w-22'} shrink-0 rounded-sm object-cover" />

				<div class="min-w-0 flex-1">
					<!-- Title -->
					<div class="mb-2">
						<a href="/jobs/{job.id}" class="text-sm font-semibold text-primary hover:underline">{job.title || 'Untitled'}</a>
					</div>

					<!-- Data table -->
					<table class="w-full text-xs">
						<tbody class="divide-y divide-primary/5 dark:divide-primary/10">
							<tr>
								<td class="py-1 pr-4 text-gray-500 dark:text-gray-400 whitespace-nowrap">Job ID</td>
								<td class="py-1 text-gray-900 dark:text-white">{job.id}</td>
								<td class="py-1 pr-4 text-gray-500 dark:text-gray-400 whitespace-nowrap pl-6">Status</td>
								<td class="py-1"><StatusBadge status={effectiveJobStatus(job)} /></td>
							</tr>
							<tr>
								<td class="py-1 pr-4 text-gray-500 dark:text-gray-400 whitespace-nowrap">Type</td>
								<td class="py-1"><span class="rounded-sm px-1 py-0.5 font-medium {typeConfig.badgeClasses}">{typeConfig.label}</span></td>
								<td class="py-1 pr-4 text-gray-500 dark:text-gray-400 whitespace-nowrap pl-6">Disc</td>
								<td class="py-1 text-gray-900 dark:text-white">
									{#if job.disc_type}
										<span class="inline-flex items-center gap-1"><DiscTypeIcon disctype={job.disc_type} size="h-3.5 w-3.5" />{discTypeLabel(job.disc_type)}</span>
									{:else}
										-
									{/if}
								</td>
							</tr>
							<tr>
								<td class="py-1 pr-4 text-gray-500 dark:text-gray-400 whitespace-nowrap">Year</td>
								<td class="py-1 text-gray-900 dark:text-white">{job.year || '-'}</td>
								<td class="py-1 pr-4 text-gray-500 dark:text-gray-400 whitespace-nowrap pl-6">Tracks</td>
								<td class="py-1 text-gray-900 dark:text-white">
									{#if displayTotal > 0}
										{displayRipped} / {displayTotal} ripped
									{:else}
										-
									{/if}
								</td>
							</tr>
							<tr>
								<td class="py-1 pr-4 text-gray-500 dark:text-gray-400 whitespace-nowrap">Progress</td>
								<td class="py-1 text-gray-900 dark:text-white" colspan="3">
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
