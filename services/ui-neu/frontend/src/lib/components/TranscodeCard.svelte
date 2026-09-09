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
	class="card card-status transcode-card"
	data-status={job.status}
	style:--card-accent="var(--color-primary)"
	onclick={toggle}
	role="button"
	tabindex="0"
>
	<!-- Collapsed row -->
	<div class="transcode-card-row" data-active={isActive}>
		<div class="flex items-center gap-3">
			<!-- Title -->
			<h3 class="min-w-0 flex-shrink truncate transcode-card-title">
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
				<span class="shrink-0 transcode-card-meta" title="Estimated time remaining">
					{etaDisplay ? `~${etaDisplay}` : (job.created_at ? elapsedTime(job.created_at) : '-')}
				</span>
			{:else if job.created_at}
				<span class="shrink-0 transcode-card-meta">{elapsedTime(job.created_at)}</span>
			{/if}

			<!-- Error indicator -->
			{#if hasError}
				<span class="shrink-0 transcode-card-error-icon" title={job.last_error ?? ''}>
					<svg class="h-4 w-4" fill="currentColor" viewBox="0 0 20 20">
						<path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
					</svg>
				</span>
			{/if}

			<!-- Expand chevron -->
			<button class="row-toggle shrink-0 transcode-card-chevron" aria-expanded={expanded} title={expanded ? 'Collapse' : 'Expand'}>
				<svg class="h-4 w-4 chevron" fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
				</svg>
			</button>
		</div>
	</div>

	<!-- Progress row -->
	{#if isActive}
		<div class="transcode-card-progress-row">
			<ProgressBar value={job.progress_pct} colorVar={accentVar} />
		</div>
	{/if}

	<!-- Expanded detail -->
	{#if expanded}
		<div transition:slide={{ duration: 200 }} class="transcode-card-detail">
			<div class="min-w-0 flex-1">
				<div class="transcode-card-detail-title-row">
					<span class="transcode-card-detail-title">{displayTitle}</span>
				</div>

				<table class="transcode-card-detail-table">
					<tbody>
						<tr>
							<td class="transcode-card-detail-label whitespace-nowrap">Task ID</td>
							<td class="transcode-card-detail-value">
								<a href="/jobs/{job.job_id}" class="transcode-card-detail-link">#{job.id}</a>
							</td>
							<td class="transcode-card-detail-label whitespace-nowrap transcode-card-detail-col2">Status</td>
							<td class="transcode-card-detail-value"><StatusBadge status={job.status} /></td>
						</tr>
						<tr>
							<td class="transcode-card-detail-label whitespace-nowrap">Attempts</td>
							<td class="transcode-card-detail-value transcode-card-detail-value-strong">{job.attempts}</td>
							<td class="transcode-card-detail-label whitespace-nowrap transcode-card-detail-col2">Output</td>
							<td class="mono truncate transcode-card-detail-output" title={job.output_path ?? ''}>{sourceFile || '-'}</td>
						</tr>
						<tr>
							<td class="transcode-card-detail-label whitespace-nowrap">Started</td>
							<td class="transcode-card-detail-value transcode-card-detail-value-strong">{#if job.created_at}<TimeAgo date={job.created_at} />{:else}-{/if}</td>
							<td class="transcode-card-detail-label whitespace-nowrap transcode-card-detail-col2">Updated</td>
							<td class="transcode-card-detail-value transcode-card-detail-value-strong">{#if job.updated_at}<TimeAgo date={job.updated_at} />{:else}-{/if}</td>
						</tr>
						<tr>
							<td class="transcode-card-detail-label whitespace-nowrap">Progress</td>
							<td class="transcode-card-detail-value transcode-card-detail-value-strong" colspan="3">{job.progress_pct}%</td>
						</tr>
					</tbody>
				</table>

				{#if hasError}
					<div class="flex items-center gap-1 transcode-card-detail-error">
						<svg class="h-3.5 w-3.5 shrink-0" fill="currentColor" viewBox="0 0 20 20">
							<path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clip-rule="evenodd" />
						</svg>
						<span>{job.last_error}</span>
					</div>
				{/if}

				<!-- Link to the owning job via job.job_id. -->
				<div class="cluster transcode-card-detail-actions">
					<a
						href="/jobs/{job.job_id}"
						class="transcode-card-open-job"
					>Open job</a>
					<a
						href="/transcoder#task-{job.id}"
						class="btn btn-sm transcode-card-open-transcoder"
					>Open transcoder</a>
				</div>
			</div>
		</div>
	{/if}
</div>
{/if}

<style>
	/* card-status colours its left accent from data-status; the ORIGINAL
	   TranscodeCard accent was always primary blue (border-l-primary), not
	   status-driven - same precedent as JobCard's video-type accent
	   override: a style:--card-accent custom property set from the
	   template, read here, no !important needed (this scoped rule already
	   compiles unlayered, which beats card-status[data-status]'s own
	   @layer components rule regardless of its higher selector
	   specificity). */
	.transcode-card { border-left-color: var(--card-accent); }
	.transcode-card-row { cursor: pointer; padding: 0.625rem 1rem 0; }
	.transcode-card-row[data-active="false"] { padding-bottom: 0.625rem; }
	.transcode-card-title { font-size: 0.875rem; line-height: 1.25rem; font-weight: 600; color: var(--color-text); }
	.transcode-card-meta { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
	.transcode-card-error-icon { color: var(--color-danger); }
	.transcode-card-chevron { padding: 0.125rem; color: var(--color-text-faint); transition: transform var(--motion-fast) var(--ease); }
	.transcode-card-chevron:hover { color: var(--color-text-muted); }
	.transcode-card-chevron[aria-expanded="true"] .chevron { transform: rotate(180deg); }
	.transcode-card-progress-row { margin-top: 0.5rem; border-top: 1px solid var(--color-border); padding: 0.625rem 1rem 0.625rem 4rem; }
	.transcode-card-detail { border-top: 1px solid var(--color-border); padding: 0.75rem 1rem; }
	.transcode-card-detail-title-row { margin-bottom: 0.5rem; }
	.transcode-card-detail-title { font-size: 0.875rem; line-height: 1.25rem; font-weight: 600; color: var(--color-text); }
	.transcode-card-detail-table { width: 100%; font-size: 0.75rem; line-height: 1rem; border-collapse: collapse; }
	.transcode-card-detail-table tr { border-top: 1px solid var(--color-border); }
	.transcode-card-detail-table tr:first-child { border-top: 0; }
	.transcode-card-detail-table td { padding: 0.25rem 0; }
	.transcode-card-detail-label { padding-right: 1rem; color: var(--color-text-muted); }
	.transcode-card-detail-col2 { padding-left: 1.5rem; }
	.transcode-card-detail-value { color: var(--color-text); }
	.transcode-card-detail-value-strong { color: var(--color-text); }
	.transcode-card-detail-link { color: var(--color-primary); }
	.transcode-card-detail-link:hover { text-decoration: underline; }
	.transcode-card-detail-output { color: var(--color-text-muted); }
	.transcode-card-detail-error { margin-top: 0.5rem; font-size: 0.75rem; line-height: 1rem; color: var(--color-danger); }
	.transcode-card-detail-actions { margin-top: 0.75rem; }
	/* solid-tinted pill (bg-primary/15, no border) - .btn's outlined default
	   doesn't reproduce that, so it stays a scoped pill like JobActions'
	   own tone pills */
	.transcode-card-open-job { border-radius: var(--radius-md); padding: 0.25rem 0.75rem; font-size: 0.75rem; line-height: 1rem; font-weight: 500; background: var(--color-primary-tint-3); color: var(--color-primary-text); }
	.transcode-card-open-job:hover { background: color-mix(in srgb, var(--color-primary-tint-3) 70%, var(--color-primary)); }
	.transcode-card-open-transcoder { border-color: var(--color-border); color: var(--color-text-muted); }
	.transcode-card-open-transcoder:hover { color: var(--color-text); }
</style>
