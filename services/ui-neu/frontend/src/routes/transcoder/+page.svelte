<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { fade } from 'svelte/transition';
	import { fetchTranscoderStats } from '$lib/api/transcoder';
	import StatusBadge from '$lib/components/StatusBadge.svelte';
	import ProgressBar from '$lib/components/ProgressBar.svelte';
	import TimeAgo from '$lib/components/TimeAgo.svelte';
	import LoadState from '$lib/components/LoadState.svelte';
	import SkeletonCard from '$lib/components/SkeletonCard.svelte';
	import { fadeIn, fadeOut } from '$lib/transitions';
	import { formatElapsed } from '$lib/utils/format';
	import { pathBasename } from '$lib/utils/path';
	import { transcoderStats, transcoderWorkers, getJobsCache } from '$lib/stores/transcoder';
	import { GpuInventory } from '$lib/stores/gpuInventory.svelte';
	import { TranscodeJobs } from '$lib/stores/transcodeJobs.svelte';
	import { TranscodeTaskActions } from '$lib/stores/transcodeTaskActions.svelte';
	import { taskCount } from '$lib/utils/transcode-stats';
	import { isAdmin } from '$lib/stores/auth';
	import { transcoderEnabled, transcodeRuntimeEnabled } from '$lib/stores/config';
	import TranscoderUnavailable from '$lib/components/transcoder/TranscoderUnavailable.svelte';
	import TranscoderStatsSkeleton from '$lib/components/transcoder/TranscoderStatsSkeleton.svelte';
	import TranscoderOfflineBanner from '$lib/components/transcoder/TranscoderOfflineBanner.svelte';
	import WorkerPoolPanel from '$lib/components/transcoder/WorkerPoolPanel.svelte';

	// Singleton stores (see $lib/stores/transcoder) so stats/workers survive
	// navigation and don't flash the offline/empty state on every visit.
	const stats = transcoderStats;
	const statsError = stats.error;
	const statsInitialized = stats.initialized;
	const workers = transcoderWorkers;
	const transcodeJobs = new TranscodeJobs();

	let s = $derived($stats);

	const taskActions = new TranscodeTaskActions(() => transcodeJobs.load());

	// Auto-refresh jobs when any are queued or in progress.
	$effect(() => {
		if (taskCount(s, 'in_progress') > 0 || taskCount(s, 'queued') > 0) {
			transcodeJobs.startPolling();
		} else {
			transcodeJobs.stopPolling();
		}
	});

	const gpus = new GpuInventory();

	// Ripper-only: encode tasks queued before the box lost transcoding are
	// held by the backend with nothing to run them; say how many.
	let heldEncodeTasks = $state(0);

	async function loadHeldEncodeTasks() {
		try {
			heldEncodeTasks = (await fetchTranscoderStats()).queued_encode_tasks ?? 0;
		} catch {
			heldEncodeTasks = 0;
		}
	}

	onMount(() => {
		// Ripper-only deployments (transcoder not capable): the nav hides this
		// route, but the URL still resolves (deep link), so the page renders a
		// full-page empty state below and fetches only the held-task count.
		if (!get(transcoderEnabled)) {
			loadHeldEncodeTasks();
			return;
		}
		stats.start();
		workers.start();
		gpus.load();
		const stopWatchingGpus = gpus.watch();
		// Skeleton only when we have nothing cached for the current tab.
		transcodeJobs.load(getJobsCache(transcodeJobs.activeTab) == null);
		return () => {
			stopWatchingGpus();
			stats.stop();
			workers.stop();
			transcodeJobs.stopPolling();
		};
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

{#if !$transcoderEnabled}
	<!-- Ripper-only deployment: nav hides /transcoder, but the URL still
	     resolves as a deep link. Only the held-task count is fetched (see onMount). -->
	<TranscoderUnavailable heldTasks={heldEncodeTasks} />
{:else}
	<div class="stack stack-lg">
		<h1 class="page-title">Transcoder</h1>

		{#if !$transcodeRuntimeEnabled}
			<!-- Runtime-disabled (capable, but turned off in Settings > Transcoding):
		     content stays visible - drain semantics need the held queue visible. -->
			<div class="alert alert-warning" role="status" data-testid="transcode-runtime-disabled-banner">
				Transcoding is disabled. Queued tasks are held and resume when it is re-enabled.
			</div>
		{/if}

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
			<TranscoderStatsSkeleton />
		{:else if $statsError}
			<!-- Offline banner -->
			<TranscoderOfflineBanner />
		{:else}
			<!-- Worker pool + Stats cards -->
			<div in:fade={fadeIn} out:fade={fadeOut} class="stack">
				<!-- Worker pool status -->
				<WorkerPoolPanel workers={$workers} stats={s} gpus={gpus.rows} />
				<div class="grid grid-cols-2 gap-4 lg:grid-cols-5">
					<div class="stat transcoder-page-stat">
						<p class="stat-label">Queued</p>
						<p class="stat-value transcoder-page-stat-value">{taskCount(s, 'queued')}</p>
					</div>
					<div class="stat transcoder-page-stat">
						<p class="stat-label">In Progress</p>
						<p class="stat-value transcoder-page-stat-value transcoder-page-stat-value-progress">
							{taskCount(s, 'in_progress')}
						</p>
					</div>
					<div class="stat transcoder-page-stat">
						<p class="stat-label">Done</p>
						<p class="stat-value transcoder-page-stat-value transcoder-page-stat-value-success">
							{taskCount(s, 'done')}
						</p>
					</div>
					<div class="stat transcoder-page-stat">
						<p class="stat-label">Failed</p>
						<p class="stat-value transcoder-page-stat-value transcoder-page-stat-value-danger">
							{taskCount(s, 'failed')}
						</p>
					</div>
					<div class="stat transcoder-page-stat">
						<p class="stat-label">Total</p>
						<p class="stat-value transcoder-page-stat-value transcoder-page-stat-value-muted">{s.total_tasks}</p>
					</div>
				</div>
			</div>
		{/if}

		<!-- Jobs section -->
		<section class="space-y-4" data-page-section>
			<h2 class="transcoder-page-section-title" data-page-section-title>Transcode Jobs</h2>

			{#if taskActions.error}
				<div class="alert alert-danger">
					{taskActions.error}
					<button onclick={taskActions.dismiss} class="btn btn-link transcoder-page-dismiss">Dismiss</button>
				</div>
			{/if}

			<!-- Tabs -->
			<div class="tabs transcoder-page-tabs">
				{#each tabs as tab (tab)}
					<button
						onclick={() => transcodeJobs.switchTab(tab)}
						data-selected={transcodeJobs.activeTab === tab}
						class="tabs-tab transcoder-page-tab"
					>
						{TAB_LABELS[tab]}
					</button>
				{/each}
			</div>

			<!-- Jobs list -->
			<LoadState
				data={transcodeJobs.sorted}
				loading={transcodeJobs.loading}
				error={transcodeJobs.error}
				isEmpty={(d) => d.length === 0}
			>
				{#snippet loadingSlot()}
					<!-- As many placeholders as the stats poll says there are tasks (it
				     lands first), so the list does not grow when the jobs arrive. -->
					<div class="stack stack-sm">
						{#each Array(Math.min(s.total_tasks || 3, 6)) as _unused, i (i)}
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
							{@const sourceFile = pathBasename(job.output_path)}
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
													<button
														onclick={() => taskActions.retry(job.id)}
														class="btn btn-primary transcoder-page-job-action-btn">Retry</button
													>
												{/if}
												<button
													onclick={() => taskActions.remove(job.id)}
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
						{/each}
					</div>
				{/snippet}
			</LoadState>
		</section>
	</div>
{/if}

<style>
	/* the original tab strip had no overflow-x-auto and its buttons had no
	   whitespace-nowrap - at narrow widths the row itself shrinks and
	   "In Progress" wraps to two lines, rather than the strip scrolling
	   horizontally with single-line tabs */
	/* the original tab strip was gap-1 (0.25rem), not .tabs' own 1rem
	   default (tuned for the wider Settings tab strip); no overflow-x-auto
	   either, so the row shrinks and wraps rather than scrolling. Both axes
	   are reset: .tabs hides overflow-y, and a hidden y axis would turn a
	   visible x axis back into auto. */
	.transcoder-page-tabs {
		gap: 0.25rem;
		overflow: visible;
	}
	/* the original buttons were px-4 py-2 (1rem/0.5rem), not .tabs-tab's own
	   0.25rem/0.625rem default, and had no whitespace-nowrap */
	.transcoder-page-tab {
		padding: 0.5rem 1rem;
		white-space: normal;
		flex-shrink: 1;
		min-width: 0;
		text-align: center;
	}
	/* the original stat cards were text-3xl (1.875rem/2.25rem), taller than
	   stat's own 1.5rem/2rem default (tuned for StatStrip) */
	.transcoder-page-stat-value {
		font-size: 1.875rem;
		line-height: 2.25rem;
	}
	/* the original "In Progress" value used a literal indigo hue with no
	   shared token; same transcoder-domain collapse as the worker card and
	   progress-bar tone above */
	.transcoder-page-stat-value-progress {
		color: var(--color-status-transcoding);
	}
	.transcoder-page-stat-value-success {
		color: var(--color-success);
	}
	.transcoder-page-stat-value-danger {
		color: var(--color-danger);
	}
	.transcoder-page-stat-value-muted {
		color: var(--color-text-muted);
	}
	.transcoder-page-section-title {
		font-size: 1.125rem;
		line-height: 1.75rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.transcoder-page-dismiss {
		margin-left: 0.5rem;
	}
	.transcoder-page-dismiss:hover {
		opacity: 0.75;
	}
	.transcoder-page-empty {
		padding: 2rem 0;
		text-align: center;
		color: var(--color-text-faint);
	}
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
