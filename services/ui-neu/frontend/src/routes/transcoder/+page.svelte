<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { fade } from 'svelte/transition';
	import { fetchTranscoderStats } from '$lib/api/transcoder';
	import { fadeIn, fadeOut } from '$lib/transitions';
	import { transcoderStats, transcoderWorkers, getJobsCache } from '$lib/stores/transcoder';
	import { GpuInventory } from '$lib/stores/gpu-inventory.svelte';
	import { TranscodeJobs } from '$lib/stores/transcode-jobs.svelte';
	import { TranscodeTaskActions } from '$lib/stores/transcode-task-actions.svelte';
	import { taskCount } from '$lib/transcode/stats';
	import { transcoderEnabled, transcodeRuntimeEnabled } from '$lib/stores/config';
	import TranscoderUnavailable from '$lib/components/transcoder/TranscoderUnavailable.svelte';
	import TranscoderStatsSkeleton from '$lib/components/transcoder/TranscoderStatsSkeleton.svelte';
	import TranscoderOfflineBanner from '$lib/components/transcoder/TranscoderOfflineBanner.svelte';
	import WorkerPoolPanel from '$lib/components/transcoder/WorkerPoolPanel.svelte';
	import TranscoderStatTiles from '$lib/components/transcoder/TranscoderStatTiles.svelte';
	import TranscodeJobList from '$lib/components/transcoder/TranscodeJobList.svelte';
	import TranscodeJobTabs from '$lib/components/transcoder/TranscodeJobTabs.svelte';

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
				<TranscoderStatTiles stats={s} />
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
			<TranscodeJobTabs active={transcodeJobs.activeTab} onselect={transcodeJobs.switchTab} />

			<!-- Jobs list -->
			<TranscodeJobList
				jobs={transcodeJobs.sorted}
				loading={transcodeJobs.loading}
				error={transcodeJobs.error}
				totalTasks={s.total_tasks}
				onretry={taskActions.retry}
				ondelete={taskActions.remove}
			/>
		</section>
	</div>
{/if}

<style>
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
</style>
