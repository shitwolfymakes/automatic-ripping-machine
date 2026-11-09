<script lang="ts">
	import { onMount } from 'svelte';
	import { get } from 'svelte/store';
	import { fade } from 'svelte/transition';
	import { fetchTranscoderStats } from '$lib/api/transcoder';
	import LoadState from '$lib/components/LoadState.svelte';
	import SkeletonCard from '$lib/components/SkeletonCard.svelte';
	import { fadeIn, fadeOut } from '$lib/transitions';
	import { transcoderStats, transcoderWorkers, getJobsCache } from '$lib/stores/transcoder';
	import { GpuInventory } from '$lib/stores/gpuInventory.svelte';
	import { TranscodeJobs } from '$lib/stores/transcodeJobs.svelte';
	import { TranscodeTaskActions } from '$lib/stores/transcodeTaskActions.svelte';
	import { taskCount } from '$lib/utils/transcode-stats';
	import { transcoderEnabled, transcodeRuntimeEnabled } from '$lib/stores/config';
	import TranscoderUnavailable from '$lib/components/transcoder/TranscoderUnavailable.svelte';
	import TranscoderStatsSkeleton from '$lib/components/transcoder/TranscoderStatsSkeleton.svelte';
	import TranscoderOfflineBanner from '$lib/components/transcoder/TranscoderOfflineBanner.svelte';
	import WorkerPoolPanel from '$lib/components/transcoder/WorkerPoolPanel.svelte';
	import TranscoderStatTiles from '$lib/components/transcoder/TranscoderStatTiles.svelte';
	import TranscodeJobCard from '$lib/components/transcoder/TranscodeJobCard.svelte';

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
							<TranscodeJobCard {job} onretry={taskActions.retry} ondelete={taskActions.remove} />
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
</style>
