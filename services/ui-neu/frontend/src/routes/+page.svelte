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
	import { uiPrefs } from '$lib/stores/uiPrefs';
	import { startRipperEvents, onRipperEvent } from '$lib/stores/ripperEvents.svelte';
	import { isAdmin } from '$lib/stores/auth';

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
	// Opens with the Settings > Interface default; toggling here is for this
	// visit only and does not change that default.
	let viewMode = $state<'card' | 'table'>(get(uiPrefs).dashboardView);

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

<div class="stack-lg stack">
	<div class="flex items-center justify-between">
		<h1 class="page-title">Dashboard</h1>
	</div>

	<!-- Global pause banner -->
	{#if !dashLoading && !dash.ripping_enabled}
		<div class="alert alert-warning flex items-center gap-3 dashboard-pause-banner">
			<div class="dashboard-pause-dot"></div>
			<div>
				<p class="alert-title">Ripping Paused</p>
				<p class="alert-body">New discs won't start ripping while paused.</p>
			</div>
		</div>
	{/if}

	<!-- API error (backend unreachable) -->
	{#if dashError}
		<div class="alert alert-danger">
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
			<SectionFrame variant="full" accent="var(--color-accent-4)" label="SCANNING - {scanningJobs.length} {scanningJobs.length === 1 ? 'DISC' : 'DISCS'}">
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
			<SectionFrame variant="full" accent="var(--color-accent-1)" label="FINISHING - {finishingJobs.length} {finishingJobs.length === 1 ? 'JOB' : 'JOBS'}">
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
	<section id="all-jobs" class="stack">
			<!-- Controls panel -->
			<div class="dashboard-jobs-panel">
				<!-- Header: Title + View toggle + Bulk actions -->
				<div class="flex flex-wrap items-center justify-between gap-3 dashboard-jobs-header">
					<h2 class="dashboard-jobs-title">All Jobs</h2>
					<div class="flex items-center gap-3">
						<div class="flex gap-1">
							<button
								onclick={() => (viewMode = 'card')}
								class="dashboard-view-toggle"
								aria-pressed={viewMode === 'card'}
							>Cards</button>
							<button
								onclick={() => (viewMode = 'table')}
								class="dashboard-view-toggle"
								aria-pressed={viewMode === 'table'}
							>Table</button>
						</div>
						{#if $isAdmin}
							<div class="dashboard-jobs-divider"></div>
							<BulkActionsMenu
								{selectedJobs}
								jobsStats={null}
								{bulkBusy}
								onaction={handleBulkAction}
							/>
						{/if}
					</div>
				</div>

				<!-- Filters -->
				<div class="dashboard-jobs-section">
					<JobFilterBar
						{statusFilter}
						onstatusfilter={setStatusFilter}
					/>
				</div>

				<!-- Bulk feedback banner -->
				{#if bulkFeedback}
					<div class="dashboard-jobs-section dashboard-bulk-feedback" data-tone={bulkFeedback.type}>
						{bulkFeedback.message}
						<button onclick={() => (bulkFeedback = null)} class="dashboard-bulk-dismiss">&times;</button>
					</div>
				{/if}
			</div>

			<div class="dashboard-jobs-body">
			<LoadState
				data={jobs}
				loading={jobsLoading}
				error={jobsError}
				transitionKey="dashboard-recent-jobs"
			>
				{#snippet loadingSlot()}
					{#if viewMode === 'table'}
						<div class="overflow-x-auto dashboard-table-scroll">
							<table class="table responsive-table">
								<thead>
									<tr>
										<th class="table-header w-8"></th>
										{#each columns as col}
											<th class="table-header">{col.label}</th>
										{/each}
									</tr>
								</thead>
								<tbody>
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
						<div class="overflow-x-auto dashboard-table-scroll">
							<table class="table responsive-table">
								<thead>
									<tr>
										<th class="table-header w-8">
											{#if $isAdmin}
												<input
													type="checkbox"
													checked={allVisibleSelected}
													onchange={toggleSelectAll}
													class="dashboard-select-all-checkbox"
												/>
											{/if}
										</th>
										{#each columns as col}
											<th class="table-header">{col.label}</th>
										{/each}
									</tr>
								</thead>
								<tbody>
									{#each list as job (job.id)}
										<JobRow
											{job}
											selected={selectedJobs.has(job.id)}
											onselect={toggleSelect}
											showSelect={$isAdmin}
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
					<p class="dashboard-empty-jobs">No jobs found.</p>
				{/snippet}
			</LoadState>
			</div>
	</section>
</div>

<style>
	.dashboard-pause-banner { padding: 1rem; }
	.dashboard-pause-dot { height: 0.75rem; width: 0.75rem; flex-shrink: 0; border-radius: 9999px; background: var(--color-warning); }
	.dashboard-jobs-panel { border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); box-shadow: var(--shadow-1); }
	.dashboard-jobs-header { padding: 0.75rem 1rem; }
	.dashboard-jobs-title { font-size: 1.125rem; line-height: 1.75rem; font-weight: 600; color: var(--color-text); }
	.dashboard-view-toggle { border-radius: var(--radius-md); padding: 0.375rem 0.75rem; font-size: 0.75rem; line-height: 1rem; font-weight: 500; color: var(--color-text-secondary); background: var(--color-primary-tint-2); transition: background-color var(--motion-fast) var(--ease); }
	.dashboard-view-toggle:hover { background: var(--color-primary-tint-3); }
	.dashboard-view-toggle[aria-pressed="true"] { background: var(--color-primary); color: var(--color-on-primary); }
	.dashboard-jobs-divider { height: 1.25rem; width: 1px; background: var(--color-border); }
	.dashboard-jobs-section { border-top: 1px solid var(--color-border); padding: 0.75rem 1rem; }
	.dashboard-bulk-feedback { font-size: 0.875rem; line-height: 1.25rem; }
	.dashboard-bulk-feedback[data-tone="success"] { color: var(--color-success); }
	.dashboard-bulk-feedback[data-tone="error"] { color: var(--color-danger); }
	.dashboard-bulk-dismiss { margin-left: 0.5rem; font-weight: 700; opacity: 0.6; }
	.dashboard-bulk-dismiss:hover { opacity: 1; }
	.dashboard-jobs-body { min-height: 60vh; }
	.dashboard-table-scroll { border: 1px solid var(--color-border); border-radius: var(--radius-lg); }
	.dashboard-select-all-checkbox { width: 1rem; height: 1rem; border-radius: var(--radius-sm); accent-color: var(--color-primary); }
	.dashboard-empty-jobs { padding: 2rem 0; text-align: center; color: var(--color-text-faint); }
</style>
