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
	}

	let { job, selected = false, onselect }: Props = $props();

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
			<td class="p-2" data-label=""><Skeleton variant="line" width="80%" height="1rem" /></td>
		{/each}
	</tr>
{:else}
<tr class="border-b border-primary/20 hover:bg-page dark:border-primary/20 dark:hover:bg-primary/5 {selected ? 'bg-primary/[0.03] dark:bg-primary/[0.06]' : ''}">
	<!-- Checkbox -->
	<td class="px-4 py-3 w-8" data-label="">
		<input
			type="checkbox"
			checked={selected}
			onchange={() => onselect?.(job.id, !selected)}
			class="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary dark:border-gray-600 dark:bg-gray-700"
		/>
	</td>

	<!-- Title -->
	<td class="px-4 py-3" data-label="Title">
		<div class="flex items-center gap-2">
			<VideoTypeIcon icon={typeConfig.icon} class="h-4 w-4 shrink-0 {typeConfig.iconColor}" />
			<div class="min-w-0">
				<a href="/jobs/{job.id}" class="font-medium text-primary-text hover:underline dark:text-primary-text-dark">
					{job.title || 'Untitled'}
				</a>
			</div>
		</div>
	</td>

	<!-- Year -->
	<td class="px-4 py-3 text-sm" data-label="Year">
		<div class="flex items-center gap-1.5">
			{#if job.year}
				<span>{job.year}</span>
			{/if}
		</div>
	</td>

	<!-- Rip -->
	<td class="px-4 py-3" data-label="Rip">
		<StatusBadge status={job.status} />
	</td>

	<!-- Transcode -->
	<td class="px-4 py-3" data-label="Transcode">
		{#if tc}
			<span class="flex items-center gap-1.5">
				<StatusBadge status={tc.badgeStatus} />
				{#if tcDetail}
					<span class="text-[11px] text-gray-500 dark:text-gray-400">{tcDetail}</span>
				{/if}
			</span>
		{:else}
			<span class="text-gray-400 dark:text-gray-500">—</span>
		{/if}
	</td>

	<!-- Type (colored badge) -->
	<td class="px-4 py-3 text-sm" data-label="Type">
		<span class="rounded-sm px-1.5 py-0.5 text-xs font-medium {typeConfig.badgeClasses}">{typeConfig.label}</span>
	</td>

	<!-- Disc -->
	<td class="px-4 py-3 text-sm" data-label="Disc">
		{#if job.disc_type}
			<span class="inline-flex items-center gap-1">
				<DiscTypeIcon disctype={job.disc_type} size="h-4 w-4" />
				{discTypeLabel(job.disc_type)}
			</span>
		{/if}
	</td>
</tr>
{/if}
