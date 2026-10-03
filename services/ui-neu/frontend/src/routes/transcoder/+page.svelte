<script lang="ts">
	import { onMount } from 'svelte';
	import { fade } from 'svelte/transition';
	import { fetchTranscoderJobs, retryTranscoderJob, deleteTranscoderJob } from '$lib/api/transcoder';
	import type { TranscodeTaskView } from '$lib/types/api.gen';
	import StatusBadge from '$lib/components/StatusBadge.svelte';
	import ProgressBar from '$lib/components/ProgressBar.svelte';
	import TimeAgo from '$lib/components/TimeAgo.svelte';
	import LoadState from '$lib/components/LoadState.svelte';
	import SkeletonCard from '$lib/components/SkeletonCard.svelte';
	import { fadeIn, fadeOut } from '$lib/transitions';
	import { transcoderStats, transcoderWorkers, getJobsCache, setJobsCache } from '$lib/stores/transcoder';
	import { sortTranscodeTasks } from '$lib/utils/transcode-sort';
	import { isAdmin } from '$lib/stores/auth';

	const emptyJobs: TranscodeTaskView[] = [];

	// Singleton stores (see $lib/stores/transcoder) so stats/workers survive
	// navigation and don't flash the offline/empty state on every visit.
	const stats = transcoderStats;
	const statsError = stats.error;
	const statsInitialized = stats.initialized;
	const workers = transcoderWorkers;
	let activeTab = $state('all');
	// Seed jobs from the per-tab cache so a revisit paints the last cards
	// immediately instead of dropping to a skeleton.
	let jobs = $state<TranscodeTaskView[]>(getJobsCache('all') ?? emptyJobs);
	let sortedJobs = $derived([...jobs].sort(sortTranscodeTasks));
	let loadingJobs = $state(getJobsCache('all') == null);
	let jobsError = $state<Error | null>(null);

	// v3 statuses: queued | in_progress | done | failed. The UI tabs map onto
	// these; "online" is implied by a successful poll (store.initialized).
	const TAB_STATUS: Record<string, string | undefined> = {
		all: undefined,
		queued: 'queued',
		in_progress: 'in_progress',
		done: 'done',
		failed: 'failed'
	};

	let s = $derived($stats);
	function statusCount(status: string): number {
		return s.tasks_by_status?.[status] ?? 0;
	}

	function formatDuration(startISO: string | null, endISO?: string | null): string | null {
		if (!startISO) return null;
		const start = new Date(startISO).getTime();
		if (isNaN(start)) return null;
		const end = endISO ? new Date(endISO).getTime() : Date.now();
		if (isNaN(end)) return null;
		const diffSec = Math.max(0, Math.floor((end - start) / 1000));
		const h = Math.floor(diffSec / 3600);
		const m = Math.floor((diffSec % 3600) / 60);
		const sec = diffSec % 60;
		if (h > 0) return `${h}h ${m}m ${sec}s`;
		if (m > 0) return `${m}m ${sec}s`;
		return `${sec}s`;
	}

	function sourceBasename(path: string | null | undefined): string {
		if (!path) return '';
		const parts = path.replace(/\/+$/, '').split('/');
		return parts[parts.length - 1] ?? '';
	}

	async function loadJobs(showLoading = true) {
		if (showLoading) loadingJobs = true;
		jobsError = null;
		try {
			jobs = await fetchTranscoderJobs({ status: TAB_STATUS[activeTab] });
			setJobsCache(activeTab, jobs);
		} catch (e) {
			jobsError = e instanceof Error ? e : new Error('Failed to load jobs');
			jobs = emptyJobs;
		} finally {
			loadingJobs = false;
		}
	}

	function switchTab(tab: string) {
		activeTab = tab;
		// Show cached cards instantly for a previously-viewed tab; only the
		// first view of a tab shows the loading skeleton.
		loadJobs(getJobsCache(tab) == null);
	}

	async function handleRetry(id: string) {
		await retryTranscoderJob(id);
		loadJobs();
	}

	let actionFeedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	async function handleDelete(id: string) {
		if (confirm('Delete this transcode task?')) {
			await deleteTranscoderJob(id);
			loadJobs();
		}
	}

	let jobsTimer: ReturnType<typeof setInterval> | null = null;

	function startJobsPolling() {
		stopJobsPolling();
		jobsTimer = setInterval(() => loadJobs(false), 5000);
	}

	function stopJobsPolling() {
		if (jobsTimer) { clearInterval(jobsTimer); jobsTimer = null; }
	}

	// Auto-refresh jobs when any are queued or in progress.
	$effect(() => {
		if (statusCount('in_progress') > 0 || statusCount('queued') > 0) {
			startJobsPolling();
		} else {
			stopJobsPolling();
		}
	});

	onMount(() => {
		stats.start();
		workers.start();
		// Skeleton only when we have nothing cached for the current tab.
		loadJobs(getJobsCache(activeTab) == null);
		return () => { stats.stop(); workers.stop(); stopJobsPolling(); };
	});

	const tabs = ['all', 'queued', 'in_progress', 'done', 'failed'];
	// Pretty tab labels — `capitalize` alone leaves "in_progress" → "In_progress".
	const TAB_LABELS: Record<string, string> = {
		all: 'All',
		queued: 'Queued',
		in_progress: 'In Progress',
		done: 'Done',
		failed: 'Failed'
	};
</script>

<svelte:head>
	<title>ARM - Transcoder</title>
</svelte:head>

<div class="stack stack-lg">
	<h1 class="page-title">Transcoder</h1>

	<!-- API error -->
	{#if $statsError}
		<div in:fade={fadeIn} out:fade={fadeOut} class="alert alert-danger alert-lg">
			Failed to reach transcoder: {$statsError}
		</div>
	{/if}

	<!-- Stats / worker pool. On the very first load (nothing cached yet) show a
	     skeleton sized to match the real cards so it fills in place without a
	     layout shift; only show the "offline" banner once a poll has actually
	     confirmed the service is down, never while still loading. -->
	{#if !$statsInitialized && !$statsError}
		<div class="stack">
			<div class="panel">
				<!-- Same box as the real header row (mb-3 + text-sm line) so the card
				     is the same height before and after the first poll. -->
				<div class="mb-3 flex items-center justify-between">
					<div class="skeleton skeleton-text transcoder-page-skeleton-title"></div>
					<div class="skeleton skeleton-text transcoder-page-skeleton-subtitle"></div>
				</div>
			</div>
			<div class="grid grid-cols-2 gap-4 lg:grid-cols-5">
				{#each Array(5) as _unused}
					<div class="panel">
						<div class="skeleton skeleton-text transcoder-page-skeleton-label"></div>
						<div class="skeleton skeleton-text transcoder-page-skeleton-value"></div>
					</div>
				{/each}
			</div>
		</div>
	{:else if $statsError}
		<!-- Offline banner -->
		<div in:fade={fadeIn} out:fade={fadeOut} class="flex items-center gap-3 panel-section transcoder-page-offline-banner">
			<div class="shrink-0 transcoder-page-offline-dot"></div>
			<div>
				<p class="transcoder-page-offline-title">Transcoder Offline</p>
				<p class="transcoder-page-offline-subtitle">The transcoder service is not responding. Transcoding features are unavailable.</p>
			</div>
		</div>
	{:else}
		<!-- Worker pool + Stats cards -->
		{@const w = $workers}
		<div in:fade={fadeIn} out:fade={fadeOut} class="stack">
		<!-- Worker pool status -->
		<div class="panel">
			<div class="mb-3 flex items-center justify-between">
				<div class="flex items-center gap-2">
					<div class="transcoder-page-worker-dot" data-active={w.length > 0}></div>
					<span class="transcoder-page-worker-title">
						Workers {w.length}/{s.max_parallel} active
					</span>
				</div>
				<span class="transcoder-page-worker-summary">
					GPUs: {s.gpus_available}/{s.gpus_total} available &middot; Queue: {statusCount('queued')} queued
				</span>
			</div>
			{#if w.length > 0}
				<div class="grid gap-2 {s.max_parallel > 1 ? 'sm:grid-cols-2 lg:grid-cols-3' : ''}">
					{#each w as worker (worker.task_id)}
						<div class="flex items-center gap-3 transcoder-page-worker-card">
							<div class="transcoder-page-worker-pulse"></div>
							<div class="min-w-0 flex-1">
								<p class="truncate transcoder-page-worker-task" title={worker.output_path ?? worker.source_track_id}>
									Task #{worker.task_id}
									{#if worker.claimed_by}
										<span class="transcoder-page-worker-claimed"> &mdash; {worker.claimed_by}</span>
									{/if}
								</p>
								{#if worker.claim_heartbeat_at}
									{@const dur = formatDuration(worker.claim_heartbeat_at)}
									<p class="transcoder-page-worker-heartbeat">{worker.progress_pct}%{#if dur} &middot; {dur} since heartbeat{/if}</p>
								{:else}
									<p class="transcoder-page-worker-heartbeat-idle">{worker.progress_pct}%</p>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>
		<div class="grid grid-cols-2 gap-4 lg:grid-cols-5">
			<div class="stat transcoder-page-stat">
				<p class="stat-label">Queued</p>
				<p class="stat-value transcoder-page-stat-value">{statusCount('queued')}</p>
			</div>
			<div class="stat transcoder-page-stat">
				<p class="stat-label">In Progress</p>
				<p class="stat-value transcoder-page-stat-value transcoder-page-stat-value-progress">{statusCount('in_progress')}</p>
			</div>
			<div class="stat transcoder-page-stat">
				<p class="stat-label">Done</p>
				<p class="stat-value transcoder-page-stat-value transcoder-page-stat-value-success">{statusCount('done')}</p>
			</div>
			<div class="stat transcoder-page-stat">
				<p class="stat-label">Failed</p>
				<p class="stat-value transcoder-page-stat-value transcoder-page-stat-value-danger">{statusCount('failed')}</p>
			</div>
			<div class="stat transcoder-page-stat">
				<p class="stat-label">Total</p>
				<p class="stat-value transcoder-page-stat-value transcoder-page-stat-value-muted">{s.total_tasks}</p>
			</div>
		</div>
		</div>
	{/if}

	<!-- Jobs section -->
	<section class="space-y-4">
		<h2 class="transcoder-page-section-title">Transcode Jobs</h2>

		{#if actionFeedback}
			<div class="alert {actionFeedback.type === 'success' ? 'alert-success' : 'alert-danger'}">
				{actionFeedback.message}
				<button onclick={() => (actionFeedback = null)} class="btn btn-link transcoder-page-dismiss">Dismiss</button>
			</div>
		{/if}

		<!-- Tabs -->
		<div class="tabs transcoder-page-tabs">
			{#each tabs as tab}
				<button
					onclick={() => switchTab(tab)}
					data-selected={activeTab === tab}
					class="tabs-tab transcoder-page-tab"
				>
					{TAB_LABELS[tab] ?? tab}
				</button>
			{/each}
		</div>

		<!-- Jobs list -->
		<LoadState
			data={sortedJobs}
			loading={loadingJobs}
			error={jobsError}
			isEmpty={(d) => d.length === 0}
			transitionKey="transcoder-jobs"
		>
			{#snippet loadingSlot()}
				<!-- As many placeholders as the stats poll says there are tasks (it
				     lands first), so the list does not grow when the jobs arrive. -->
				<div class="stack stack-sm">
					{#each Array(Math.min(s.total_tasks || 3, 6)) as _unused}
						<SkeletonCard lines={4} class="pb-3" />
					{/each}
				</div>
			{/snippet}
			{#snippet empty()}
				<p class="transcoder-page-empty">No transcode tasks found.</p>
			{/snippet}
			{#snippet ready(jobList)}
			<div class="stack stack-sm">
				{#each jobList as job (job.id)}
					{@const sourceFile = sourceBasename(job.output_path)}
					<div in:fade={fadeIn} out:fade={fadeOut} class="card card-status transcoder-page-job-card" style:--card-accent="var(--color-primary)">
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
											<button
												onclick={() => handleRetry(job.id)}
												class="btn btn-primary transcoder-page-job-action-btn"
											>Retry</button>
										{/if}
										<button
											onclick={() => handleDelete(job.id)}
											class="btn transcoder-page-job-action-btn transcoder-page-job-delete-btn"
										>Delete</button>
									</div>
								{/if}
							</div>

							<!-- Row 2: ARM job link, attempts -->
							<div class="mt-0.5 flex items-center gap-2 transcoder-page-job-meta">
								{#if job.job_id}
									<a
										href="/jobs/{job.job_id}"
										data-testid="transcode-job-link"
										class="chip"
									>Job {job.job_id}</a>
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
								{#if job.status === 'done' && job.created_at && job.updated_at}
									{@const dur = formatDuration(job.created_at, job.updated_at)}
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
				{/each}
			</div>
			{/snippet}
		</LoadState>
	</section>
</div>

<style>
	/* the original tab strip had no overflow-x-auto and its buttons had no
	   whitespace-nowrap - at narrow widths the row itself shrinks and
	   "In Progress" wraps to two lines, rather than the strip scrolling
	   horizontally with single-line tabs */
	/* the original tab strip was gap-1 (0.25rem), not .tabs' own 1rem
	   default (tuned for the wider Settings tab strip); no overflow-x-auto
	   either, so the row shrinks and wraps rather than scrolling */
	.transcoder-page-tabs { gap: 0.25rem; overflow-x: visible; }
	/* the original buttons were px-4 py-2 (1rem/0.5rem), not .tabs-tab's own
	   0.25rem/0.625rem default, and had no whitespace-nowrap */
	.transcoder-page-tab { padding: 0.5rem 1rem; white-space: normal; flex-shrink: 1; min-width: 0; text-align: center; }
	.transcoder-page-skeleton-title { height: 1.5rem; width: 14rem; }
	.transcoder-page-skeleton-subtitle { height: 1rem; width: 12rem; }
	.transcoder-page-skeleton-label { height: 1rem; width: 4rem; }
	.transcoder-page-skeleton-value { margin-top: 0.5rem; height: 2rem; width: 3rem; }
	.transcoder-page-offline-dot { height: 0.75rem; width: 0.75rem; border-radius: 9999px; background: var(--color-text-faint); }
	.transcoder-page-offline-title { font-weight: 500; color: var(--color-text-secondary); }
	.transcoder-page-offline-subtitle { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	/* panel-section's own background is a translucent primary tint, which
	   only matches the original's DARK-mode bg-page/5 half of its pair; the
	   original LIGHT mode was the flat --color-page - same gap as the
	   NotificationsTab precedent from Task 9 */
	.transcoder-page-offline-banner { background: var(--color-page); }
	.transcoder-page-worker-dot { height: 0.625rem; width: 0.625rem; border-radius: 9999px; background: var(--color-warning); }
	.transcoder-page-worker-dot[data-active="true"] { background: var(--color-success); }
	.transcoder-page-worker-title { font-size: 0.875rem; line-height: 1.25rem; font-weight: 600; color: var(--color-text-secondary); }
	.transcoder-page-worker-summary { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-faint); }
	/* the original worker card used a literal indigo hue (border-indigo-200,
	   bg-indigo-50/50) with no shared token; collapses onto
	   --color-status-transcoding (violet), the same tone already accepted
	   for the transcoder domain's progress-bar tone (DEVIATIONS.md group 2) */
	.transcoder-page-worker-card { border: 1px solid color-mix(in srgb, var(--color-status-transcoding) 30%, transparent); border-radius: var(--radius-md); background: color-mix(in srgb, var(--color-status-transcoding) 8%, transparent); padding: 0.5rem 0.75rem; }
	.transcoder-page-worker-pulse { height: 0.5rem; width: 0.5rem; flex-shrink: 0; border-radius: 9999px; background: var(--color-status-transcoding); animation: skeleton-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
	.transcoder-page-worker-task { font-size: 0.875rem; line-height: 1.25rem; font-weight: 500; color: var(--color-text-secondary); }
	.transcoder-page-worker-claimed { font-weight: 400; color: var(--color-text-muted); }
	.transcoder-page-worker-heartbeat { font-size: 0.75rem; line-height: 1rem; color: var(--color-status-transcoding); }
	.transcoder-page-worker-heartbeat-idle { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-faint); }
	/* the original stat cards were text-3xl (1.875rem/2.25rem), taller than
	   stat's own 1.5rem/2rem default (tuned for StatStrip) */
	.transcoder-page-stat-value { font-size: 1.875rem; line-height: 2.25rem; }
	/* the original "In Progress" value used a literal indigo hue with no
	   shared token; same transcoder-domain collapse as the worker card and
	   progress-bar tone above */
	.transcoder-page-stat-value-progress { color: var(--color-status-transcoding); }
	.transcoder-page-stat-value-success { color: var(--color-success); }
	.transcoder-page-stat-value-danger { color: var(--color-danger); }
	.transcoder-page-stat-value-muted { color: var(--color-text-muted); }
	.transcoder-page-section-title { font-size: 1.125rem; line-height: 1.75rem; font-weight: 600; color: var(--color-text); }
	.transcoder-page-dismiss { margin-left: 0.5rem; }
	.transcoder-page-dismiss:hover { opacity: 0.75; }
	.transcoder-page-empty { padding: 2rem 0; text-align: center; color: var(--color-text-faint); }
	/* card-status colours its left accent from data-status, but this card
	   never sets that attribute - the original was always primary blue.
	   style:--card-accent + this scoped rule (which already compiles
	   unlayered, beating card-status's own @layer components rule
	   regardless of specificity) reproduces that with no !important -
	   same precedent as JobCard/TranscodeCard's own accent override. */
	.transcoder-page-job-card { border-left-color: var(--card-accent); padding: 1rem; }
	.transcoder-page-job-title { font-weight: 600; color: var(--color-text); }
	/* original action buttons were px-2.5 py-1 text-xs (0.625rem/0.25rem),
	   smaller than .btn's own default */
	.transcoder-page-job-action-btn { padding: 0.25rem 0.625rem; font-size: 0.75rem; line-height: 1rem; }
	.transcoder-page-job-delete-btn { border: 0; background: var(--color-danger); color: var(--color-on-primary); }
	.transcoder-page-job-delete-btn:hover { filter: brightness(0.9); }
	.transcoder-page-job-meta { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	.transcoder-page-job-meta-sm { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
	.transcoder-page-no-job-chip { cursor: default; color: var(--color-text-muted); }
	.transcoder-page-attempt { font-size: 0.75rem; line-height: 1rem; }
	.transcoder-page-claimed-by { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-faint); }
	.transcoder-page-took { color: var(--color-success); }
	.transcoder-page-arrow { color: var(--color-text-faint); }
</style>
