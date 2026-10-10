<script lang="ts">
	import type { JobView } from '$lib/types/api.gen';
	import StatusBadge from './StatusBadge.svelte';
	import Skeleton from './Skeleton.svelte';
	import { getVideoTypeConfig, discTypeLabel } from '$lib/utils/job-type';
	import { transcodeColumnStatus } from '$lib/utils/job-status';
	import { statusLabel } from '$lib/utils/format';
	import DiscTypeIcon from './DiscTypeIcon.svelte';
	import VideoTypeIcon from './VideoTypeIcon.svelte';

	interface Props {
		job?: JobView;
		selected?: boolean;
		onselect?: (jobId: string, selected: boolean) => void;
		/** Selection exists only to feed bulk actions — hide the checkbox for guests. */
		showSelect?: boolean;
	}

	let { job, selected = false, onselect, showSelect = true }: Props = $props();

	let typeConfig = $derived(getVideoTypeConfig(null, job?.disc_type ?? null));
	let tc = $derived(job ? transcodeColumnStatus(job) : null);
	// Only show the caption when it carries extra information (e.g. "Transcoding 2/4")
	// that the StatusBadge label does not already show.  For plain terminal states
	// ("Complete", "Transcode failed") tc.label === statusLabel(tc.badgeStatus), so
	// the caption is suppressed to avoid showing the same text twice.
	let tcDetail = $derived(tc && tc.label !== statusLabel(tc.badgeStatus) ? tc.label : null);
</script>

{#if !job}
	<tr aria-busy="true">
		{#each { length: 7 } as _}
			<td class="table-cell" data-label=""><Skeleton variant="line" width="80%" height="1rem" /></td>
		{/each}
	</tr>
{:else}
<tr class="table-row" data-selected={selected}>
	<!-- Checkbox -->
	<td class="table-cell w-8" data-label="">
		{#if showSelect}
			<input
				type="checkbox"
				checked={selected}
				onchange={() => onselect?.(job.id, !selected)}
				class="job-row-checkbox"
			/>
		{/if}
	</td>

	<!-- Title -->
	<td class="table-cell" data-label="Title">
		<div class="flex items-center gap-2" style:--jt-icon={typeConfig.iconColor}>
			<VideoTypeIcon icon={typeConfig.icon} class="h-4 w-4 shrink-0 job-row-type-icon" />
			<div class="min-w-0">
				<a href="/jobs/{job.id}" class="job-row-title-link">
					{job.title || 'Untitled'}
				</a>
			</div>
		</div>
	</td>

	<!-- Year -->
	<td class="table-cell" data-label="Year">
		<div class="flex items-center gap-1.5">
			{#if job.year}
				<span>{job.year}</span>
			{/if}
		</div>
	</td>

	<!-- Rip -->
	<td class="table-cell" data-label="Rip">
		<StatusBadge status={job.status} />
	</td>

	<!-- Transcode -->
	<td class="table-cell" data-label="Transcode">
		{#if tc}
			<span class="flex items-center gap-1.5">
				<StatusBadge status={tc.badgeStatus} />
				{#if tcDetail}
					<span class="job-row-transcode-detail">{tcDetail}</span>
				{/if}
			</span>
		{:else}
			<span class="job-row-dash">-</span>
		{/if}
	</td>

	<!-- Type (colored badge) -->
	<td class="table-cell" data-label="Type">
		<span class="job-row-type-pill" style:--jt-bg={typeConfig.badgeBg} style:--jt-text={typeConfig.badgeText}>{typeConfig.label}</span>
	</td>

	<!-- Disc -->
	<td class="table-cell" data-label="Disc">
		{#if job.disc_type}
			<span class="inline-flex items-center gap-1">
				<DiscTypeIcon disctype={job.disc_type} size="h-4 w-4" />
				{discTypeLabel(job.disc_type)}
			</span>
		{/if}
	</td>
</tr>
{/if}

<style>
	.job-row-transcode-detail { font-size: 11px; line-height: 1rem; color: var(--color-text-muted); }
	.job-row-dash { color: var(--color-text-faint); }
	.job-row-type-pill { border-radius: var(--radius-sm); padding: 0.125rem 0.375rem; font-size: 0.75rem; line-height: 1rem; font-weight: 500; background: var(--jt-bg); color: var(--jt-text); }
	.job-row-checkbox { width: 1rem; height: 1rem; border-radius: var(--radius-sm); accent-color: var(--color-primary); }
	.job-row-title-link { font-weight: 500; color: var(--color-primary-text); }
	/* :global: forwarded through VideoTypeIcon's class prop onto its own icon */
	:global(.job-row-type-icon) { color: var(--jt-icon); }
</style>
