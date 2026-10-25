<script lang="ts">
	import SetupChecklistCard from '$lib/components/setup/SetupChecklistCard.svelte';
	import { onMount } from 'svelte';
	import { SvelteSet } from 'svelte/reactivity';
	import { fetchDashboard } from '$lib/api/dashboard';
	import { fetchJobsPage, bulkDeleteJobs } from '$lib/api/jobs';
	import type { JobView } from '$lib/types/api.gen';
	import type { DashboardData } from '$lib/api/dashboard';
	import DiscReviewWidget from '$lib/components/DiscReviewWidget.svelte';
	import JobCard from '$lib/components/JobCard.svelte';
	import ActiveJobRow from '$lib/components/ActiveJobRow.svelte';
	import IsoPreparingRow from '$lib/components/IsoPreparingRow.svelte';
	import { ripProgress, startWS, stopWS, reconcileSubscriptions } from '$lib/stores/rips.svelte';
	import JobRow from '$lib/components/JobRow.svelte';
	import TranscodeCard from '$lib/components/TranscodeCard.svelte';
	import SectionFrame from '$lib/components/SectionFrame.svelte';
	import JobFilterBar from '$lib/components/JobFilterBar.svelte';
	import BulkActionsMenu from '$lib/components/BulkActionsMenu.svelte';
	import JobPagination from '$lib/components/JobPagination.svelte';
	import CloseButton from '$lib/components/CloseButton.svelte';
	import LoadState from '$lib/components/LoadState.svelte';
	import EmptyDashboardPanel from '$lib/components/EmptyDashboardPanel.svelte';
	import { fadeIn, fadeOut } from '$lib/transitions';
	import { fade, slide } from 'svelte/transition';
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
			s === 'awaiting_user_id' || s === 'ripped_awaiting_identify' || s === 'awaiting_review' || s === 'identified'
		);
	}

	// Record jobs seen in review so they stick through a post-apply `identified`.
	$effect(() => {
		const toAdd = activeJobs.filter((j) => isAwaiting(j) && !stickyReviewIds.has(j.id));
		if (toAdd.length > 0) {
			stickyReviewIds = new Set([...stickyReviewIds, ...toAdd.map((j) => j.id)]);
		}
	});

	let preparingRips = $derived(dash.preparing ?? []);
	let scanningJobs = $derived(activeJobs.filter((j: JobView) => j.status?.toLowerCase() === 'created'));
	let waitingJobs = $derived(
		activeJobs.filter((j: JobView) => {
			if (dismissedJobIds.has(j.id)) return false;
			// In review while awaiting (incl. awaiting_review), sticky after an apply
			// promoted it to identified, OR post-rip awaiting a transcode session
			// (ripped/ripped_partial, no session in flight) — these come BACK as a
			// rich review card so the operator can apply a session + fix metadata.
			return (
				isAwaiting(j) || (stickyReviewIds.has(j.id) && j.status?.toLowerCase() === 'identified') || isAwaitingAction(j)
			);
		})
	);
	let waitingJobIds = $derived(new Set(waitingJobs.map((j) => j.id)));
	let nonWaitingActiveJobs = $derived(activeJobs.filter((j: JobView) => j.status?.toLowerCase() === 'ripping'));
	// A sticky review card that promoted to `identified` shows in Waiting, not
	// also in Finishing — exclude anything currently rendered as a review card.
	let finishingJobs = $derived(activeJobs.filter((j: JobView) => isAwaitingAction(j) && !waitingJobIds.has(j.id)));

	function dismissJob(jobId: string) {
		dismissedJobIds = new Set([...dismissedJobIds, jobId]);
		// Drop from sticky so a later poll can't re-show the card.
		if (stickyReviewIds.has(jobId)) {
			// eslint-disable-next-line svelte/prefer-svelte-reactivity -- copy-on-write; reassigning the $state variable triggers updates
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
	// GET /api/jobs pages server-side: the body is one page of JobView[] and
	// the filtered total rides in X-Total-Count. 48 per page fills the card
	// grid evenly at both two and three columns.
	let jobs = $state<JobView[] | null>(null);
	let total = $state(0);
	let page = $state(1);
	const perPage = 48;
	let pages = $derived(Math.max(1, Math.ceil(total / perPage)));
	let jobsError = $state<Error | null>(null);
	let jobsLoading = $state(true);
	let pageReady = $derived(!dashLoading && !jobsLoading);

	let statusFilter = $state('');
	// Opens with the Settings > Interface default; toggling here is for this
	// visit only and does not change that default.
	let viewMode = $state<'card' | 'table'>(get(uiPrefs).dashboardView);

	// Selection
	const selectedJobs = new SvelteSet<string>();

	// Gear menu
	let bulkBusy = $state(false);
	let bulkFeedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

	// Derived
	let allVisibleSelected = $derived(jobs !== null && jobs.length > 0 && jobs.every((j) => selectedJobs.has(j.id)));

	// Reloads the current page only (the poll and ripper events call this too).
	// Calls overlap (poll, events, paging), so only the latest request's
	// response is applied; an earlier, slower one is dropped.
	let jobsRequest = 0;
	async function loadJobs() {
		const request = ++jobsRequest;
		if (!jobs) jobsLoading = true;
		jobsError = null;
		try {
			const result = await fetchJobsPage({
				status: statusFilter || undefined,
				limit: perPage,
				offset: (page - 1) * perPage
			});
			if (request !== jobsRequest) return;
			jobs = result.jobs;
			total = result.total;
			// A delete (here or elsewhere) can empty the page we are on: step
			// back to the last page that still has rows.
			if (jobs.length === 0 && page > 1 && total > 0) {
				page = Math.max(1, Math.ceil(total / perPage));
				return loadJobs();
			}
			// Selection only ever covers rows on the visible page.
			for (const id of [...selectedJobs]) {
				if (!jobs.some((j) => j.id === id)) selectedJobs.delete(id);
			}
		} catch (e) {
			if (request !== jobsRequest) return;
			jobsError = e instanceof Error ? e : new Error('Failed to load jobs');
		} finally {
			if (request === jobsRequest) jobsLoading = false;
		}
	}

	const setStatusFilter = (v: string) => {
		statusFilter = v;
		page = 1;
		selectedJobs.clear();
		loadJobs();
	};

	const setPage = (p: number) => {
		page = p;
		selectedJobs.clear();
		loadJobs();
	};

	function toggleSelect(jobId: string, selected: boolean) {
		if (selected) {
			selectedJobs.add(jobId);
		} else {
			selectedJobs.delete(jobId);
		}
	}

	function toggleSelectAll() {
		if (!jobs) return;
		const selectAll = !allVisibleSelected;
		selectedJobs.clear();
		if (selectAll) {
			for (const j of jobs) selectedJobs.add(j.id);
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
			selectedJobs.clear();
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

	function deleteSelected() {
		const ids = [...selectedJobs];
		handleBulkAction('delete', { job_ids: ids }, `delete ${ids.length} selected job(s)`);
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
	<div class="flex flex-wrap items-center justify-between gap-3">
		<h1 class="page-title">Dashboard</h1>
		<SetupChecklistCard />
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
			<SectionFrame
				variant="full"
				accent="var(--color-primary)"
				emphasis
				label="WAITING FOR REVIEW - {waitingJobs.length} DISC{waitingJobs.length > 1 ? 'S' : ''}"
			>
				<div class="grid gap-4">
					{#each waitingJobs as job (job.id)}
						<div in:fade|local={fadeIn} out:fade|local={fadeOut}>
							<DiscReviewWidget
								{job}
								driveNames={dash.drive_names}
								isoSources={dash.iso_sources}
								isoSourceKinds={dash.iso_source_kinds}
								paused={!dash.ripping_enabled}
								onrefresh={refreshDashboard}
								ondismiss={() => dismissJob(job.id)}
							/>
						</div>
					{/each}
				</div>
			</SectionFrame>
		</section>
	{/if}

	<!-- Preparing: ISO rips scanning / unpacking their image, no job yet -->
	{#if preparingRips.length > 0}
		<section in:fade={fadeIn} out:fade={fadeOut}>
			<SectionFrame
				variant="full"
				accent="var(--color-accent-4)"
				label="PREPARING - {preparingRips.length} {preparingRips.length === 1 ? 'ISO' : 'ISOS'}"
			>
				<div class="space-y-2">
					{#each preparingRips as prepare (prepare.drive_id)}
						<div in:fade|local={fadeIn} out:fade|local={fadeOut}>
							<IsoPreparingRow {prepare} />
						</div>
					{/each}
				</div>
			</SectionFrame>
		</section>
	{/if}

	<!-- Scanning -->
	{#if scanningJobs.length > 0}
		<section in:fade={fadeIn} out:fade={fadeOut}>
			<SectionFrame
				variant="full"
				accent="var(--color-accent-4)"
				label="SCANNING - {scanningJobs.length} {scanningJobs.length === 1 ? 'DISC' : 'DISCS'}"
			>
				<div class="space-y-2">
					{#each scanningJobs as job (job.id)}
						<div in:fade|local={fadeIn} out:fade|local={fadeOut}>
							<ActiveJobRow
								{job}
								isoSource={job.drive_id ? (dash.iso_sources?.[job.drive_id] ?? null) : null}
								isoKind={job.drive_id ? (dash.iso_source_kinds?.[job.drive_id] ?? 'iso') : 'iso'}
							/>
						</div>
					{/each}
				</div>
			</SectionFrame>
		</section>
	{/if}

	<!-- Active rips -->
	{#if nonWaitingActiveJobs.length > 0}
		<section in:fade={fadeIn} out:fade={fadeOut}>
			<SectionFrame
				variant="full"
				accent="var(--color-primary)"
				label="ACTIVE RIPS - {nonWaitingActiveJobs.length} IN PROGRESS"
			>
				<div class="space-y-2">
					{#each nonWaitingActiveJobs as job (job.id)}
						<div in:fade|local={fadeIn} out:fade|local={fadeOut}>
							<ActiveJobRow
								{job}
								progress={ripProgress.value[job.id]?.progress_pct ?? null}
								eta={ripProgress.value[job.id]?.eta_seconds ?? null}
								live={ripProgress.value[job.id] ?? null}
								isoSource={job.drive_id ? (dash.iso_sources?.[job.drive_id] ?? null) : null}
								isoKind={job.drive_id ? (dash.iso_source_kinds?.[job.drive_id] ?? 'iso') : 'iso'}
							/>
						</div>
					{/each}
				</div>
			</SectionFrame>
		</section>
	{/if}

	<!-- Finishing (identified / ripped / ripped_partial) -->
	{#if finishingJobs.length > 0}
		<section in:fade={fadeIn} out:fade={fadeOut}>
			<SectionFrame
				variant="full"
				accent="var(--color-accent-1)"
				label="FINISHING - {finishingJobs.length} {finishingJobs.length === 1 ? 'JOB' : 'JOBS'}"
			>
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
			<SectionFrame
				variant="full"
				accent="var(--color-primary)"
				label="TRANSCODING - {dash.active_transcodes.length} ACTIVE"
			>
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
	{#if pageReady && preparingRips.length === 0 && scanningJobs.length === 0 && waitingJobs.length === 0 && nonWaitingActiveJobs.length === 0 && finishingJobs.length === 0 && dash.active_transcodes.length === 0}
		<div in:fade={fadeIn}>
			<EmptyDashboardPanel
				drivesOnline={dash.drives_online}
				armOnline={dash.arm_online}
				transcoderOnline={dash.transcoder_online}
			/>
		</div>
	{/if}

	<!-- All Jobs: one panel (header, selection bar, list, footer). Plain divs
	     inside, not header/footer/.panel: the winamp-97 scheme styles those
	     as the app titlebar and would rebuild the old two-row layout. -->
	<section id="all-jobs" class="list-panel">
		<div class="list-panel-header">
			<h2 class="list-panel-title">All Jobs</h2>
			<span class="list-panel-count">{total} {total === 1 ? 'job' : 'jobs'}</span>
			<JobFilterBar {statusFilter} onstatusfilter={setStatusFilter} />
			<span class="flex-1"></span>
			<div class="dashboard-view-group">
				<button
					onclick={() => (viewMode = 'card')}
					class="btn btn-sm dashboard-view-toggle"
					aria-pressed={viewMode === 'card'}>Cards</button
				>
				<button
					onclick={() => (viewMode = 'table')}
					class="btn btn-sm dashboard-view-toggle"
					aria-pressed={viewMode === 'table'}>Table</button
				>
			</div>
			{#if $isAdmin}
				<BulkActionsMenu {selectedJobs} {bulkBusy} onaction={handleBulkAction} />
			{/if}
		</div>

		{#if $isAdmin && selectedJobs.size > 0}
			<div class="dashboard-jobs-selection" data-testid="jobs-selection-bar" transition:slide={{ duration: 120 }}>
				<span class="dashboard-jobs-selection-count">{selectedJobs.size} selected</span>
				<span class="dashboard-jobs-selection-divider"></span>
				<button onclick={deleteSelected} disabled={bulkBusy} class="btn btn-sm btn-danger">Delete selected</button>
				<span class="flex-1"></span>
				<button onclick={() => selectedJobs.clear()} class="btn btn-link dashboard-jobs-selection-clear"
					>Clear selection</button
				>
			</div>
		{/if}

		{#if bulkFeedback}
			<div class="dashboard-jobs-feedback" data-tone={bulkFeedback.type}>
				<span>{bulkFeedback.message}</span>
				<CloseButton onclick={() => (bulkFeedback = null)} label="Dismiss" />
			</div>
		{/if}

		<div class="list-panel-body">
			<LoadState data={jobs} loading={jobsLoading} error={jobsError} transitionKey="dashboard-recent-jobs">
				{#snippet loadingSlot()}
					{#if viewMode === 'table'}
						<div class="overflow-x-auto">
							<table class="table responsive-table">
								<thead>
									<tr>
										<th class="table-header w-8"></th>
										{#each columns as col (col.key)}
											<th class="table-header">{col.label}</th>
										{/each}
									</tr>
								</thead>
								<tbody>
									{#each { length: 12 } as _, i (i)}
										<JobRow />
									{/each}
								</tbody>
							</table>
						</div>
					{:else}
						<div class="dashboard-jobs-grid grid md:grid-cols-2 xl:grid-cols-3">
							{#each { length: 6 } as _, i (i)}
								<JobCard />
							{/each}
						</div>
					{/if}
				{/snippet}
				{#snippet ready(list)}
					{#if viewMode === 'table'}
						<div class="overflow-x-auto">
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
										{#each columns as col (col.key)}
											<th class="table-header">{col.label}</th>
										{/each}
									</tr>
								</thead>
								<tbody>
									{#each list as job (job.id)}
										<JobRow {job} selected={selectedJobs.has(job.id)} onselect={toggleSelect} showSelect={$isAdmin} />
									{/each}
								</tbody>
							</table>
						</div>
					{:else}
						<div class="dashboard-jobs-grid grid md:grid-cols-2 xl:grid-cols-3">
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

		<div class="dashboard-jobs-footer">
			<JobPagination {page} {pages} {perPage} {total} onpage={setPage} />
		</div>
	</section>
</div>

<style>
	.dashboard-pause-banner {
		padding: 1rem;
	}
	.dashboard-pause-dot {
		height: 0.75rem;
		width: 0.75rem;
		flex-shrink: 0;
		border-radius: 9999px;
		background: var(--color-warning);
	}
	/* Cards / Table: one tinted track, the active view filled in primary */
	.dashboard-view-group {
		display: flex;
		gap: 2px;
		padding: 3px;
		border-radius: var(--radius-md);
		background: color-mix(in srgb, var(--color-primary) 8%, transparent);
	}
	.dashboard-view-toggle {
		border-color: transparent;
		border-radius: calc(var(--radius-md) * 0.75);
		padding: 0.3125rem 0.75rem;
		color: var(--color-text-secondary);
	}
	.dashboard-view-toggle:hover {
		background: var(--color-primary-tint-2);
	}
	.dashboard-view-toggle[aria-pressed='true'] {
		background: var(--color-primary);
		color: var(--color-on-primary);
	}
	.dashboard-jobs-selection {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.75rem;
		padding: 0.5rem 1rem;
		border-top: 1px solid color-mix(in srgb, var(--color-primary) 30%, transparent);
		background: color-mix(in srgb, var(--color-primary) 12%, var(--color-surface));
	}
	.dashboard-jobs-selection-count {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--color-primary-text);
	}
	.dashboard-jobs-selection-divider {
		width: 1px;
		height: 18px;
		background: color-mix(in srgb, var(--color-primary) 30%, transparent);
	}
	.dashboard-jobs-selection-clear {
		font-size: 0.8125rem;
	}
	.dashboard-jobs-feedback {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		padding: 0.375rem 0.5rem 0.375rem 1rem;
		border-top: 1px solid var(--color-border);
		font-size: 0.875rem;
		line-height: 1.25rem;
	}
	.dashboard-jobs-feedback[data-tone='success'] {
		color: var(--color-success);
	}
	.dashboard-jobs-feedback[data-tone='error'] {
		color: var(--color-danger);
	}
	.dashboard-jobs-grid {
		padding: 0.75rem;
		gap: 0.75rem;
	}
	.dashboard-jobs-footer {
		padding: 0.625rem 1rem;
		border-top: 1px solid var(--color-border);
	}
	.dashboard-select-all-checkbox {
		width: 1rem;
		height: 1rem;
		border-radius: var(--radius-sm);
		accent-color: var(--color-primary);
	}
	.dashboard-empty-jobs {
		padding: 2rem 0;
		text-align: center;
		color: var(--color-text-faint);
	}
</style>
