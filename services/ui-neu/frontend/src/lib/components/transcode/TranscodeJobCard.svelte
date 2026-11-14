<script lang="ts">
	import { fade } from 'svelte/transition';
	import StatusBadge from '$lib/components/shared/StatusBadge.svelte';
	import ProgressBar from '$lib/components/shared/ProgressBar.svelte';
	import TimeAgo from '$lib/components/shared/TimeAgo.svelte';
	import { fadeIn, fadeOut } from '$lib/transitions';
	import { formatElapsed } from '$lib/utils/format';
	import { pathBasename } from '$lib/utils/path';
	import { isAdmin } from '$lib/stores/auth';
	import type { TranscodeTaskView } from '$lib/types/api.gen';

	interface Props {
		job: TranscodeTaskView;
		onretry: (id: string) => unknown;
		ondelete: (id: string) => unknown;
	}

	let { job, onretry, ondelete }: Props = $props();

	const sourceFile = $derived(pathBasename(job.output_path));
</script>

<div
	in:fade={fadeIn}
	out:fade={fadeOut}
	class="card card-status transcoder-page-job-card"
	style:--card-accent="var(--color-primary)"
>
	<div class="min-w-0 flex-1">
		<!-- Row 1: Title + Status + Actions -->
		<div class="flex items-start justify-between gap-2">
			<div class="flex min-w-0 items-center gap-3">
				<h3 class="truncate transcoder-page-job-title" title={job.output_path ?? job.source_track_id}>
					{sourceFile || `Task #${job.id}`}
				</h3>
				<StatusBadge status={job.status} />
			</div>
			{#if $isAdmin}
				<div class="flex shrink-0 gap-2">
					{#if job.status === 'failed'}
						<button onclick={() => onretry(job.id)} class="btn btn-primary transcoder-page-job-action-btn">Retry</button
						>
					{/if}
					<button
						onclick={() => ondelete(job.id)}
						class="btn transcoder-page-job-action-btn transcoder-page-job-delete-btn">Delete</button
					>
				</div>
			{/if}
		</div>

		<!-- Row 2: ARM job link, attempts -->
		<div class="mt-0.5 flex items-center gap-2 transcoder-page-job-meta">
			{#if job.job_id}
				<a href="/jobs/{job.job_id}" data-testid="transcode-job-link" class="chip">Job {job.job_id}</a>
			{:else}
				<span class="chip transcoder-page-no-job-chip">No job</span>
			{/if}
			{#if job.attempts > 0}
				<span class="transcoder-page-attempt">Attempt {job.attempts}</span>
			{/if}
			{#if job.claimed_by}
				<span class="mono truncate transcoder-page-claimed-by">{job.claimed_by}</span>
			{/if}
		</div>

		<!-- Error message for failed tasks -->
		{#if job.status === 'failed' && job.last_error}
			<p class="mt-2 alert alert-danger">
				{job.last_error}
			</p>
		{/if}

		<!-- Progress bar for queued/in_progress -->
		{#if job.status === 'queued' || job.status === 'in_progress'}
			<div class="mt-3">
				<ProgressBar value={job.progress_pct} colorVar="var(--color-status-transcoding)" />
			</div>
		{/if}

		<!-- Timestamps -->
		<div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 transcoder-page-job-meta-sm">
			{#if job.created_at}
				<span>Queued <TimeAgo date={job.created_at} /></span>
			{/if}
			{#if job.updated_at}
				<span>Updated <TimeAgo date={job.updated_at} /></span>
			{/if}
			<!-- From claim to finish: created_at would add the queue wait (D-202).
			     Tasks from before started_at existed fall back to created_at. -->
			{#if job.status === 'done' && (job.started_at ?? job.created_at) && job.updated_at}
				{@const dur = formatElapsed(job.started_at ?? job.created_at, job.updated_at)}
				{#if dur}
					<span class="transcoder-page-took">Took {dur}</span>
				{/if}
			{/if}
		</div>

		<!-- Output path for done tasks -->
		{#if job.status === 'done' && job.output_path}
			<p class="mt-2 flex items-center gap-1 transcoder-page-job-meta-sm">
				<span class="transcoder-page-arrow">&rarr;</span>
				<span class="mono truncate" title={job.output_path}>{sourceFile}</span>
			</p>
		{/if}
	</div>
</div>

<style>
	/* card-status colours its left accent from data-status, but this card
	   never sets that attribute - the original was always primary blue.
	   style:--card-accent + this scoped rule (which already compiles
	   unlayered, beating card-status's own @layer components rule
	   regardless of specificity) reproduces that with no !important -
	   same precedent as JobCard/TranscodeCard's own accent override. */
	.transcoder-page-job-card {
		border-left-color: var(--card-accent);
		padding: 1rem;
	}
	.transcoder-page-job-title {
		font-weight: 600;
		color: var(--color-text);
	}
	/* original action buttons were px-2.5 py-1 text-xs (0.625rem/0.25rem),
	   smaller than .btn's own default */
	.transcoder-page-job-action-btn {
		padding: 0.25rem 0.625rem;
		font-size: 0.75rem;
		line-height: 1rem;
	}
	.transcoder-page-job-delete-btn {
		border: 0;
		background: var(--color-danger);
		color: var(--color-on-primary);
	}
	.transcoder-page-job-delete-btn:hover {
		filter: brightness(0.9);
	}
	.transcoder-page-job-meta {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	.transcoder-page-job-meta-sm {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-muted);
	}
	.transcoder-page-no-job-chip {
		cursor: default;
		color: var(--color-text-muted);
	}
	.transcoder-page-attempt {
		font-size: 0.75rem;
		line-height: 1rem;
	}
	.transcoder-page-claimed-by {
		font-size: 0.75rem;
		line-height: 1rem;
		color: var(--color-text-faint);
	}
	.transcoder-page-took {
		color: var(--color-success);
	}
	.transcoder-page-arrow {
		color: var(--color-text-faint);
	}
</style>
