<script lang="ts">
	import { plural } from '$lib/utils/plural';
	import SetupChecklistCard from '$lib/components/setup/SetupChecklistCard.svelte';
	import { onMount } from 'svelte';
	import { fetchDashboard } from '$lib/api/dashboard';
	import { DashboardJobs } from '$lib/stores/dashboard-jobs.svelte';
	import type { DashboardData } from '$lib/api/dashboard';
	import DiscReviewWidget from '$lib/components/dashboard/DiscReviewWidget.svelte';
	import ActiveJobRow from '$lib/components/dashboard/ActiveJobRow.svelte';
	import IsoPreparingRow from '$lib/components/dashboard/IsoPreparingRow.svelte';
	import { ripProgress, startWS, stopWS, reconcileSubscriptions } from '$lib/stores/rips.svelte';
	import TranscodeCard from '$lib/components/dashboard/TranscodeCard.svelte';
	import DashboardSection from '$lib/components/dashboard/DashboardSection.svelte';
	import AllJobsPanel from '$lib/components/dashboard/AllJobsPanel.svelte';
	import EmptyDashboardPanel from '$lib/components/dashboard/EmptyDashboardPanel.svelte';
	import { fadeIn } from '$lib/transitions';
	import { fade } from 'svelte/transition';
	import { groupActiveJobs } from '$lib/dashboard/groups';
	import { isoSourceFor, isoKindFor } from '$lib/drives/iso-source';
	import { transcoderEnabled } from '$lib/stores/config';
	import { dashboard } from '$lib/stores/dashboard';
	import { get } from 'svelte/store';
	import { startRipperEvents, onRipperEvent } from '$lib/stores/ripper-events.svelte';

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
				driveNames={dash.drive_names}
				isoSources={dash.iso_sources}
				isoSourceKinds={dash.iso_source_kinds}
				paused={!dash.ripping_enabled}
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
			<ActiveJobRow
				{job}
				isoSource={isoSourceFor(job.drive_id, dash.iso_sources)}
				isoKind={isoKindFor(job.drive_id, dash.iso_source_kinds)}
			/>
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
			<ActiveJobRow
				{job}
				progress={ripProgress.value[job.id]?.progress_pct ?? null}
				eta={ripProgress.value[job.id]?.eta_seconds ?? null}
				live={ripProgress.value[job.id] ?? null}
				isoSource={isoSourceFor(job.drive_id, dash.iso_sources)}
				isoKind={isoKindFor(job.drive_id, dash.iso_source_kinds)}
			/>
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
