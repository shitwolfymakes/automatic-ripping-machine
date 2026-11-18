<script lang="ts">
	import { plural } from '$lib/utils/plural';
	import SetupChecklistCard from '$lib/components/setup/SetupChecklistCard.svelte';
	import { onMount } from 'svelte';
	import { DashboardJobs } from '$lib/stores/dashboard-jobs.svelte';
	import DiscReviewWidget from '$lib/components/dashboard/DiscReviewWidget.svelte';
	import ActiveJobRow from '$lib/components/dashboard/ActiveJobRow.svelte';
	import IsoPreparingRow from '$lib/components/dashboard/IsoPreparingRow.svelte';
	import { wsClient } from '$lib/api/ws';
	import TranscodeCard from '$lib/components/dashboard/TranscodeCard.svelte';
	import DashboardSection from '$lib/components/dashboard/DashboardSection.svelte';
	import AllJobsPanel from '$lib/components/dashboard/AllJobsPanel.svelte';
	import EmptyDashboardPanel from '$lib/components/dashboard/EmptyDashboardPanel.svelte';
	import { fadeIn } from '$lib/ui/transitions';
	import { fade } from 'svelte/transition';
	import { groupActiveJobs } from '$lib/dashboard/groups';
	import { driveSummary } from '$lib/drives/summary';
	import { transcoderEnabled } from '$lib/stores/config';
	import { dashboard } from '$lib/stores/dashboard';
	import { startRipperEvents, onRipperEvent } from '$lib/stores/ripper-events.svelte';

	// --- Dashboard state ---
	// The page reads the dashboard store the layout already polls every 5 s,
	// so it shows the same data as the header (the Paused banner follows the
	// header switch at once) and does not fetch the same endpoints a second
	// time. Navigating back paints the last-known data straight away.
	const dashInitialized = dashboard.initialized;
	const dashError = dashboard.error;
	const dash = $derived($dashboard);
	// Loading until the first read lands or fails.
	const dashLoading = $derived(!$dashInitialized && $dashError === null);

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

	// A card's action or a ripper event: fetch now rather than at the next tick.
	const refreshDashboard = () => dashboard.refresh();

	// --- Jobs section state ---
	const jobsList = new DashboardJobs();
	let pageReady = $derived(!dashLoading && !jobsList.loading);

	onMount(() => {
		let stopped = false;
		wsClient.start();
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

		// The store polls on its own; fetch once now so arriving here is fresh
		// (unless the layout's first fetch is still running).
		dashboard.refreshIfIdle();
		poll(jobsList.load, 10000);
		return () => {
			stopped = true;
			offRipperEvents();
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
	{#if $dashError}
		<div class="alert alert-danger">
			Failed to reach backend: {$dashError}
		</div>
	{/if}

	<!-- Disc review (waiting jobs) -->
	<DashboardSection
		items={waitingJobs}
		key={(job) => job.id}
		accent="var(--color-primary)"
		emphasis
		listClass="grid grid-cols-1 gap-4"
		label="WAITING FOR REVIEW - {waitingJobs.length} DISC{waitingJobs.length > 1 ? 'S' : ''}"
	>
		{#snippet row(job)}
			<DiscReviewWidget
				{job}
				drive={driveSummary(dash.drives, job.drive_id)}
				paused={!dash.ripping_enabled}
				manualWaitSeconds={dash.review_wait_seconds}
				onrefresh={refreshDashboard}
				ondismiss={() => dismissJob(job.id)}
			/>
		{/snippet}
	</DashboardSection>

	<!-- Preparing: ISO rips scanning / unpacking their image, no job yet -->
	<DashboardSection
		items={preparingRips}
		key={(prepare) => prepare.drive_id}
		accent="var(--color-accent-4)"
		label="PREPARING - {preparingRips.length} {plural(preparingRips.length, 'ISO', 'ISOS')}"
	>
		{#snippet row(prepare)}
			<IsoPreparingRow {prepare} />
		{/snippet}
	</DashboardSection>

	<!-- Scanning -->
	<DashboardSection
		items={scanningJobs}
		key={(job) => job.id}
		accent="var(--color-accent-4)"
		label="SCANNING - {scanningJobs.length} {plural(scanningJobs.length, 'DISC', 'DISCS')}"
	>
		{#snippet row(job)}
			<ActiveJobRow {job} drive={driveSummary(dash.drives, job.drive_id)} />
		{/snippet}
	</DashboardSection>

	<!-- Active rips -->
	<DashboardSection
		items={nonWaitingActiveJobs}
		key={(job) => job.id}
		accent="var(--color-primary)"
		label="ACTIVE RIPS - {nonWaitingActiveJobs.length} IN PROGRESS"
	>
		{#snippet row(job)}
			<ActiveJobRow {job} drive={driveSummary(dash.drives, job.drive_id)} />
		{/snippet}
	</DashboardSection>

	<!-- Finishing (identified / ripped / ripped_partial) -->
	<DashboardSection
		items={finishingJobs}
		key={(job) => job.id}
		accent="var(--color-accent-1)"
		label="FINISHING - {finishingJobs.length} {plural(finishingJobs.length, 'JOB', 'JOBS')}"
	>
		{#snippet row(job)}
			<ActiveJobRow {job} />
		{/snippet}
	</DashboardSection>

	<!-- Active transcodes -->
	<DashboardSection
		items={$transcoderEnabled ? dash.active_transcodes : []}
		key={(tc) => tc.id}
		accent="var(--color-primary)"
		label="TRANSCODING - {dash.active_transcodes.length} ACTIVE"
	>
		{#snippet row(tc)}
			<TranscodeCard job={tc} />
		{/snippet}
	</DashboardSection>

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

	<AllJobsPanel jobs={jobsList} />
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
</style>
