<script lang="ts">
	import type { TranscodeTaskView } from '$lib/types/api.gen';
	import StatusBadge from './StatusBadge.svelte';
	import ProgressBar from './ProgressBar.svelte';
	import { elapsedTime, etaTime, statusAccentVar } from '$lib/utils/format';
	import TimeAgo from './TimeAgo.svelte';
	import SkeletonCard from './SkeletonCard.svelte';
	import { slide } from 'svelte/transition';

	interface Props {
		job?: TranscodeTaskView;
	}

	let { job }: Props = $props();
	let expanded = $state(false);

	// v3 TranscodeTaskView has no rich job metadata (title/poster/year). Derive a
	// display label from the output path, then the source track id.
	let sourceFile = $derived(job?.output_path?.split('/').pop() ?? null);
	let displayTitle = $derived(sourceFile || `Transcode #${job?.id}`);
	let hasError = $derived(!!job?.last_error);
	let isActive = $derived(job?.status === 'in_progress');
	let accentVar = $derived(statusAccentVar(job?.status));
	let etaDisplay = $derived(
		isActive && job?.created_at ? etaTime(job.created_at, job.progress_pct) : null
	);

	function toggle(e: MouseEvent) {
		if ((e.target as HTMLElement).closest('a, button:not(.row-toggle)')) return;
		expanded = !expanded;
	}
</script>

{#if !job}
	<SkeletonCard />
{:else}
<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
<div
	class="rounded-lg border border-primary/20 border-l-4 border-l-primary bg-surface shadow-xs transition dark:border-primary/20 dark:bg-surface-dark"
	onclick={toggle}
	role="button"
	tabindex="0"
>
	<!-- Collapsed row -->
	<div class="cursor-pointer px-4 pt-2.5" class:pb-2.5={!isActive}>
		<div class="flex items-center gap-3">
			<!-- Title -->
			<h3 class="min-w-0 flex-shrink truncate font-semibold text-sm text-gray-900 dark:text-white">
				{displayTitle}
			</h3>

			<!-- Status badge -->
			<div class="shrink-0">
				<StatusBadge status={job.status} />
			</div>

			<!-- Spacer -->
			<span class="flex-1"></span>

			<!-- ETA (active) or Elapsed (otherwise) -->
			{#if isActive}
				<span class="shrink-0 text-xs text-gray-500 dark:text-gray-400" title="Estimated time remaining">
					{etaDisplay ? `~${etaDisplay}` : (job.created_at ? elapsedTime(job.created_at) : '-')}
				</span>
			{:else if job.created_at}
				<span class="shrink-0 text-xs text-gray-500 dark:text-gray-400">{elapsedTime(job.created_at)}</span>
			{/if}

			<!-- Error indicator -->
			{#if hasError}
				<span class="shrink-0 text-red-500 dark:text-red-400" title={job.last_error ?? ''}>
					<svg class="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
						<path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
					</svg>
				</span>
			{/if}

			<!-- Expand chevron -->
			<button class="row-toggle shrink-0 p-0.5 text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 transition-transform" class:rotate-180={expanded} title={expanded ? 'Collapse' : 'Expand'}>
				<svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
				</svg>
			</button>
		</div>
	</div>

	<!-- Progress row -->
	{#if isActive}
		<div class="mt-2 border-t border-primary/10 dark:border-primary/15 px-4 pl-[64px] pr-4 py-2.5">
			<ProgressBar value={job.progress_pct} colorVar={accentVar} />
		</div>
	{/if}

	<!-- Expanded detail -->
	{#if expanded}
		<div transition:slide={{ duration: 200 }} class="border-t border-primary/10 px-4 py-3 dark:border-primary/15">
			<div class="min-w-0 flex-1">
				<div class="mb-2">
					<span class="text-sm font-semibold text-gray-900 dark:text-white">{displayTitle}</span>
				</div>

				<table class="w-full text-xs">
					<tbody class="divide-y divide-primary/5 dark:divide-primary/10">
						<tr>
							<td class="py-1 pr-4 text-gray-500 dark:text-gray-400 whitespace-nowrap">Task ID</td>
							<td class="py-1">
								<a href="/jobs/{job.job_id}" class="text-primary hover:underline">#{job.id}</a>
							</td>
							<td class="py-1 pr-4 text-gray-500 dark:text-gray-400 whitespace-nowrap pl-6">Status</td>
							<td class="py-1"><StatusBadge status={job.status} /></td>
						</tr>
						<tr>
							<td class="py-1 pr-4 text-gray-500 dark:text-gray-400 whitespace-nowrap">Attempts</td>
							<td class="py-1 text-gray-900 dark:text-white">{job.attempts}</td>
							<td class="py-1 pr-4 text-gray-500 dark:text-gray-400 whitespace-nowrap pl-6">Output</td>
							<td class="py-1 font-mono text-gray-600 dark:text-gray-400 truncate" title={job.output_path ?? ''}>{sourceFile || '-'}</td>
						</tr>
						<tr>
							<td class="py-1 pr-4 text-gray-500 dark:text-gray-400 whitespace-nowrap">Started</td>
							<td class="py-1 text-gray-900 dark:text-white">{#if job.created_at}<TimeAgo date={job.created_at} />{:else}-{/if}</td>
							<td class="py-1 pr-4 text-gray-500 dark:text-gray-400 whitespace-nowrap pl-6">Updated</td>
							<td class="py-1 text-gray-900 dark:text-white">{#if job.updated_at}<TimeAgo date={job.updated_at} />{:else}-{/if}</td>
						</tr>
						<tr>
							<td class="py-1 pr-4 text-gray-500 dark:text-gray-400 whitespace-nowrap">Progress</td>
							<td class="py-1 text-gray-900 dark:text-white" colspan="3">{job.progress_pct}%</td>
						</tr>
					</tbody>
				</table>

				{#if hasError}
					<div class="mt-2 flex items-center gap-1 text-xs text-red-500 dark:text-red-400">
						<svg class="h-3.5 w-3.5 shrink-0" fill="currentColor" viewBox="0 0 20 20">
							<path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
						</svg>
						<span>{job.last_error}</span>
					</div>
				{/if}

				<!-- session_application_id == the owning job id, so link to the job. -->
				<div class="mt-3 flex flex-wrap items-center gap-2">
					<a
						href="/jobs/{job.job_id}"
						class="rounded-md border border-primary/30 bg-primary/15 px-3 py-1 text-xs font-medium text-primary hover:bg-primary/25"
					>Open job</a>
					<a
						href="/transcoder#task-{job.id}"
						class="rounded-md border border-primary/25 bg-transparent px-3 py-1 text-xs font-medium text-gray-600 hover:bg-primary/10 hover:text-gray-900 dark:text-gray-300 dark:hover:text-white"
					>Open transcoder</a>
				</div>
			</div>
		</div>
	{/if}
</div>
{/if}
