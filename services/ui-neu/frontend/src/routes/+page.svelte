<script lang="ts">
	import { onMount } from 'svelte';
	import { fetchDashboard } from '$lib/api/dashboard';
	import { fetchJobs, bulkDeleteJobs } from '$lib/api/jobs';
	import type { JobView } from '$lib/types/api.gen';
	import type { DashboardData } from '$lib/api/dashboard';
	import DiscReviewWidget from '$lib/components/DiscReviewWidget.svelte';
	import JobCard from '$lib/components/JobCard.svelte';
	import ActiveJobRow from '$lib/components/ActiveJobRow.svelte';
	import { ripProgress, startWS, stopWS, reconcileSubscriptions } from '$lib/stores/rips.svelte';
	import JobRow from '$lib/components/JobRow.svelte';
	import TranscodeCard from '$lib/components/TranscodeCard.svelte';
	import SectionFrame from '$lib/components/SectionFrame.svelte';
	import JobFilterBar from '$lib/components/JobFilterBar.svelte';
	import BulkActionsMenu from '$lib/components/BulkActionsMenu.svelte';
	import LoadState from '$lib/components/LoadState.svelte';
	import EmptyDashboardPanel from '$lib/components/EmptyDashboardPanel.svelte';
	import { fadeIn, fadeOut } from '$lib/transitions';
	import { fade } from 'svelte/transition';
	import { isAwaitingAction } from '$lib/utils/job-status';
	import { transcoderEnabled } from '$lib/stores/config';
	import { dashboard } from '$lib/stores/dashboard';
	import { get } from 'svelte/store';
	import { startRipperEvents, onRipperEvent } from '$lib/stores/ripperEvents.svelte';

	// --- Dashboard state ---
	// Seed from the persistent singleton store the layout already polls, so
	// navigating back to the dashboard paints the last-known data (transcoder
	// section, drives, etc.) immediately instead of flashing empty and popping
	// in once our own poll resolves. In tests the layout isn't mounted, so the
	// store is still its empty default — same starting point as before.
	let dash = $state<DashboardData>(get(dashboard));
	let dashLoading = $state(!get(dashboard.initialized));
	let dashError = $state<Error | null>(null);

	let dismissedJobIds = $state(new Set<string>());
	// Jobs that have entered review (awaiting_user_id/ripped_awaiting_identify).
	// Applying a metadata match promotes a job to `identified`, which would
	// otherwise drop its review card mid-review. Keep showing the card for any
	// job that was in review until the operator explicitly dismisses it.
	let stickyReviewIds = $state(new Set<string>());
	let activeJobs = $derived(dash.active_jobs ?? []);

	function isAwaiting(j: JobView): boolean {
		const s = j.status?.toLowerCase();
		// `identified` is pre-rip (disc identified, waiting to start) — it belongs
		// on the review card (with Start rip), NOT in FINISHING. Keep it here so it
		// shows the review widget even after a page reload, not only while sticky.
		return (
			s === 'awaiting_user_id' ||
			s === 'ripped_awaiting_identify' ||
			s === 'awaiting_review' ||
			s === 'identified'
		);
	}

	// Record jobs seen in review so they stick through a post-apply `identified`.
	$effect(() => {
		const toAdd = activeJobs.filter((j) => isAwaiting(j) && !stickyReviewIds.has(j.id));
		if (toAdd.length > 0) {
			stickyReviewIds = new Set([...stickyReviewIds, ...toAdd.map((j) => j.id)]);
		}
	});

	let scanningJobs = $derived(
		activeJobs.filter((j: JobView) => j.status?.toLowerCase() === 'created')
	);
	let waitingJobs = $derived(
		activeJobs.filter((j: JobView) => {
			if (dismissedJobIds.has(j.id)) return false;
			// In review while awaiting (incl. awaiting_review), sticky after an apply
			// promoted it to identified, OR post-rip awaiting a transcode session
			// (ripped/ripped_partial, no session in flight) — these come BACK as a
			// rich review card so the operator can apply a session + fix metadata.
			return (
				isAwaiting(j) ||
				(stickyReviewIds.has(j.id) && j.status?.toLowerCase() === 'identified') ||
				isAwaitingAction(j)
			);
		})
	);
	let waitingJobIds = $derived(new Set(waitingJobs.map((j) => j.id)));
	let nonWaitingActiveJobs = $derived(
		activeJobs.filter((j: JobView) => j.status?.toLowerCase() === 'ripping')
	);
	// A sticky review card that promoted to `identified` shows in Waiting, not
	// also in Finishing — exclude anything currently rendered as a review card.
	let finishingJobs = $derived(
		activeJobs.filter((j: JobView) => isAwaitingAction(j) && !waitingJobIds.has(j.id))
	);

	function dismissJob(jobId: string) {
		dismissedJobIds = new Set([...dismissedJobIds, jobId]);
		// Drop from sticky so a later poll can't re-show the card.
		if (stickyReviewIds.has(jobId)) {
			const next = new Set(stickyReviewIds);
			next.delete(jobId);
			stickyReviewIds = next;
		}
	}

	async function refreshDashboard() {
		try {
			dash = await fetchDashboard();
			dashError = null;
		} catch (e) {
			dashError = e instanceof Error ? e : new Error('Unknown error');
		} finally {
			dashLoading = false;
		}
	}

	// --- Jobs section state ---
	// v3 GET /api/jobs returns a flat JobView[] (no pagination envelope, no
	// stats, no progress endpoint). The BFF's page/per_page/search/sort and the
	// stats cards are gone.
	let jobs = $state<JobView[] | null>(null);
	let jobsError = $state<Error | null>(null);
	let jobsLoading = $state(true);
	let pageReady = $derived(!dashLoading && !jobsLoading);

	let statusFilter = $state('');
	let viewMode = $state<'card' | 'table'>('card');

	// Selection
	let selectedJobs = $state<Set<string>>(new Set());

	// Gear menu
	let bulkBusy = $state(false);
	let bulkFeedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	// Derived
	let allVisibleSelected = $derived(
		jobs !== null && jobs.length > 0 && jobs.every((j) => selectedJobs.has(j.id))
	);

	async function loadJobs() {
		if (!jobs) jobsLoading = true;
		jobsError = null;
		selectedJobs = new Set();
		try {
			jobs = await fetchJobs({ status: statusFilter || undefined });
		} catch (e) {
			jobsError = e instanceof Error ? e : new Error('Failed to load jobs');
		} finally {
			jobsLoading = false;
		}
	}

	const setStatusFilter = (v: string) => {
		statusFilter = v;
		loadJobs();
	};

	function toggleSelect(jobId: string, selected: boolean) {
		if (selected) {
			selectedJobs.add(jobId);
		} else {
			selectedJobs.delete(jobId);
		}
		selectedJobs = new Set(selectedJobs);
	}

	function toggleSelectAll() {
		if (!jobs) return;
		if (allVisibleSelected) {
			selectedJobs = new Set();
		} else {
			selectedJobs = new Set(jobs.map((j) => j.id));
		}
	}

	async function handleBulkAction(
		action: 'delete' | 'purge',
		params: { job_ids?: string[]; status?: string },
		description: string
	) {
		if (!confirm(`Are you sure you want to ${description}?`)) return;
		bulkBusy = true;
		bulkFeedback = null;
		try {
			// v3 only exposes bulk delete; purge has no endpoint and the menu
			// routes both actions here. The response reports deleted_ids plus
			// skipped_non_terminal (in-flight jobs the backend refused).
			const result = await bulkDeleteJobs(params);
			const skipped = result.skipped_non_terminal.length;
			bulkFeedback = {
				type: skipped > 0 ? 'error' : 'success',
				message:
					skipped > 0
						? `Deleted ${result.deleted_ids.length}, skipped ${skipped} in-flight job(s)`
						: `Deleted ${result.deleted_ids.length} job(s)`
			};
			await loadJobs();
		} catch (e) {
			bulkFeedback = {
				type: 'error',
				message: e instanceof Error ? e.message : 'Bulk action failed'
			};
		} finally {
			bulkBusy = false;
		}
	}

	// Sortable columns (v3 JobRow renders Title / Year / Rip / Transcode / Type / Disc).
	const columns = [
		{ key: 'title', label: 'Title' },
		{ key: 'year', label: 'Year' },
		{ key: 'status', label: 'Rip' },
		{ key: 'transcode', label: 'Transcode' },
		{ key: 'video_type', label: 'Type' },
		{ key: 'disctype', label: 'Disc' }
	];

	// Live rip-progress: open the WS once, then keep the per-job
	// `ripper.progress.{id}` subscriptions in sync with the set of jobs
	// currently ripping. The $effect re-runs whenever that set changes.
	$effect(() => {
		reconcileSubscriptions(nonWaitingActiveJobs.map((j) => j.id));
	});

	onMount(() => {
		let stopped = false;
		startWS();
		// Instant status: any ripper.events burst -> immediate refresh of both
		// surfaces (sections/cards AND the jobs table). Polls below stay as
		// reconciliation. Unregister only our listener on unmount — the topic
		// subscription is shared with the job detail page.
		startRipperEvents();
		const offRipperEvents = onRipperEvent(() => {
			refreshDashboard();
			loadJobs();
		});

		function poll(fn: () => Promise<void>, intervalMs: number) {
			(async () => {
				while (!stopped) {
					await fn();
					await new Promise((r) => setTimeout(r, intervalMs));
				}
			})();
		}

		poll(refreshDashboard, 5000);
		poll(loadJobs, 10000);
		return () => {
			stopped = true;
			offRipperEvents();
			stopWS();
		};
	});
</script>

<svelte:head>
	<title>ARM - Dashboard</title>
</svelte:head>

<div class="space-y-6">
	<div class="flex items-center justify-between">
		<h1 class="text-2xl font-bold text-gray-900 dark:text-white">Dashboard</h1>
	</div>

	<!-- Global pause banner -->
	{#if !dashLoading && !dash.ripping_enabled}
		<div class="flex items-center gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4 dark:border-amber-700 dark:bg-amber-900/20">
			<div class="h-3 w-3 shrink-0 rounded-full bg-amber-500"></div>
			<div>
				<p class="font-medium text-amber-800 dark:text-amber-300">Ripping Paused</p>
				<p class="text-sm text-amber-700 dark:text-amber-400">New discs won't start ripping while paused.</p>
			</div>
		</div>
	{/if}

	<!-- API error (backend unreachable) -->
	{#if dashError}
		<div class="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
			Failed to reach backend: {dashError.message}
		</div>
	{/if}

	<!-- Disc review (waiting jobs) -->
	{#if waitingJobs.length > 0}
		<section in:fade={fadeIn} out:fade={fadeOut}>
			<SectionFrame variant="full" accent="var(--color-primary)" label="WAITING FOR REVIEW - {waitingJobs.length} DISC{waitingJobs.length > 1 ? 'S' : ''}">
				<div class="grid gap-4">
					{#each waitingJobs as job (job.id)}
						<div in:fade|local={fadeIn} out:fade|local={fadeOut}>
							<DiscReviewWidget {job} driveNames={dash.drive_names} paused={!dash.ripping_enabled} onrefresh={refreshDashboard} ondismiss={() => dismissJob(job.id)} />
						</div>
					{/each}
				</div>
			</SectionFrame>
		</section>
	{/if}

	<!-- Scanning -->
	{#if scanningJobs.length > 0}
		<section in:fade={fadeIn} out:fade={fadeOut}>
			<SectionFrame variant="full" accent="var(--color-cyan-500, #06b6d4)" label="SCANNING - {scanningJobs.length} {scanningJobs.length === 1 ? 'DISC' : 'DISCS'}">
				<div class="space-y-2">
					{#each scanningJobs as job (job.id)}
						<div in:fade|local={fadeIn} out:fade|local={fadeOut}>
							<ActiveJobRow {job} />
						</div>
					{/each}
				</div>
			</SectionFrame>
		</section>
	{/if}

	<!-- Active rips -->
	{#if nonWaitingActiveJobs.length > 0}
		<section in:fade={fadeIn} out:fade={fadeOut}>
			<SectionFrame variant="full" accent="var(--color-primary)" label="ACTIVE RIPS - {nonWaitingActiveJobs.length} IN PROGRESS">
				<div class="space-y-2">
					{#each nonWaitingActiveJobs as job (job.id)}
						<div in:fade|local={fadeIn} out:fade|local={fadeOut}>
							<ActiveJobRow {job} progress={ripProgress.value[job.id]?.progress_pct ?? null} eta={ripProgress.value[job.id]?.eta_seconds ?? null} />
						</div>
					{/each}
				</div>
			</SectionFrame>
		</section>
	{/if}

	<!-- Finishing (identified / ripped / ripped_partial) -->
	{#if finishingJobs.length > 0}
		<section in:fade={fadeIn} out:fade={fadeOut}>
			<SectionFrame variant="full" accent="var(--color-amber-500, #f59e0b)" label="FINISHING - {finishingJobs.length} {finishingJobs.length === 1 ? 'JOB' : 'JOBS'}">
				<div class="space-y-2">
					{#each finishingJobs as job (job.id)}
						<div in:fade|local={fadeIn} out:fade|local={fadeOut}>
							<ActiveJobRow {job} />
						</div>
					{/each}
				</div>
			</SectionFrame>
		</section>
	{/if}

	<!-- Active transcodes -->
	{#if $transcoderEnabled && dash.active_transcodes.length > 0}
		<section in:fade={fadeIn} out:fade={fadeOut}>
			<SectionFrame variant="full" accent="var(--color-primary)" label="TRANSCODING - {dash.active_transcodes.length} ACTIVE">
				<div class="space-y-2">
					{#each dash.active_transcodes as tc (tc.id)}
						<div in:fade|local={fadeIn} out:fade|local={fadeOut}>
							<TranscodeCard job={tc} />
						</div>
					{/each}
				</div>
			</SectionFrame>
		</section>
	{/if}

	<!-- Idle state -->
	{#if pageReady && scanningJobs.length === 0 && waitingJobs.length === 0 && nonWaitingActiveJobs.length === 0 && finishingJobs.length === 0 && dash.active_transcodes.length === 0}
		<div in:fade={fadeIn}>
			<EmptyDashboardPanel
				drivesOnline={dash.drives_online}
				armOnline={dash.arm_online}
				transcoderOnline={dash.transcoder_online}
			/>
		</div>
	{/if}

	<!-- All Jobs -->
	<section id="all-jobs" class="space-y-4">
			<!-- Controls panel -->
			<div class="rounded-lg border border-primary/20 bg-surface shadow-xs dark:border-primary/20 dark:bg-surface-dark">
				<!-- Header: Title + View toggle + Bulk actions -->
				<div class="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
					<h2 class="text-lg font-semibold text-gray-900 dark:text-white">All Jobs</h2>
					<div class="flex items-center gap-3">
						<div class="flex gap-1">
							<button
								onclick={() => (viewMode = 'card')}
								class="rounded-md px-3 py-1.5 text-xs font-medium {viewMode === 'card' ? 'bg-primary text-on-primary' : 'bg-primary/10 text-gray-600 hover:bg-primary/15 dark:bg-primary/15 dark:text-gray-300'}"
							>Cards</button>
							<button
								onclick={() => (viewMode = 'table')}
								class="rounded-md px-3 py-1.5 text-xs font-medium {viewMode === 'table' ? 'bg-primary text-on-primary' : 'bg-primary/10 text-gray-600 hover:bg-primary/15 dark:bg-primary/15 dark:text-gray-300'}"
							>Table</button>
						</div>
						<div class="h-5 w-px bg-primary/20 dark:bg-primary/20"></div>
						<BulkActionsMenu
							{selectedJobs}
							jobsStats={null}
							{bulkBusy}
							onaction={handleBulkAction}
						/>
					</div>
				</div>

				<!-- Filters -->
				<div class="border-t border-primary/15 px-4 py-3 dark:border-primary/15">
					<JobFilterBar
						{statusFilter}
						onstatusfilter={setStatusFilter}
					/>
				</div>

				<!-- Bulk feedback banner -->
				{#if bulkFeedback}
					<div class="border-t border-primary/15 px-4 py-3 text-sm dark:border-primary/15 {bulkFeedback.type === 'success' ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'}">
						{bulkFeedback.message}
						<button onclick={() => (bulkFeedback = null)} class="ml-2 font-bold opacity-60 hover:opacity-100">&times;</button>
					</div>
				{/if}
			</div>

			<div style="min-height: 60vh;">
			<LoadState
				data={jobs}
				loading={jobsLoading}
				error={jobsError}
				transitionKey="dashboard-recent-jobs"
			>
				{#snippet loadingSlot()}
					{#if viewMode === 'table'}
						<div class="overflow-x-auto rounded-lg border border-primary/20 dark:border-primary/20">
							<table class="responsive-table w-full text-left text-sm">
								<thead class="bg-page text-gray-600 dark:bg-primary/5 dark:text-gray-400">
									<tr>
										<th class="px-4 py-3 w-8"></th>
										{#each columns as col}
											<th class="px-4 py-3 font-medium">{col.label}</th>
										{/each}
									</tr>
								</thead>
								<tbody class="divide-y divide-gray-200 dark:divide-gray-700">
									{#each { length: 25 } as _}
										<JobRow />
									{/each}
								</tbody>
							</table>
						</div>
					{:else}
						<div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
							{#each { length: 6 } as _}
								<JobCard />
							{/each}
						</div>
					{/if}
				{/snippet}
				{#snippet ready(list)}
					{#if viewMode === 'table'}
						<div class="overflow-x-auto rounded-lg border border-primary/20 dark:border-primary/20">
							<table class="responsive-table w-full text-left text-sm">
								<thead class="bg-page text-gray-600 dark:bg-primary/5 dark:text-gray-400">
									<tr>
										<th class="px-4 py-3 w-8">
											<input
												type="checkbox"
												checked={allVisibleSelected}
												onchange={toggleSelectAll}
												class="h-4 w-4 rounded border-gray-300 text-primary focus:ring-primary dark:border-gray-600 dark:bg-gray-700"
											/>
										</th>
										{#each columns as col}
											<th class="px-4 py-3 font-medium">{col.label}</th>
										{/each}
									</tr>
								</thead>
								<tbody class="divide-y divide-gray-200 dark:divide-gray-700">
									{#each list as job (job.id)}
										<JobRow
											{job}
											selected={selectedJobs.has(job.id)}
											onselect={toggleSelect}
										/>
									{/each}
								</tbody>
							</table>
						</div>
					{:else}
						<div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
							{#each list as job (job.id)}
								<JobCard {job} />
							{/each}
						</div>
					{/if}
				{/snippet}
				{#snippet empty()}
					<p class="py-8 text-center text-gray-400">No jobs found.</p>
				{/snippet}
			</LoadState>
			</div>
	</section>
</div>
