<script lang="ts">
	import SetupChecklistCard from '$lib/components/setup/SetupChecklistCard.svelte';
	import { onMount } from 'svelte';
	import { fetchDashboard } from '$lib/api/dashboard';
	import { bulkDeleteJobs } from '$lib/api/jobs';
	import { DashboardJobs } from '$lib/stores/dashboardJobs.svelte';
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
	import { groupActiveJobs } from '$lib/utils/dashboard-groups';
	import { isoSourceFor, isoKindFor } from '$lib/utils/iso-source';
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
	let activeJobs = $derived(dash.active_jobs ?? []);

	let preparingRips = $derived(dash.preparing ?? []);
	const groups = $derived(groupActiveJobs(activeJobs, dismissedJobIds));
	let scanningJobs = $derived(groups.scanning);
	let waitingJobs = $derived(groups.waiting);
	let nonWaitingActiveJobs = $derived(groups.ripping);
	let finishingJobs = $derived(groups.finishing);

	function dismissJob(jobId: string) {
		dismissedJobIds = new Set([...dismissedJobIds, jobId]);
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
	const jobsList = new DashboardJobs();
	let pageReady = $derived(!dashLoading && !jobsList.loading);

	// Opens with the Settings > Interface default; toggling here is for this
	// visit only and does not change that default.
	let viewMode = $state<'card' | 'table'>(get(uiPrefs).dashboardView);

	// Gear menu
	let bulkBusy = $state(false);
	let bulkFeedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);

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
			jobsList.selected.clear();
			await jobsList.load();
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
		const ids = [...jobsList.selected];
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
			jobsList.load();
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
		poll(jobsList.load, 10000);
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
				<div class="grid grid-cols-1 gap-4">
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
								isoSource={isoSourceFor(job.drive_id, dash.iso_sources)}
								isoKind={isoKindFor(job.drive_id, dash.iso_source_kinds)}
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
								isoSource={isoSourceFor(job.drive_id, dash.iso_sources)}
								isoKind={isoKindFor(job.drive_id, dash.iso_source_kinds)}
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
			<span class="list-panel-count">{jobsList.total} {jobsList.total === 1 ? 'job' : 'jobs'}</span>
			<JobFilterBar statusFilter={jobsList.statusFilter} onstatusfilter={jobsList.setStatusFilter} />
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
				<BulkActionsMenu selectedJobs={jobsList.selected} {bulkBusy} onaction={handleBulkAction} />
			{/if}
		</div>

		{#if $isAdmin && jobsList.selected.size > 0}
			<div class="dashboard-jobs-selection" data-testid="jobs-selection-bar" transition:slide={{ duration: 120 }}>
				<span class="dashboard-jobs-selection-count">{jobsList.selected.size} selected</span>
				<span class="dashboard-jobs-selection-divider"></span>
				<button onclick={deleteSelected} disabled={bulkBusy} class="btn btn-sm btn-danger">Delete selected</button>
				<span class="flex-1"></span>
				<button onclick={() => jobsList.selected.clear()} class="btn btn-link dashboard-jobs-selection-clear"
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
			<LoadState
				data={jobsList.jobs}
				loading={jobsList.loading}
				error={jobsList.error}
				transitionKey="dashboard-recent-jobs"
			>
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
													checked={jobsList.allVisibleSelected}
													onchange={jobsList.toggleSelectAll}
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
										<JobRow
											{job}
											selected={jobsList.selected.has(job.id)}
											onselect={jobsList.toggleSelect}
											showSelect={$isAdmin}
										/>
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
			<JobPagination
				page={jobsList.page}
				pages={jobsList.pages}
				perPage={jobsList.perPage}
				total={jobsList.total}
				onpage={jobsList.setPage}
			/>
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
