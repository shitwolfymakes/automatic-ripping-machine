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

<div class="space-y-6">
	<h1 class="text-2xl font-bold text-gray-900 dark:text-white">Transcoder</h1>

	<!-- API error -->
	{#if $statsError}
		<div in:fade={fadeIn} out:fade={fadeOut} class="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
			Failed to reach transcoder: {$statsError}
		</div>
	{/if}

	<!-- Stats / worker pool. On the very first load (nothing cached yet) show a
	     skeleton sized to match the real cards so it fills in place without a
	     layout shift; only show the "offline" banner once a poll has actually
	     confirmed the service is down, never while still loading. -->
	{#if !$statsInitialized && !$statsError}
		<div class="space-y-4">
			<div class="rounded-lg border border-primary/20 bg-surface p-4 shadow-xs dark:border-primary/20 dark:bg-surface-dark">
				<!-- Same box as the real header row (mb-3 + text-sm line) so the card
				     is the same height before and after the first poll. -->
				<div class="mb-3 flex items-center justify-between">
					<div class="h-6 w-56 animate-pulse rounded bg-gray-200 dark:bg-gray-700"></div>
					<div class="h-4 w-48 animate-pulse rounded bg-gray-200 dark:bg-gray-700"></div>
				</div>
			</div>
			<div class="grid grid-cols-2 gap-4 lg:grid-cols-5">
				{#each Array(5) as _unused}
					<div class="rounded-lg border border-primary/20 bg-surface p-4 shadow-xs dark:border-primary/20 dark:bg-surface-dark">
						<div class="h-4 w-16 animate-pulse rounded bg-gray-200 dark:bg-gray-700"></div>
						<div class="mt-2 h-8 w-12 animate-pulse rounded bg-gray-200 dark:bg-gray-700"></div>
					</div>
				{/each}
			</div>
		</div>
	{:else if $statsError}
		<!-- Offline banner -->
		<div in:fade={fadeIn} out:fade={fadeOut} class="flex items-center gap-3 rounded-lg border border-primary/25 bg-page p-4 dark:border-primary/25 dark:bg-page-dark">
			<div class="h-3 w-3 shrink-0 rounded-full bg-gray-400"></div>
			<div>
				<p class="font-medium text-gray-700 dark:text-gray-300">Transcoder Offline</p>
				<p class="text-sm text-gray-500 dark:text-gray-400">The transcoder service is not responding. Transcoding features are unavailable.</p>
			</div>
		</div>
	{:else}
		<!-- Worker pool + Stats cards -->
		{@const w = $workers}
		<div in:fade={fadeIn} out:fade={fadeOut} class="space-y-4">
		<!-- Worker pool status -->
		<div class="rounded-lg border border-primary/20 bg-surface p-4 shadow-xs dark:border-primary/20 dark:bg-surface-dark">
			<div class="mb-3 flex items-center justify-between">
				<div class="flex items-center gap-2">
					<div class="h-2.5 w-2.5 rounded-full {w.length > 0 ? 'bg-green-500' : 'bg-yellow-500'}"></div>
					<span class="text-sm font-semibold text-gray-700 dark:text-gray-300">
						Workers {w.length}/{s.max_parallel} active
					</span>
				</div>
				<span class="text-xs text-gray-400 dark:text-gray-500">
					GPUs: {s.gpus_available}/{s.gpus_total} available &middot; Queue: {statusCount('queued')} queued
				</span>
			</div>
			{#if w.length > 0}
				<div class="grid gap-2 {s.max_parallel > 1 ? 'sm:grid-cols-2 lg:grid-cols-3' : ''}">
					{#each w as worker (worker.task_id)}
						<div class="flex items-center gap-3 rounded-md border border-indigo-200 bg-indigo-50/50 px-3 py-2 dark:border-indigo-800 dark:bg-indigo-900/20">
							<div class="h-2 w-2 rounded-full bg-indigo-500 animate-pulse"></div>
							<div class="min-w-0 flex-1">
								<p class="truncate text-sm font-medium text-gray-700 dark:text-gray-300" title={worker.output_path ?? worker.source_track_id}>
									Task #{worker.task_id}
									{#if worker.claimed_by}
										<span class="font-normal text-gray-500 dark:text-gray-400"> &mdash; {worker.claimed_by}</span>
									{/if}
								</p>
								{#if worker.claim_heartbeat_at}
									{@const dur = formatDuration(worker.claim_heartbeat_at)}
									<p class="text-xs text-indigo-600 dark:text-indigo-400">{worker.progress_pct}%{#if dur} &middot; {dur} since heartbeat{/if}</p>
								{:else}
									<p class="text-xs text-gray-400 dark:text-gray-500">{worker.progress_pct}%</p>
								{/if}
							</div>
						</div>
					{/each}
				</div>
			{/if}
		</div>
		<div class="grid grid-cols-2 gap-4 lg:grid-cols-5">
			<div class="rounded-lg border border-primary/20 bg-surface p-4 shadow-xs dark:border-primary/20 dark:bg-surface-dark">
				<p class="text-sm text-gray-500 dark:text-gray-400">Queued</p>
				<p class="mt-1 text-3xl font-bold text-primary-text dark:text-primary-text-dark">{statusCount('queued')}</p>
			</div>
			<div class="rounded-lg border border-primary/20 bg-surface p-4 shadow-xs dark:border-primary/20 dark:bg-surface-dark">
				<p class="text-sm text-gray-500 dark:text-gray-400">In Progress</p>
				<p class="mt-1 text-3xl font-bold text-indigo-600 dark:text-indigo-400">{statusCount('in_progress')}</p>
			</div>
			<div class="rounded-lg border border-primary/20 bg-surface p-4 shadow-xs dark:border-primary/20 dark:bg-surface-dark">
				<p class="text-sm text-gray-500 dark:text-gray-400">Done</p>
				<p class="mt-1 text-3xl font-bold text-green-600 dark:text-green-400">{statusCount('done')}</p>
			</div>
			<div class="rounded-lg border border-primary/20 bg-surface p-4 shadow-xs dark:border-primary/20 dark:bg-surface-dark">
				<p class="text-sm text-gray-500 dark:text-gray-400">Failed</p>
				<p class="mt-1 text-3xl font-bold text-red-600 dark:text-red-400">{statusCount('failed')}</p>
			</div>
			<div class="rounded-lg border border-primary/20 bg-surface p-4 shadow-xs dark:border-primary/20 dark:bg-surface-dark">
				<p class="text-sm text-gray-500 dark:text-gray-400">Total</p>
				<p class="mt-1 text-3xl font-bold text-gray-500 dark:text-gray-400">{s.total_tasks}</p>
			</div>
		</div>
		</div>
	{/if}

	<!-- Jobs section -->
	<section class="space-y-4">
		<h2 class="text-lg font-semibold text-gray-900 dark:text-white">Transcode Jobs</h2>

		{#if actionFeedback}
			<div class="rounded-lg border px-4 py-3 text-sm {actionFeedback.type === 'success' ? 'border-green-200 bg-green-50 text-green-700 dark:border-green-800 dark:bg-green-900/20 dark:text-green-400' : 'border-red-200 bg-red-50 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400'}">
				{actionFeedback.message}
				<button onclick={() => (actionFeedback = null)} class="ml-2 font-medium hover:opacity-75">Dismiss</button>
			</div>
		{/if}

		<!-- Tabs -->
		<div class="flex gap-1 border-b border-primary/20 dark:border-primary/20">
			{#each tabs as tab}
				<button
					onclick={() => switchTab(tab)}
					class="border-b-2 px-4 py-2 text-sm font-medium transition-colors
						{activeTab === tab
							? 'border-primary text-primary-text dark:border-primary-text-dark dark:text-primary-text-dark'
							: 'border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300'}"
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
				<div class="space-y-3">
					{#each Array(Math.min(s.total_tasks || 3, 6)) as _unused}
						<SkeletonCard lines={4} class="pb-3" />
					{/each}
				</div>
			{/snippet}
			{#snippet empty()}
				<p class="py-8 text-center text-gray-400">No transcode tasks found.</p>
			{/snippet}
			{#snippet ready(jobList)}
			<div class="space-y-3">
				{#each jobList as job (job.id)}
					{@const sourceFile = sourceBasename(job.output_path)}
					<div in:fade={fadeIn} out:fade={fadeOut} class="rounded-lg border border-primary/20 border-l-4 border-l-primary bg-surface p-4 shadow-xs dark:border-primary/20 dark:bg-surface-dark">
						<div class="min-w-0 flex-1">
							<!-- Row 1: Title + Status + Actions -->
							<div class="flex items-start justify-between gap-2">
								<div class="flex min-w-0 items-center gap-3">
									<h3 class="truncate font-semibold text-gray-900 dark:text-white" title={job.output_path ?? job.source_track_id}>
										{sourceFile || `Task #${job.id}`}
									</h3>
									<StatusBadge status={job.status} />
								</div>
								{#if $isAdmin}
									<div class="flex shrink-0 gap-2">
										{#if job.status === 'failed'}
											<button
												onclick={() => handleRetry(job.id)}
												class="rounded-sm bg-primary px-2.5 py-1 text-xs font-medium text-on-primary hover:bg-primary-hover"
											>Retry</button>
										{/if}
										<button
											onclick={() => handleDelete(job.id)}
											class="rounded-sm bg-red-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-red-700"
										>Delete</button>
									</div>
								{/if}
							</div>

							<!-- Row 2: ARM job link, attempts -->
							<div class="mt-0.5 flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
								{#if job.job_id}
									<a
										href="/jobs/{job.job_id}"
										data-testid="transcode-job-link"
										class="inline-flex items-center rounded-sm bg-primary/10 px-1.5 py-0.5 text-xs font-medium text-primary-text hover:bg-primary/20 dark:bg-primary/15 dark:text-primary-text-dark dark:hover:bg-primary/25"
									>Job {job.job_id}</a>
								{:else}
									<span class="inline-flex items-center rounded-sm bg-primary/10 px-1.5 py-0.5 text-xs font-medium text-gray-500 dark:bg-primary/15 dark:text-gray-400">No job</span>
								{/if}
								{#if job.attempts > 0}
									<span class="text-xs">Attempt {job.attempts}</span>
								{/if}
								{#if job.claimed_by}
									<span class="truncate font-mono text-xs text-gray-400 dark:text-gray-500">{job.claimed_by}</span>
								{/if}
							</div>

							<!-- Error message for failed tasks -->
							{#if job.status === 'failed' && job.last_error}
								<p class="mt-2 rounded-sm bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-400">
									{job.last_error}
								</p>
							{/if}

							<!-- Progress bar for queued/in_progress -->
							{#if job.status === 'queued' || job.status === 'in_progress'}
								<div class="mt-3">
									<ProgressBar value={job.progress_pct} color="bg-indigo-500" />
								</div>
							{/if}

							<!-- Timestamps -->
							<div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
								{#if job.created_at}
									<span>Queued <TimeAgo date={job.created_at} /></span>
								{/if}
								{#if job.updated_at}
									<span>Updated <TimeAgo date={job.updated_at} /></span>
								{/if}
								{#if job.status === 'done' && job.created_at && job.updated_at}
									{@const dur = formatDuration(job.created_at, job.updated_at)}
									{#if dur}
										<span class="text-green-600 dark:text-green-400">Took {dur}</span>
									{/if}
								{/if}
							</div>

							<!-- Output path for done tasks -->
							{#if job.status === 'done' && job.output_path}
								<p class="mt-2 flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
									<span class="text-gray-400 dark:text-gray-500">&rarr;</span>
									<span class="truncate font-mono" title={job.output_path}>{sourceFile}</span>
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
