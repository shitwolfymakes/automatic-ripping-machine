<script lang="ts">
	import { errorMessage } from '$lib/utils/errors';
	import type { JobView } from '$lib/types/api.gen';
	import StatusBadge from '../shared/StatusBadge.svelte';
	import LiveProgressLine from '../jobs/LiveProgressLine.svelte';
	import ActiveJobRowDetails from './active-job-row/ActiveJobRowDetails.svelte';
	import { statusAccentVar } from '$lib/jobs/status-format';
	import { getVideoTypeConfig, discTypeLabel } from '$lib/jobs/type';
	import { effectiveJobStatus } from '$lib/jobs/status';
	import { isInProgress } from '$lib/jobs/status-groups';
	import DiscTypeIcon from '../shared/DiscTypeIcon.svelte';
	import PosterImage from '../shared/PosterImage.svelte';
	import { jobPoster } from '$lib/match/poster';
	import SkeletonCard from '../shared/SkeletonCard.svelte';
	import IsoSourceChip from '../drives/IsoSourceChip.svelte';
	import { jobLive } from '$lib/stores/job-live.svelte';
	import { progressSample, ripStageWords } from '$lib/jobs/progress';
	import { slide } from 'svelte/transition';
	import { isAdmin } from '$lib/stores/auth';
	import { cancelIsoRip } from '$lib/api/iso';
	import { addToast } from '$lib/stores/toast.svelte';

	interface Props {
		job?: JobView;
		/** ISO file name for this job's (virtual) drive, when it's an ISO rip. */
		isoSource?: string | null;
		/** Whether that virtual drive rips an .iso file or a disc folder. */
		isoKind?: 'iso' | 'folder';
	}

	let { job, isoSource = null, isoKind = 'iso' }: Props = $props();

	// Re-watch exactly when the id or status changes, not on other field updates.
	let watchId = $derived(job?.id);
	let watchStatus = $derived(job?.status);
	$effect(() => {
		const id = watchId;
		const status = watchStatus;
		if (id === undefined || status === undefined) return;
		return jobLive.watch({ id, status });
	});

	let cancelling = $state(false);

	async function handleCancelIso() {
		if (!job?.drive_id) return;
		cancelling = true;
		try {
			await cancelIsoRip(job.drive_id);
		} catch (e) {
			// The card stays; tell the operator why (e.g. 409 once the rip ended).
			addToast({ tone: 'error', title: 'Cancel failed', body: errorMessage(e, 'Unknown error') });
		} finally {
			cancelling = false;
		}
	}

	let expanded = $state(false);

	let typeConfig = $derived(getVideoTypeConfig(null, job?.disc_type ?? null));
	// Gate the progress row on isInProgress: isLive minus the idle post-rip
	// statuses (ripped, ripped_partial, ripped_awaiting_identify). A job
	// waiting on the operator shows no progress bar, a transcoding job
	// (effective 'transcoding') does, and a terminal one (complete/failed)
	// does not.
	let active = $derived(job ? isInProgress(job) : false);
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
	{@const live = jobLive.get(job.id)}
	{@const ripped = job.rip_progress?.tracks_done ?? 0}
	{@const total = job.rip_progress?.tracks_total ?? 0}
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<div
		class="card card-status job-active-row"
		data-status={effectiveJobStatus(job)}
		data-source={isoSource ? 'iso' : undefined}
		style:--jt-accent={typeConfig.accent}
		onclick={toggle}
		role="button"
		tabindex="0"
	>
		<!-- Collapsed row -->
		<div class="job-active-row-collapsed" data-inactive={!active}>
			<div class="flex items-center gap-3">
				<!-- Poster thumbnail -->
				<PosterImage
					url={jobPoster(job)}
					alt=""
					class="job-active-row-poster {job.disc_type === 'cd' ? 'job-active-row-poster-square' : ''}"
				/>

				<!-- Title -->
				<h3 class="min-w-0 flex-shrink truncate job-active-row-title">
					{job.title || 'Untitled'}
				</h3>

				<!-- Year -->
				{#if job.year}
					<span class="shrink-0 job-active-row-meta">{job.year}</span>
				{/if}

				<!-- ISO source chip (replaces the absent drive pill for a virtual drive) -->
				{#if isoSource}
					<span class="shrink-0">
						<IsoSourceChip name={isoSource} kind={isoKind} />
					</span>
				{/if}

				<!-- Status badge -->
				<div class="shrink-0 flex items-center gap-1.5">
					<StatusBadge status={effectiveJobStatus(job)} />
				</div>

				<!-- Type + disc badges -->
				<div class="hidden sm:flex shrink-0 items-center gap-1.5">
					<span
						class="job-active-row-type-pill"
						style:--jt-bg={typeConfig.badgeBg}
						style:--jt-text={typeConfig.badgeText}>{typeConfig.label}</span
					>
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
				{#if active && total > 0}
					<span class="shrink-0 job-active-row-meta">
						{ripped}/{total}
					</span>
				{/if}

				<!-- Details -->
				<a href="/jobs/{job.id}" class="shrink-0 job-active-row-details">Details</a>

				<!-- ISO rip: admin-only Cancel (removes the virtual drive too) -->
				{#if isoSource && $isAdmin}
					<button
						onclick={handleCancelIso}
						disabled={cancelling}
						class="btn btn-danger btn-sm shrink-0"
						title="Cancel the rip and remove the virtual drive"
					>
						{cancelling ? 'Cancelling...' : 'Cancel'}
					</button>
				{/if}

				<!-- Expand chevron -->
				<button
					class="row-toggle shrink-0 job-active-row-chevron-btn"
					aria-expanded={expanded}
					title={expanded ? 'Collapse' : 'Expand'}
				>
					<svg
						class="h-4 w-4 job-active-row-chevron"
						fill="none"
						stroke="currentColor"
						viewBox="0 0 24 24"
						stroke-width="2"
					>
						<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
					</svg>
				</button>
			</div>
		</div>

		<!-- Progress row: own line below a divider, indented under content -->
		{#if active}
			<div class="job-active-row-progress">
				<LiveProgressLine sample={progressSample(job, live)} colorVar={accentVar} />
			</div>
		{/if}

		<!-- Expanded detail -->
		{#if expanded}
			<div transition:slide={{ duration: 200 }} class="job-active-row-expanded">
				<ActiveJobRowDetails {job} {typeConfig} {active} stageWords={ripStageWords(live.rip?.phase ?? null)} />
			</div>
		{/if}
	</div>
{/if}

<style>
	/* card-status colours its accent stripe from data-status (job/drive/
	   transcode statuses); the original's left accent was the video-type hue
	   instead, a different axis, so this overrides the accent colour. */
	.job-active-row {
		border-left-color: var(--jt-accent);
		cursor: pointer;
	}
	.job-active-row-collapsed {
		cursor: pointer;
		padding: 0.625rem 1rem 0;
	}
	.job-active-row-collapsed[data-inactive='true'] {
		padding-bottom: 0.625rem;
	}
	/* :global: forwarded through PosterImage's class prop */
	:global(.job-active-row-poster) {
		height: 2.5rem;
		width: 1.75rem;
		flex-shrink: 0;
		border-radius: var(--radius-sm);
		object-fit: cover;
	}
	/* :global: forwarded through PosterImage's class prop */
	:global(.job-active-row-poster-square) {
		width: 2.5rem;
	}
	.job-active-row-title {
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.job-active-row-meta {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-muted);
	}
	.job-active-row-type-pill {
		border-radius: var(--radius-sm);
		padding: 0.125rem 0.375rem;
		font-size: 0.75rem;
		line-height: 1rem;
		font-weight: 500;
		background: var(--jt-bg);
		color: var(--jt-text);
	}
	.job-active-row-disc-pill {
		border-radius: var(--radius-sm);
		padding: 0.125rem 0.375rem;
		font-size: 0.75rem;
		line-height: 1rem;
		background: var(--color-primary-tint-2);
	}
	.job-active-row-details {
		border-radius: var(--radius-md);
		border: 1px solid var(--color-border-strong);
		background: var(--color-primary-tint-3);
		padding: 0.375rem 1rem;
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 500;
		color: var(--color-primary);
		transition: background-color var(--motion-fast) var(--ease);
	}
	.job-active-row-details:hover {
		background: color-mix(in srgb, var(--color-primary) 25%, transparent);
	}
	.job-active-row-chevron-btn {
		padding: 0.125rem;
		color: var(--color-text-faint);
		transition: color var(--motion-fast) var(--ease);
	}
	.job-active-row-chevron-btn:hover {
		color: var(--color-text-secondary);
	}
	.job-active-row-chevron {
		transition: transform var(--motion-fast) var(--ease);
	}
	.job-active-row-chevron-btn[aria-expanded='true'] .job-active-row-chevron {
		transform: rotate(180deg);
	}
	.job-active-row-progress {
		margin-top: 0.5rem;
		border-top: 1px solid var(--color-border);
		padding: 0.625rem 1rem 0.625rem 4rem;
	}
	.job-active-row-expanded {
		border-top: 1px solid var(--color-border);
		padding: 0.75rem 1rem;
	}
</style>
