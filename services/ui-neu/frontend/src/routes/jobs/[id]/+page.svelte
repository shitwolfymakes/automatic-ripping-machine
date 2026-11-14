<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { jobPoster } from '$lib/match/poster';
	import PosterImage from '$lib/components/shared/PosterImage.svelte';
	import type { ResolveResponse, ApplySessionResponse } from '$lib/types/api.gen';
	import JobFactsGrid from '$lib/components/jobs/JobFactsGrid.svelte';
	import type { EditableJobField } from '$lib/jobs/fields';
	import JobHeaderActions from '$lib/components/jobs/JobHeaderActions.svelte';
	import JobTitleBar from '$lib/components/jobs/JobTitleBar.svelte';
	import JobPanelTabs from '$lib/components/jobs/JobPanelTabs.svelte';
	import TitleSearch from '$lib/components/match/TitleSearch.svelte';
	import JobTracksTable from '$lib/components/jobs/JobTracksTable.svelte';
	import JobFingerprints from '$lib/components/jobs/JobFingerprints.svelte';
	import JobMusicTracklist from '$lib/components/jobs/JobMusicTracklist.svelte';
	import MusicSearch from '$lib/components/music/MusicSearch.svelte';
	import EpisodeMatchPanel from '$lib/components/episodes/EpisodeMatchPanel.svelte';
	import IdentifyDialog from '$lib/components/jobs/IdentifyDialog.svelte';
	import ApplySessionDialog from '$lib/components/jobs/ApplySessionDialog.svelte';
	import JobLifecycle from '$lib/components/jobs/JobLifecycle.svelte';
	import { identitySuggestionOf } from '$lib/jobs/review';
	import { effectiveJobStatus, isPartialComplete } from '$lib/jobs/status';
	import IdentitySuggestionBanner from '$lib/components/jobs/IdentitySuggestionBanner.svelte';
	import { isLive } from '$lib/jobs/status-groups';
	import { applyNote, identifyNote } from '$lib/jobs/action-notes';
	import { fetchSessions } from '$lib/api/sessions';
	import { buildMetadataFields } from '$lib/jobs/fields';
	import LoadState from '$lib/components/shared/LoadState.svelte';
	import SkeletonCard from '$lib/components/shared/SkeletonCard.svelte';
	import JobRawMetadata from '$lib/components/jobs/JobRawMetadata.svelte';
	import JobLogPanel from '$lib/components/jobs/JobLogPanel.svelte';
	import { EpisodeMatching, watchEpisodeMatching } from '$lib/stores/episode-matching.svelte';
	import { reconcileSubscriptions, startWS } from '$lib/stores/rips.svelte';
	import JobRipProgress from '$lib/components/jobs/JobRipProgress.svelte';
	import { isAdmin } from '$lib/stores/auth';
	import { dashboard } from '$lib/stores/dashboard';
	import { JobDetail } from '$lib/stores/job-detail.svelte';
	import { JobPanels } from '$lib/stores/job-panels.svelte';

	const jobDetail = new JobDetail(() => $page.params.id ?? '');
	let detail = $derived(jobDetail.detail);
	const panels = new JobPanels();
	let episodePanel = $state<{ reload: () => Promise<void> } | undefined>(undefined);

	// "Matching episodes..." while the Backend re-matches after a type flip or a
	// series apply; job.identity_updated for this job (or a timeout) ends it.
	const matching = new EpisodeMatching();

	// Dialog visibility + a transient note shown after a resolve/apply lands.
	let showIdentify = $state(false);
	let showApply = $state(false);
	let actionNote = $state<string | null>(null);
	let noteTimer: ReturnType<typeof setTimeout> | null = null;

	function flashNote(message: string) {
		actionNote = message;
		if (noteTimer) clearTimeout(noteTimer);
		noteTimer = setTimeout(() => {
			actionNote = null;
		}, 6000);
	}

	function handleIdentified(resp: ResolveResponse) {
		showIdentify = false;
		jobDetail.load();
		const note = identifyNote(resp);
		if (note) flashNote(note);
	}

	function handleApplied(resp: ApplySessionResponse) {
		showApply = false;
		jobDetail.load();
		flashNote(applyNote(resp, jobDetail.isPostRip));
	}

	let sessionNames = $state(new Map<string, string>());
	let metadataFields = $derived(detail ? buildMetadataFields(detail.job, $dashboard.drive_names, sessionNames) : []);

	function handleTitleApply() {
		panels.active = null;
		jobDetail.load();
	}

	async function saveFact(field: EditableJobField | 'title', raw: string) {
		if (await jobDetail.saveFact(field, raw)) matching.start();
	}

	function handleSeriesApplied() {
		panels.active = 'episodes';
		matching.start();
		jobDetail.load();
	}

	function handleMediaTypeChanged(type: 'movie' | 'tv') {
		if (type === 'tv') matching.start();
		else matching.stop();
		panels.active = type === 'tv' ? 'episodes' : null;
		jobDetail.load();
	}

	function handleMusicApply() {
		panels.active = null;
		jobDetail.load();
	}

	// Client-side navigation from one job page to another keeps this component
	// mounted, so onMount never re-runs: reload whenever the route's job id changes
	// (a notification link, or Back/Forward between two jobs).
	let loadedId = $page.params.id ?? '';
	$effect(() => {
		const id = $page.params.id ?? '';
		if (id && id !== loadedId) {
			loadedId = id;
			jobDetail.load();
		}
	});

	// Live rip progress for this job (the same ripper.progress feed the
	// dashboard uses): subscribed only while the job is ripping.
	let ripping = $derived(detail?.job.status === 'ripping');
	$effect(() => {
		const id = detail?.job.id;
		reconcileSubscriptions(ripping && id ? [id] : []);
	});

	onMount(() => {
		let stopped = false;
		startWS();
		fetchSessions()
			.then((s) => (sessionNames = new Map(s.map((x) => [x.id, x.name]))))
			.catch(() => {});
		// Instant status for the job being viewed (ripper and transcode
		// events): refresh only when an event names this job, so other jobs'
		// events don't disturb the page. The 5s poll below stays as
		// reconciliation. Only the identity update ends matching
		// (rip.identify_resolved fires before the episode stage has run).
		const offRipperEvents = watchEpisodeMatching(
			() => $page.params.id,
			matching,
			async () => {
				await jobDetail.load();
				await episodePanel?.reload();
			}
		);
		async function poll() {
			// Never exits while mounted: a finished job can go live again (a new
			// apply), and the next tick picks that up without a remount.
			while (!stopped) {
				await new Promise((r) => setTimeout(r, 5000));
				if (!stopped && detail && isLive(detail.job)) await jobDetail.load({ poll: true });
			}
		}
		jobDetail.load().then(() => poll());
		return () => {
			stopped = true;
			offRipperEvents();
			reconcileSubscriptions([]);
			matching.stop();
		};
	});
</script>

<svelte:head>
	<title>ARM - {detail?.job.title || 'Job Detail'}</title>
</svelte:head>

<LoadState data={jobDetail.detail} loading={jobDetail.loading} error={jobDetail.error}>
	{#snippet loadingSlot()}
		<SkeletonCard lines={6} />
	{/snippet}
	{#snippet ready(d)}
		{@const job = d.job}
		{@const tracks = d.tracks}
		<div class="stack-lg stack">
			<!-- Breadcrumb -->
			<nav class="job-detail-breadcrumb">
				<a href="/" class="job-detail-breadcrumb-link">Dashboard</a>
				<span class="mx-1.5 job-detail-breadcrumb-sep">&rsaquo;</span>
				<span class="job-detail-breadcrumb-current">{job.title || 'Untitled'}</span>
			</nav>

			{#if actionNote}
				<div data-testid="action-note" class="job-detail-action-note">
					{actionNote}
				</div>
			{/if}

			<!-- Main header container -->
			<div class="job-detail-header-card">
				<!-- Title bar -->
				<JobTitleBar {job} {jobDetail} onsavetitle={(raw) => saveFact('title', raw)}>
					<JobHeaderActions
						{job}
						{jobDetail}
						onmediatypechanged={handleMediaTypeChanged}
						onidentify={() => (showIdentify = true)}
						onapply={() => (showApply = true)}
						ondelete={() => goto('/')}
					/>
				</JobTitleBar>

				<!-- A confident match identify held for confirmation (auto-apply off). -->
				{#if identitySuggestionOf(job)}
					<div class="job-detail-suggestion">
						<IdentitySuggestionBanner
							{job}
							canAct={$isAdmin && jobDetail.canResolve}
							onaccepted={handleIdentified}
							onsearch={() => (showIdentify = true)}
						/>
					</div>
				{/if}

				<!-- Poster + Metadata grid -->
				<div class="flex flex-col sm:flex-row items-start">
					<!-- Poster -->
					<div class="shrink-0 job-detail-poster-cell" data-disc-type={job.disc_type}>
						<PosterImage url={jobPoster(job)} alt={job.title ?? 'Poster'} class="job-detail-poster" />
					</div>

					<!-- Metadata grid -->
					<JobFactsGrid fields={metadataFields} canEdit={$isAdmin && jobDetail.canResolve} onsave={saveFact} />
				</div>

				<!-- Panel toggle bar: poster override (manual poster_url_manual quick-edit).
			     Disc identity commits through the IdentifyDialog (resolve), not here. -->
				<JobPanelTabs {job} {jobDetail} {panels} />

				<!-- Active panel content -->
				{#if panels.active === 'title'}
					<div class="job-detail-panel-content">
						<TitleSearch
							{job}
							onapply={handleTitleApply}
							onseries={handleSeriesApplied}
							initialType={panels.titleInitialType}
						/>
					</div>
				{/if}
				{#if panels.active === 'episodes' && jobDetail.isVideoDisc && job.media_type === 'tv'}
					<div class="job-detail-panel-content">
						<EpisodeMatchPanel
							bind:this={episodePanel}
							{job}
							{tracks}
							matching={matching.active}
							onchanged={() => jobDetail.load()}
							onsearchseries={panels.searchSeries}
						/>
					</div>
				{/if}
				{#if panels.active === 'music'}
					<div class="job-detail-panel-content">
						<MusicSearch {job} discTracks={tracks} onapply={handleMusicApply} />
					</div>
				{/if}
			</div>

			<!-- Lifecycle widget: visual stage progression below header, above status bars -->
			<div class="job-detail-lifecycle-card">
				<JobLifecycle status={effectiveJobStatus(job)} sourceType={null} size="md" partial={isPartialComplete(job)} />
			</div>

			{#if ripping}
				<JobRipProgress jobId={job.id} />
			{/if}

			<!-- Tracks -->
			{#if tracks.length > 0}
				<JobTracksTable
					{job}
					{tracks}
					tracksAreSeries={jobDetail.tracksAreSeries}
					previewByTrack={jobDetail.previewByTrack}
					onexcludedchange={jobDetail.setExcluded}
					ontitleapplied={() => jobDetail.load()}
				/>
			{/if}

			<!-- Disc fingerprints (read-only) -->
			{#if d.fingerprints && d.fingerprints.length > 0}
				<JobFingerprints fingerprints={d.fingerprints} />
			{/if}

			<!-- Music tracklist (CD jobs; read-only). Fallback ONLY when there are no
		     real Track rows yet — once the disc has tracks (which carry the mapped
		     song titles), the Tracks table above is authoritative and this would
		     just duplicate it. Mirrors neu's single-section behavior. -->
			{#if tracks.length === 0 && jobDetail.musicTracks.length > 0}
				<JobMusicTracklist tracks={jobDetail.musicTracks} />
			{/if}

			<!-- Live, per-service job log (backend + ripper + transcode aggregated) -->
			<JobLogPanel jobId={job.id} {job} />

			<!-- Raw metadata (collapsible): the full metadata_json as a JSON tree, nothing hidden -->
			{#if jobDetail.rawMetadataPairs.length > 0}
				<JobRawMetadata pairs={jobDetail.rawMetadataPairs} />
			{/if}
		</div>

		{#if showIdentify}
			<IdentifyDialog
				{job}
				driveNames={$dashboard.drive_names}
				onclose={() => (showIdentify = false)}
				onidentified={handleIdentified}
			/>
		{/if}
		{#if showApply}
			<ApplySessionDialog {job} onclose={() => (showApply = false)} onapplied={handleApplied} />
		{/if}
	{/snippet}
</LoadState>

<style>
	.job-detail-breadcrumb {
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-text-muted);
	}
	.job-detail-breadcrumb-link {
		color: var(--color-primary-text);
	}
	.job-detail-breadcrumb-link:hover {
		text-decoration: underline;
	}
	.job-detail-breadcrumb-sep {
		color: var(--color-text-faint);
	}
	.job-detail-breadcrumb-current {
		color: var(--color-text-muted);
	}
	.job-detail-action-note {
		border: 1px solid var(--color-border-strong);
		border-radius: var(--radius-lg);
		background: var(--color-primary-tint-1);
		padding: 0.5rem 1rem;
		font-size: 0.875rem;
		line-height: 1.25rem;
		color: var(--color-primary-text);
	}
	.job-detail-header-card {
		overflow: hidden;
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		background: var(--color-surface);
		box-shadow: var(--shadow-1);
	}
	.job-detail-suggestion {
		border-bottom: 1px solid var(--color-border);
		padding: 0.75rem 1.25rem;
	}
	.job-detail-poster-cell {
		border-bottom: 1px solid var(--color-border);
		padding: 1rem;
	}
	@media (min-width: 640px) {
		.job-detail-poster-cell {
			border-bottom: 0;
			border-right: 1px solid var(--color-border);
		}
	}
	/* :global: forwarded through PosterImage's class prop */
	:global(.job-detail-poster) {
		width: 120px;
		aspect-ratio: 2 / 3;
		border-radius: var(--radius-md);
		object-fit: cover;
		box-shadow: var(--shadow-1);
	}
	/* An audio CD's cover is square. :global: the poster is rendered by PosterImage. */
	.job-detail-poster-cell[data-disc-type='cd'] :global(.job-detail-poster) {
		aspect-ratio: 1 / 1;
	}
	.job-detail-panel-content {
		border-top: 1px solid var(--color-border);
		padding: 1.25rem;
	}
	.job-detail-lifecycle-card {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		background: var(--color-surface);
		padding: 0.75rem 1rem;
		box-shadow: var(--shadow-1);
	}
</style>
