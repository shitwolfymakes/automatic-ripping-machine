<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { jobPoster } from '$lib/utils/poster';
	import PosterImage from '$lib/components/PosterImage.svelte';
	import type { ResolveResponse, ApplySessionResponse } from '$lib/types/api.gen';
	import InlineField from '$lib/components/InlineField.svelte';
	import type { EditableJobField } from '$lib/utils/job-fields';
	import JobActions from '$lib/components/JobActions.svelte';
	import StatusBadge from '$lib/components/StatusBadge.svelte';
	import TitleSearch from '$lib/components/TitleSearch.svelte';
	import JobTracksTable from '$lib/components/JobTracksTable.svelte';
	import JobFingerprints from '$lib/components/JobFingerprints.svelte';
	import MusicSearch from '$lib/components/MusicSearch.svelte';
	import EpisodeMatchPanel from '$lib/components/episodes/EpisodeMatchPanel.svelte';
	import MediaTypeSwitch from '$lib/components/episodes/MediaTypeSwitch.svelte';
	import IdentifyDialog from '$lib/components/IdentifyDialog.svelte';
	import ApplySessionDialog from '$lib/components/ApplySessionDialog.svelte';
	import JobLifecycle from '$lib/components/JobLifecycle.svelte';
	import { identitySuggestionOf } from '$lib/utils/job-review';
	import { effectiveJobStatus, isPartialComplete } from '$lib/utils/job-status';
	import IdentitySuggestionBanner from '$lib/components/IdentitySuggestionBanner.svelte';
	import { isAwaitingIdentity, isLive } from '$lib/utils/job-status-groups';
	import { applyNote, identifyNote } from '$lib/utils/job-action-notes';
	import { fetchSessions } from '$lib/api/sessions';
	import { buildMetadataFields } from '$lib/utils/job-fields';
	import LoadState from '$lib/components/LoadState.svelte';
	import SkeletonCard from '$lib/components/SkeletonCard.svelte';
	import JsonTree from '$lib/components/JsonTree.svelte';
	import JobLogPanel from '$lib/components/JobLogPanel.svelte';
	import { EpisodeMatching, watchEpisodeMatching } from '$lib/stores/episodeMatching.svelte';
	import { reconcileSubscriptions, startWS } from '$lib/stores/rips.svelte';
	import JobRipProgress from '$lib/components/JobRipProgress.svelte';
	import { isAdmin } from '$lib/stores/auth';
	import { dashboard } from '$lib/stores/dashboard';
	import { JobDetail } from '$lib/stores/jobDetail.svelte';

	const jobDetail = new JobDetail(() => $page.params.id ?? '');
	let detail = $derived(jobDetail.detail);
	let activePanel = $state<'title' | 'music' | 'episodes' | null>(null);
	// Search type TitleSearch opens with; set when the episode panel asks for a series search.
	let titleInitialType = $state<'movie' | 'tv' | undefined>(undefined);
	let episodePanel = $state<{ reload: () => Promise<void> } | undefined>(undefined);

	// "Matching episodes..." while the Backend re-matches after a type flip or a
	// series apply; job.identity_updated for this job (or a timeout) ends it.
	const matching = new EpisodeMatching();

	// Dialog visibility + a transient note shown after a resolve/apply lands.
	let showIdentify = $state(false);
	let showApply = $state(false);
	let actionNote = $state<string | null>(null);
	let noteTimer: ReturnType<typeof setTimeout> | null = null;

	// Identify is "Edit identity" once an identity already exists (post-rip /
	// identified), otherwise "Identify disc" for the auto-id-failed case.
	let identifyLabel = $derived(detail && isAwaitingIdentity(detail.job.status) ? 'Identify disc' : 'Edit identity');

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
	let showRawMetadata = $state(false);

	function handleTitleApply() {
		activePanel = null;
		jobDetail.load();
	}

	async function saveFact(field: EditableJobField | 'title', raw: string) {
		if (await jobDetail.saveFact(field, raw)) matching.start();
	}

	function handleSeriesApplied() {
		activePanel = 'episodes';
		matching.start();
		jobDetail.load();
	}

	function handleMediaTypeChanged(type: 'movie' | 'tv') {
		if (type === 'tv') matching.start();
		else matching.stop();
		activePanel = type === 'tv' ? 'episodes' : null;
		jobDetail.load();
	}

	function togglePanel(panel: 'title' | 'music' | 'episodes') {
		if (panel === 'title') titleInitialType = undefined;
		activePanel = activePanel === panel ? null : panel;
	}

	function handleMusicApply() {
		activePanel = null;
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

<LoadState data={jobDetail.detail} loading={jobDetail.loading} error={jobDetail.error} transitionKey="job-detail-main">
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
				<div class="flex flex-wrap items-center gap-2 job-detail-title-bar">
					<h1 class="job-detail-title">
						<InlineField
							label="Title"
							value={job.title || 'Untitled'}
							canEdit={$isAdmin && jobDetail.canResolve}
							onsave={(raw) => saveFact('title', raw)}
						/>
					</h1>
					{#if job.year}
						<span class="job-detail-year">({job.year})</span>
					{/if}
					<StatusBadge status={effectiveJobStatus(job)} />
					{#if jobDetail.isVideoDisc && !$isAdmin}
						<span class="badge" data-testid="media-type-text">{job.media_type === 'tv' ? 'TV' : 'Movie'}</span>
					{/if}
					{#if jobDetail.jobMeta.imdb_id && !jobDetail.isCdDisc}
						<a
							href="https://www.imdb.com/title/{jobDetail.jobMeta.imdb_id}"
							target="_blank"
							rel="noopener noreferrer"
							class="badge badge-imdb job-detail-imdb-badge">IMDb</a
						>
					{/if}
					{#if jobDetail.jobMeta.multi_title}
						<span class="badge badge-sm job-detail-multi-title-badge">Multi-Title</span>
					{/if}
					{#if jobDetail.jobMeta.source_type === 'iso'}
						<span class="job-detail-source-badge">ISO</span>
					{:else if jobDetail.jobMeta.source_type === 'folder'}
						<span class="job-detail-source-badge">Folder</span>
					{/if}

					<!-- Action buttons pushed right -->
					<div class="flex flex-wrap items-center gap-2 ml-auto">
						<!-- The type is part of the identity, so its switch sits beside Edit identity. -->
						{#if jobDetail.isVideoDisc && $isAdmin}
							<MediaTypeSwitch {job} handSetCount={jobDetail.handSetCount} onchanged={handleMediaTypeChanged} />
						{/if}
						<!-- A video job with an identity edits it in place on the facts grid and
						     searches from the tab below; the dialog stays for a disc still waiting
						     for an identity, and for CDs (album, artist, track titles). -->
						{#if jobDetail.canResolve && $isAdmin && (jobDetail.isCdDisc || isAwaitingIdentity(job.status))}
							<button
								type="button"
								data-testid="identify-open"
								onclick={() => (showIdentify = true)}
								class="btn job-detail-header-btn"
							>
								{identifyLabel}
							</button>
						{/if}
						{#if jobDetail.canApply && $isAdmin}
							<button
								type="button"
								data-testid="apply-open"
								onclick={() => (showApply = true)}
								class="btn job-detail-header-btn"
							>
								Apply session
							</button>
						{/if}
						{#if $isAdmin}
							<JobActions {job} onaction={jobDetail.load} ondelete={() => goto('/')} />
						{/if}
					</div>
				</div>

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
					<div class="job-detail-metadata-grid w-full sm:w-auto flex-1 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4">
						{#each metadataFields as field, i (field.empty ? `pad-${i}` : field.label)}
							<div class="job-detail-metadata-cell">
								{#if !field.empty}
									<div class="job-detail-metadata-label">{field.label}</div>
									{#if field.link}
										<a
											href={field.link}
											target="_blank"
											rel="noopener noreferrer"
											class="mt-1 block job-detail-metadata-value job-detail-metadata-link {field.mono
												? 'mono job-detail-metadata-mono'
												: ''}">{field.value}</a
										>
									{:else if field.edit}
										<div class="mt-1 job-detail-metadata-value" data-testid="fact-{field.edit}">
											<InlineField
												label={field.label}
												value={field.raw ?? ''}
												type={field.edit === 'season' ||
												field.edit === 'disc_number' ||
												field.edit === 'disc_total' ||
												field.edit === 'year'
													? 'number'
													: 'text'}
												canEdit={$isAdmin && jobDetail.canResolve}
												onsave={(raw) => saveFact(field.edit!, raw)}
											/>
										</div>
									{:else}
										<div
											class="mt-1 job-detail-metadata-value {field.mono
												? 'mono job-detail-metadata-mono truncate'
												: ''}"
											title={field.mono ? field.value : undefined}
										>
											{field.value}
										</div>
									{/if}
								{/if}
							</div>
						{/each}
					</div>
				</div>

				<!-- Panel toggle bar: poster override (manual poster_url_manual quick-edit).
			     Disc identity now commits through the IdentifyDialog (resolve), not here. -->
				{#if jobDetail.isVideoDisc}
					<div class="flex job-detail-panel-toggle-bar">
						<button
							type="button"
							onclick={() => togglePanel('title')}
							class="job-detail-panel-tab"
							aria-pressed={activePanel === 'title'}>Poster &amp; metadata search</button
						>
						{#if job.media_type === 'tv'}
							<button
								type="button"
								onclick={() => togglePanel('episodes')}
								class="job-detail-panel-tab"
								aria-pressed={activePanel === 'episodes'}>Match Episodes</button
							>
						{/if}
					</div>
				{:else if jobDetail.isCdDisc}
					<div class="flex job-detail-panel-toggle-bar">
						<button
							type="button"
							onclick={() => togglePanel('music')}
							class="job-detail-panel-tab"
							aria-pressed={activePanel === 'music'}>Match CD</button
						>
					</div>
				{/if}

				<!-- Active panel content -->
				{#if activePanel === 'title'}
					<div class="job-detail-panel-content">
						<TitleSearch
							{job}
							onapply={handleTitleApply}
							onseries={handleSeriesApplied}
							initialType={titleInitialType}
						/>
					</div>
				{/if}
				{#if activePanel === 'episodes' && jobDetail.isVideoDisc && job.media_type === 'tv'}
					<div class="job-detail-panel-content">
						<EpisodeMatchPanel
							bind:this={episodePanel}
							{job}
							{tracks}
							matching={matching.active}
							onchanged={() => jobDetail.load()}
							onsearchseries={() => {
								titleInitialType = 'tv';
								activePanel = 'title';
							}}
						/>
					</div>
				{/if}
				{#if activePanel === 'music'}
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
				<section>
					<h2 class="mb-3 job-detail-section-title">
						Tracklist
						<span class="job-detail-section-subtitle">({jobDetail.musicTracks.length} tracks via MusicBrainz)</span>
					</h2>
					<div class="overflow-x-auto job-detail-table-scroll">
						<table class="table responsive-table">
							<thead>
								<tr>
									<th class="table-header">#</th>
									<th class="table-header">Title</th>
									<th class="table-header job-detail-right">Duration</th>
								</tr>
							</thead>
							<tbody>
								{#each jobDetail.musicTracks as mt (mt.number)}
									<tr class="table-row">
										<td class="table-cell" data-label="#">{mt.number}</td>
										<td class="table-cell" data-label="Title">{mt.title}</td>
										<td class="table-cell job-detail-right" data-label="Duration">{mt.durationLabel}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				</section>
			{/if}

			<!-- Live, per-service job log (backend + ripper + transcode aggregated) -->
			<JobLogPanel jobId={job.id} {job} />

			<!-- Raw metadata (collapsible): the full metadata_json as a JSON tree, nothing hidden -->
			{#if jobDetail.rawMetadataPairs.length > 0}
				<section>
					<button
						type="button"
						onclick={() => {
							showRawMetadata = !showRawMetadata;
						}}
						class="flex w-full items-center gap-2 job-detail-section-title"
						aria-expanded={showRawMetadata}
					>
						<svg class="h-4 w-4 chevron" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
						</svg>
						Raw metadata
					</button>
					{#if showRawMetadata}
						<div class="mt-3 overflow-x-auto job-detail-raw-metadata">
							{#each jobDetail.rawMetadataPairs as [key, value] (key)}
								<JsonTree {value} name={key} depth={0} />
							{/each}
						</div>
					{/if}
				</section>
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
	.job-detail-title-bar {
		border-bottom: 1px solid var(--color-border);
		padding: 0.75rem 1.25rem;
	}
	.job-detail-suggestion {
		border-bottom: 1px solid var(--color-border);
		padding: 0.75rem 1.25rem;
	}
	/* the original header buttons were px-3 py-1.5 text-sm (0.75rem/0.375rem,
	   0.875rem) - between .btn's default and .btn-sm */
	.job-detail-header-btn {
		min-height: auto;
		padding: 0.375rem 0.75rem;
		font-size: 0.875rem;
		line-height: 1.25rem;
	}
	.job-detail-title {
		font-size: 1.25rem;
		line-height: 1.75rem;
		font-weight: 700;
		color: var(--color-text);
	}
	.job-detail-year {
		font-size: 1rem;
		line-height: 1.5rem;
		color: var(--color-text-faint);
	}
	.job-detail-imdb-badge {
		border-radius: 9999px;
		padding: 0.125rem 0.625rem;
		font-size: 10px;
	}
	.job-detail-multi-title-badge {
		border-radius: 9999px;
		text-transform: uppercase;
		background: color-mix(in srgb, var(--color-accent-3) 15%, transparent);
		color: var(--color-accent-3);
	}
	.job-detail-source-badge {
		border-radius: var(--radius-sm);
		padding: 0.125rem 0.5rem;
		font-size: 10px;
		font-weight: 500;
		background: color-mix(in srgb, var(--color-accent-3) 15%, transparent);
		color: var(--color-accent-3);
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
	.job-detail-metadata-cell {
		border-bottom: 1px solid var(--color-border);
		border-right: 1px solid var(--color-border);
		padding: 0.75rem 1rem;
	}
	.job-detail-metadata-cell:nth-child(2n) {
		border-right-width: 0;
	}
	@media (min-width: 640px) {
		.job-detail-metadata-cell:nth-child(2n) {
			border-right-width: 1px;
		}
		.job-detail-metadata-cell:nth-child(3n) {
			border-right-width: 0;
		}
	}
	@media (min-width: 1024px) {
		.job-detail-metadata-cell:nth-child(3n) {
			border-right-width: 1px;
		}
		.job-detail-metadata-cell:nth-child(4n) {
			border-right-width: 0;
		}
	}
	.job-detail-metadata-label {
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--color-text-muted);
	}
	.job-detail-metadata-value {
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 500;
		color: var(--color-text);
	}
	.job-detail-metadata-link {
		color: var(--color-primary);
	}
	.job-detail-metadata-link:hover {
		text-decoration: underline;
	}
	.job-detail-metadata-mono {
		font-size: 0.75rem;
		line-height: 1rem;
	}
	.job-detail-panel-toggle-bar {
		border-top: 1px solid var(--color-border);
		background: color-mix(in srgb, var(--color-surface) 50%, transparent);
	}
	.job-detail-panel-tab {
		flex: 1 1 0%;
		padding: 0.625rem 1rem;
		text-align: center;
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 500;
		color: var(--color-text-muted);
		transition: color var(--motion-fast) var(--ease);
	}
	.job-detail-panel-tab:hover {
		color: var(--color-text-secondary);
	}
	.job-detail-panel-tab[aria-pressed='true'] {
		color: var(--color-primary);
		border-bottom: 2px solid var(--color-primary);
		background: var(--color-primary-tint-1);
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
	.job-detail-section-title {
		font-size: 1.125rem;
		line-height: 1.75rem;
		font-weight: 600;
		color: var(--color-text);
	}
	.job-detail-section-title .chevron {
		transition: transform var(--motion-fast) var(--ease);
	}
	.job-detail-section-title[aria-expanded='true'] .chevron {
		transform: rotate(90deg);
	}
	.job-detail-section-subtitle {
		font-size: 0.875rem;
		line-height: 1.25rem;
		font-weight: 400;
		color: var(--color-text-muted);
	}
	.job-detail-table-scroll {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
	}
	.job-detail-right {
		text-align: right;
	}
	.job-detail-raw-metadata {
		border: 1px solid var(--color-border);
		border-radius: var(--radius-lg);
		padding: 0.75rem;
	}
</style>
