<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { fetchJob, fetchNamingPreview, updateTrack } from '$lib/api/jobs';
	import { posterSrc, posterFallback, jobPoster } from '$lib/utils/poster';
	import PosterImage from '$lib/components/PosterImage.svelte';
	import type { JobDetailView, ResolveResponse, ApplySessionResponse, NamingPreviewItem } from '$lib/types/api.gen';
	import JobActions from '$lib/components/JobActions.svelte';
	import StatusBadge from '$lib/components/StatusBadge.svelte';
	import TitleSearch from '$lib/components/TitleSearch.svelte';
	import TrackTitleSearch from '$lib/components/TrackTitleSearch.svelte';
	import MusicSearch from '$lib/components/MusicSearch.svelte';
	import IdentifyDialog from '$lib/components/IdentifyDialog.svelte';
	import ApplySessionDialog from '$lib/components/ApplySessionDialog.svelte';
	import JobLifecycle from '$lib/components/JobLifecycle.svelte';
	import { effectiveJobStatus, isPartialComplete } from '$lib/utils/job-status';
	import { discTypeLabel, isJobActive } from '$lib/utils/job-type';
	import { buildMetadataFields, readJobMetadata } from '$lib/utils/job-fields';
	import { extractMusicTracks } from '$lib/utils/music-tracks';
	import { trackKindLabel, trackSizeLabel } from '$lib/utils/track-fields';
	import LoadState from '$lib/components/LoadState.svelte';
	import SkeletonCard from '$lib/components/SkeletonCard.svelte';
	import JsonTree from '$lib/components/JsonTree.svelte';
	import JobLogPanel from '$lib/components/JobLogPanel.svelte';
	import { startRipperEvents, onRipperEvent } from '$lib/stores/ripperEvents.svelte';
	import { isAdmin } from '$lib/stores/auth';
	import { dashboard } from '$lib/stores/dashboard';

	let detail = $state<JobDetailView | null>(null);
	let jobLoading = $state(true);
	let jobError = $state<Error | null>(null);
	let activePanel = $state<string | null>(null);
	let editingTrackId = $state<string | null>(null);
	let previewItems = $state<NamingPreviewItem[]>([]);
	let previewByTrack = $derived(new Map(previewItems.map((i) => [i.track_id, i])));

	// Dialog visibility + a transient note shown after a resolve/apply lands.
	let showIdentify = $state(false);
	let showApply = $state(false);
	let actionNote = $state<string | null>(null);
	let noteTimer: ReturnType<typeof setTimeout> | null = null;

	// Statuses where identify (resolve) and apply-session are offered. These
	// mirror the dialog gating in the spec: resolvable shows "Identify"/"Edit
	// identity"; apply-session shows once an identity exists or a rip is done.
	const RESOLVABLE_STATUSES = [
		'awaiting_user_id',
		'ripped_awaiting_identify',
		'identified',
		'ripped',
		'ripped_partial'
	];
	const APPLY_STATUSES = ['identified', 'ripped', 'ripped_partial', 'awaiting_user_id'];

	let canResolve = $derived(!!detail && RESOLVABLE_STATUSES.includes(detail.job.status));
	let canApply = $derived(!!detail && APPLY_STATUSES.includes(detail.job.status));

	// Identify is "Edit identity" once an identity already exists (post-rip /
	// identified), otherwise "Identify disc" for the auto-id-failed case.
	let identifyLabel = $derived(
		detail && ['awaiting_user_id', 'ripped_awaiting_identify'].includes(detail.job.status)
			? 'Identify disc'
			: 'Edit identity'
	);

	function flashNote(message: string) {
		actionNote = message;
		if (noteTimer) clearTimeout(noteTimer);
		noteTimer = setTimeout(() => {
			actionNote = null;
		}, 6000);
	}

	function handleIdentified(resp: ResolveResponse) {
		showIdentify = false;
		loadJob();
		if (resp.fan_out?.length) {
			const n = resp.fan_out.length;
			flashNote(`${n} session${n === 1 ? '' : 's'} resumed`);
		}
	}

	function handleApplied(resp: ApplySessionResponse) {
		showApply = false;
		loadJob();
		const n = resp.tasks?.length ?? 0;
		flashNote(`${n} transcode task${n === 1 ? '' : 's'} queued`);
	}

	let isVideoDisc = $derived(
		detail?.job.disc_type === 'dvd' || detail?.job.disc_type === 'bluray'
	);

	let isCdDisc = $derived(detail?.job.disc_type === 'cd');

	let metadataFields = $derived(detail ? buildMetadataFields(detail.job, $dashboard.drive_names) : []);
	let musicTracks = $derived(detail ? extractMusicTracks(detail.job.metadata_json) : []);
	let tracksAreSeries = $derived(
		(detail?.tracks ?? []).some((t) => t.video_type === 'series' || t.episode_number != null)
	);
	let jobMeta = $derived(detail ? readJobMetadata(detail.job.metadata_json) : {});
	let showRawMetadata = $state(false);
	let rawMetadataPairs = $derived(
		detail ? Object.entries((detail.job.metadata_json ?? {}) as Record<string, unknown>) : []
	);


	function handleTrackTitleApply() {
		editingTrackId = null;
		loadJob();
	}

	async function toggleExcluded(trackId: string, excluded: boolean) {
		try {
			await updateTrack($page.params.id ?? '', trackId, { excluded });
		} finally {
			// Refetch regardless: on success to pick up new naming/derived state,
			// on failure to restore the last server-truth value in the checkbox.
			await loadJob();
		}
	}

	async function loadJob() {
		const id = $page.params.id ?? '';
		// Only flip into the loading state on the FIRST load. The 5s poll
		// re-calls loadJob() and on a slow network that would unmount the
		// rendered detail in favour of a skeleton, then remount when the
		// fetch settles. On refreshes we already have a previous payload to
		// render; just swap it in place when the new one arrives.
		const isInitialLoad = detail == null;
		if (isInitialLoad) {
			jobLoading = true;
		}
		jobError = null;
		try {
			detail = await fetchJob(id);
			// Rendered filename preview is a best-effort SECOND fetch — never block
			// or fail the job render on it. Excluded tracks may be absent from items[].
			try {
				const preview = await fetchNamingPreview(id);
				previewItems = preview.items;
			} catch {
				previewItems = [];
			}
		} catch (e) {
			if (e instanceof Error && e.message.includes('404')) {
				goto('/');
				return;
			}
			jobError = e instanceof Error ? e : new Error('Failed to load job');
		} finally {
			jobLoading = false;
		}
	}

	function handleTitleApply() {
		activePanel = null;
		loadJob();
	}

	function handleMusicApply() {
		activePanel = null;
		loadJob();
	}

	function formatDuration(seconds: number | null | undefined): string {
		if (seconds == null) return '';
		const m = Math.floor(seconds / 60);
		const s = seconds % 60;
		return `${m}:${String(s).padStart(2, '0')}`;
	}

	onMount(() => {
		let stopped = false;
		// Instant status for the job being viewed: refresh only when an event
		// names this job — other jobs' events don't disturb the page. The 5s
		// poll below stays as reconciliation.
		startRipperEvents();
		const offRipperEvents = onRipperEvent((jobIds) => {
			const id = $page.params.id ?? '';
			if (id !== '' && jobIds.has(id)) loadJob();
		});
		async function poll() {
			while (!stopped) {
				await new Promise((r) => setTimeout(r, 5000));
				if (detail && isJobActive(detail.job.status)) {
					await loadJob();
				} else {
					break;
				}
			}
		}
		loadJob().then(() => poll());
		return () => {
			stopped = true;
			offRipperEvents();
		};
	});
</script>

<svelte:head>
	<title>ARM - {detail?.job.title || 'Job Detail'}</title>
</svelte:head>

<LoadState
	data={detail}
	loading={jobLoading}
	error={jobError}
	transitionKey="job-detail-main"
>
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
			<div
				data-testid="action-note"
				class="job-detail-action-note"
			>
				{actionNote}
			</div>
		{/if}

		<!-- Main header container -->
		<div class="job-detail-header-card">

			<!-- Title bar -->
			<div class="flex flex-wrap items-center gap-2 job-detail-title-bar">
				<h1 class="job-detail-title">
					{job.title || 'Untitled'}
				</h1>
				{#if job.year}
					<span class="job-detail-year">({job.year})</span>
				{/if}
				<StatusBadge status={effectiveJobStatus(job)} />
				{#if jobMeta.imdb_id && !isCdDisc}
					<a href="https://www.imdb.com/title/{jobMeta.imdb_id}" target="_blank" rel="noopener noreferrer" class="badge badge-imdb job-detail-imdb-badge">IMDb</a>
				{/if}
				{#if jobMeta.multi_title}
					<span class="badge badge-sm job-detail-multi-title-badge">Multi-Title</span>
				{/if}
				{#if jobMeta.source_type === 'iso'}
					<span class="job-detail-source-badge">ISO</span>
				{:else if jobMeta.source_type === 'folder'}
					<span class="job-detail-source-badge">Folder</span>
				{/if}

				<!-- Action buttons pushed right -->
				<div class="flex flex-wrap items-center gap-2 ml-auto">
					{#if canResolve && $isAdmin}
						<button
							type="button"
							data-testid="identify-open"
							onclick={() => (showIdentify = true)}
							class="btn job-detail-header-btn"
						>
							{identifyLabel}
						</button>
					{/if}
					{#if canApply && $isAdmin}
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
						<JobActions {job} onaction={loadJob} ondelete={() => goto('/')} />
					{/if}
				</div>
			</div>

			<!-- Poster + Metadata grid -->
			<div class="flex flex-col sm:flex-row items-start">
				<!-- Poster -->
				<div class="shrink-0 job-detail-poster-cell">
					<PosterImage
						url={jobPoster(job)}
						alt={job.title ?? 'Poster'}
						class="job-detail-poster"
						style={`aspect-ratio: ${job.disc_type === 'cd' ? '1/1' : '2/3'}`}
					/>
				</div>

				<!-- Metadata grid -->
				<div class="job-detail-metadata-grid w-full sm:w-auto flex-1 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4">
					{#each metadataFields as field}
						<div class="job-detail-metadata-cell">
							{#if !field.empty}
								<div class="job-detail-metadata-label">{field.label}</div>
								{#if field.link}
									<a href={field.link} target="_blank" rel="noopener noreferrer" class="mt-1 block job-detail-metadata-value job-detail-metadata-link {field.mono ? 'mono job-detail-metadata-mono' : ''}">{field.value}</a>
								{:else}
									<div class="mt-1 job-detail-metadata-value {field.mono ? 'mono job-detail-metadata-mono truncate' : ''}" title={field.mono ? field.value : undefined}>{field.value}</div>
								{/if}
							{/if}
						</div>
					{/each}
				</div>
			</div>

			<!-- Panel toggle bar: poster override (manual poster_url_manual quick-edit).
			     Disc identity now commits through the IdentifyDialog (resolve), not here. -->
			{#if isVideoDisc}
				<div class="flex job-detail-panel-toggle-bar">
					<button onclick={() => (activePanel = activePanel === 'title' ? null : 'title')} class="job-detail-panel-tab" aria-pressed={activePanel === 'title'}>Poster &amp; metadata search</button>
				</div>
			{:else if isCdDisc}
				<div class="flex job-detail-panel-toggle-bar">
					<button onclick={() => (activePanel = activePanel === 'music' ? null : 'music')} class="job-detail-panel-tab" aria-pressed={activePanel === 'music'}>Match CD</button>
				</div>
			{/if}

			<!-- Active panel content -->
			{#if activePanel === 'title'}
				<div class="job-detail-panel-content">
					<TitleSearch {job} onapply={handleTitleApply} />
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

		<!-- Tracks -->
		{#if tracks.length > 0}
			<section>
				<div class="mb-3 flex items-center justify-between">
					<h2 class="job-detail-section-title">
						Tracks ({tracks.length})
					</h2>
				</div>
				<div class="overflow-x-auto job-detail-table-scroll">
					<table class="table responsive-table">
						<thead>
							<tr>
								<th class="table-header">#</th>
								<th class="table-header">Kind</th>
								<th class="table-header">Title</th>
								{#if tracksAreSeries}
									<th class="table-header">Episode</th>
								{/if}
								<th class="table-header">Filename</th>
								<th class="table-header">Length</th>
								<th class="table-header">Size</th>
								<th class="table-header">Include</th>
								<th class="table-header">Rip</th>
								<th class="table-header">Transcode</th>
							</tr>
						</thead>
						<tbody>
							{#each tracks as track}
								{@const preview = previewByTrack.get(track.id)}
								<tr class="table-row" data-disabled={track.excluded}>
									<td class="table-cell" data-label="#">{track.index}</td>
									<td class="table-cell job-detail-track-kind" data-label="Kind">{trackKindLabel(track.kind)}</td>
									<td
										class="table-cell {$isAdmin ? 'job-detail-track-title-cell' : ''}"
										data-label="Title"
										onclick={$isAdmin ? () => { editingTrackId = editingTrackId === track.id ? null : track.id; } : undefined}
									>
										{#if track.title}
											<div class="flex items-center gap-1.5">
												{#if track.poster_url}
													<img data-poster src={posterSrc(track.poster_url)} alt="" class="job-detail-track-poster" onerror={posterFallback} />
												{/if}
												<div>
													<span class="job-detail-track-title job-detail-track-title-strong">{track.title}</span>
													{#if track.year}
														<span class="job-detail-track-year"> ({track.year})</span>
													{/if}
													<div class="mt-0.5 flex flex-wrap items-center gap-1">
														{#if track.imdb_id}
															<a href="https://www.imdb.com/title/{track.imdb_id}" target="_blank" rel="noopener noreferrer" onclick={(e) => e.stopPropagation()} class="badge badge-imdb job-detail-track-imdb-badge">IMDb</a>
														{/if}
														{#if track.edition}
															<span class="job-detail-track-meta-pill">{track.edition}</span>
														{/if}
														{#if track.role}
															<span class="job-detail-track-meta-pill">{track.role}</span>
														{/if}
													</div>
												</div>
											</div>
										{:else}
											<span class="job-detail-track-untitled">{job.title || 'Untitled'}{#if job.year} ({job.year}){/if}</span>
										{/if}
									</td>
									{#if tracksAreSeries}
										<td class="table-cell" data-label="Episode">
											{#if track.episode_number != null}
												<span class="job-detail-track-title job-detail-track-title-strong">{track.episode_number}</span>
												{#if track.episode_name}
													<span class="ml-1.5 job-detail-track-episode-name">{track.episode_name}</span>
												{/if}
											{:else}
												<span class="job-detail-track-faint">-</span>
											{/if}
										</td>
									{/if}
									<td class="truncate table-cell mono job-detail-track-filename" data-label="Filename" title={preview?.output_name ?? ''}>
										{#if preview?.output_name}
											<span>{preview.output_name}</span>
											{#if track.custom_filename}
												<span class="ml-1 badge badge-sm badge-warning">custom</span>
											{/if}
										{:else}
											<span class="job-detail-track-faint">{track.excluded ? 'excluded' : '-'}</span>
										{/if}
									</td>
									<td class="table-cell" data-label="Length">
										{#if track.duration_seconds != null}
											{formatDuration(track.duration_seconds)}
										{:else if track.expected_duration_seconds != null}
											<span class="job-detail-track-faint">~{formatDuration(track.expected_duration_seconds)}</span>
										{:else}-{/if}
									</td>
									<td class="table-cell job-detail-track-kind" data-label="Size">{trackSizeLabel(track)}</td>
									<td class="table-cell" data-label="Include">
										{#if $isAdmin}
											<input
												type="checkbox"
												checked={!track.excluded}
												onchange={(e) => toggleExcluded(track.id, !(e.currentTarget as HTMLInputElement).checked)}
												title="Include this track in transcode output (the disc still rips in full)"
												class="job-detail-track-checkbox"
											/>
										{:else}
											<span class="job-detail-track-untitled">{track.excluded ? 'Excluded' : 'Included'}</span>
										{/if}
									</td>
									<!-- Rip outcome -->
									<td class="table-cell" data-label="Rip">
										<span class="flex items-center gap-1">
											<StatusBadge status={track.status} />
											{#if track.attempts > 1}
												<span class="job-detail-track-attempts" title="Rip attempts">x{track.attempts}</span>
											{/if}
										</span>
									</td>
									<!-- Transcode outcome (— when no transcode task yet) -->
									<td class="table-cell" data-label="Transcode">
										{#if track.transcode_status}
											<StatusBadge status={track.transcode_status} />
										{:else}
											<span class="job-detail-track-faint">-</span>
										{/if}
									</td>
								</tr>
								{#if track.status === 'failed' && track.last_error}
									<tr>
										<td colspan="99" class="table-cell job-detail-track-error" data-label="">
											<span class="job-detail-error-strong">Error:</span> {track.last_error}
										</td>
									</tr>
								{/if}
								{#if editingTrackId === track.id}
									<tr>
										<td colspan="99" class="table-cell" data-label="">
											<TrackTitleSearch jobId={job.id} {track} onapply={handleTrackTitleApply} onclose={() => { editingTrackId = null; }} />
										</td>
									</tr>
								{/if}
							{/each}
						</tbody>
					</table>
				</div>
			</section>
		{/if}

		<!-- Disc fingerprints (read-only) -->
		{#if d.fingerprints && d.fingerprints.length > 0}
			<section>
				<h2 class="mb-3 job-detail-section-title">Disc fingerprints</h2>
				<div class="overflow-x-auto job-detail-table-scroll">
					<table class="table responsive-table">
						<thead>
							<tr>
								<th class="table-header">Algorithm</th>
								<th class="table-header">Value</th>
							</tr>
						</thead>
						<tbody>
							{#each d.fingerprints as fp}
								<tr class="table-row">
									<td class="table-cell job-detail-uppercase" data-label="Algorithm">{fp.algo}</td>
									<td class="truncate table-cell mono job-detail-fingerprint-value" data-label="Value" title={fp.value}>{fp.value}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</section>
		{/if}

		<!-- Music tracklist (CD jobs; read-only). Fallback ONLY when there are no
		     real Track rows yet — once the disc has tracks (which carry the mapped
		     song titles), the Tracks table above is authoritative and this would
		     just duplicate it. Mirrors neu's single-section behavior. -->
		{#if tracks.length === 0 && musicTracks.length > 0}
			<section>
				<h2 class="mb-3 job-detail-section-title">
					Tracklist
					<span class="job-detail-section-subtitle">({musicTracks.length} tracks via MusicBrainz)</span>
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
							{#each musicTracks as mt}
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
		<JobLogPanel jobId={job.id} status={job.status} />

		<!-- Raw metadata (collapsible): the full metadata_json as a JSON tree, nothing hidden -->
		{#if rawMetadataPairs.length > 0}
			<section>
				<button
					type="button"
					onclick={() => { showRawMetadata = !showRawMetadata; }}
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
						{#each rawMetadataPairs as [key, value]}
							<JsonTree {value} name={key} depth={0} />
						{/each}
					</div>
				{/if}
			</section>
		{/if}
	</div>

	{#if showIdentify}
		<IdentifyDialog {job} driveNames={$dashboard.drive_names} onclose={() => (showIdentify = false)} onidentified={handleIdentified} />
	{/if}
	{#if showApply}
		<ApplySessionDialog {job} onclose={() => (showApply = false)} onapplied={handleApplied} />
	{/if}
	{/snippet}
</LoadState>

<style>
	.job-detail-breadcrumb { font-size: 0.875rem; line-height: 1.25rem; color: var(--color-text-muted); }
	.job-detail-breadcrumb-link { color: var(--color-primary-text); }
	.job-detail-breadcrumb-link:hover { text-decoration: underline; }
	.job-detail-breadcrumb-sep { color: var(--color-text-faint); }
	.job-detail-breadcrumb-current { color: var(--color-text-muted); }
	.job-detail-action-note { border: 1px solid var(--color-border-strong); border-radius: var(--radius-lg); background: var(--color-primary-tint-1); padding: 0.5rem 1rem; font-size: 0.875rem; line-height: 1.25rem; color: var(--color-primary-text); }
	.job-detail-header-card { overflow: hidden; border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); box-shadow: var(--shadow-1); }
	.job-detail-title-bar { border-bottom: 1px solid var(--color-border); padding: 0.75rem 1.25rem; }
	/* the original header buttons were px-3 py-1.5 text-sm (0.75rem/0.375rem,
	   0.875rem) - between .btn's default and .btn-sm */
	.job-detail-header-btn { min-height: auto; padding: 0.375rem 0.75rem; font-size: 0.875rem; line-height: 1.25rem; }
	.job-detail-title { font-size: 1.25rem; line-height: 1.75rem; font-weight: 700; color: var(--color-text); }
	.job-detail-year { font-size: 1rem; line-height: 1.5rem; color: var(--color-text-faint); }
	.job-detail-imdb-badge { border-radius: 9999px; padding: 0.125rem 0.625rem; font-size: 10px; }
	.job-detail-multi-title-badge { border-radius: 9999px; text-transform: uppercase; background: color-mix(in srgb, var(--color-accent-3) 15%, transparent); color: var(--color-accent-3); }
	.job-detail-source-badge { border-radius: var(--radius-sm); padding: 0.125rem 0.5rem; font-size: 10px; font-weight: 500; background: color-mix(in srgb, var(--color-accent-3) 15%, transparent); color: var(--color-accent-3); }
	.job-detail-poster-cell { border-bottom: 1px solid var(--color-border); padding: 1rem; }
	@media (min-width: 640px) { .job-detail-poster-cell { border-bottom: 0; border-right: 1px solid var(--color-border); } }
	/* :global: forwarded through PosterImage's class prop */
	:global(.job-detail-poster) { width: 120px; border-radius: var(--radius-md); object-fit: cover; box-shadow: var(--shadow-1); }
	.job-detail-metadata-cell { border-bottom: 1px solid var(--color-border); border-right: 1px solid var(--color-border); padding: 0.75rem 1rem; }
	.job-detail-metadata-cell:nth-child(2n) { border-right-width: 0; }
	@media (min-width: 640px) {
		.job-detail-metadata-cell:nth-child(2n) { border-right-width: 1px; }
		.job-detail-metadata-cell:nth-child(3n) { border-right-width: 0; }
	}
	@media (min-width: 1024px) {
		.job-detail-metadata-cell:nth-child(3n) { border-right-width: 1px; }
		.job-detail-metadata-cell:nth-child(4n) { border-right-width: 0; }
	}
	.job-detail-metadata-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-text-muted); }
	.job-detail-metadata-value { font-size: 0.875rem; line-height: 1.25rem; font-weight: 500; color: var(--color-text); }
	.job-detail-metadata-link { color: var(--color-primary); }
	.job-detail-metadata-link:hover { text-decoration: underline; }
	.job-detail-metadata-mono { font-size: 0.75rem; line-height: 1rem; }
	.job-detail-panel-toggle-bar { border-top: 1px solid var(--color-border); background: color-mix(in srgb, var(--color-surface) 50%, transparent); }
	.job-detail-panel-tab { flex: 1 1 0%; padding: 0.625rem 1rem; text-align: center; font-size: 0.875rem; line-height: 1.25rem; font-weight: 500; color: var(--color-text-muted); transition: color var(--motion-fast) var(--ease); }
	.job-detail-panel-tab:hover { color: var(--color-text-secondary); }
	.job-detail-panel-tab[aria-pressed="true"] { color: var(--color-primary); border-bottom: 2px solid var(--color-primary); background: var(--color-primary-tint-1); }
	.job-detail-panel-content { border-top: 1px solid var(--color-border); padding: 1.25rem; }
	.job-detail-lifecycle-card { border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); padding: 0.75rem 1rem; box-shadow: var(--shadow-1); }
	.job-detail-section-title { font-size: 1.125rem; line-height: 1.75rem; font-weight: 600; color: var(--color-text); }
	.job-detail-section-title .chevron { transition: transform var(--motion-fast) var(--ease); }
	.job-detail-section-title[aria-expanded="true"] .chevron { transform: rotate(90deg); }
	.job-detail-section-subtitle { font-size: 0.875rem; line-height: 1.25rem; font-weight: 400; color: var(--color-text-muted); }
	.job-detail-table-scroll { border: 1px solid var(--color-border); border-radius: var(--radius-lg); }
	.job-detail-right { text-align: right; }
	.job-detail-track-kind { color: var(--color-text-secondary); }
	.job-detail-track-title-cell { cursor: pointer; }
	.job-detail-track-title-cell:hover { background: var(--color-primary-tint-1); }
	.job-detail-track-poster { height: 2rem; width: 1.25rem; border-radius: var(--radius-sm); object-fit: cover; }
	.job-detail-track-title { color: var(--color-text); }
	.job-detail-track-title-strong { font-weight: 500; }
	.job-detail-error-strong { font-weight: 600; }
	.job-detail-uppercase { text-transform: uppercase; }
	.job-detail-track-year { color: var(--color-text-faint); }
	.job-detail-track-imdb-badge { border-radius: 9999px; padding: 0.125rem 0.375rem; font-size: 9px; }
	.job-detail-track-meta-pill { border-radius: var(--radius-sm); padding: 0.125rem 0.375rem; font-size: 9px; font-weight: 500; background: var(--color-primary-tint-2); color: var(--color-text-secondary); }
	.job-detail-track-untitled { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-faint); }
	.job-detail-track-episode-name { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
	.job-detail-track-faint { color: var(--color-text-faint); }
	.job-detail-track-filename { max-width: 260px; color: var(--color-text-secondary); }
	.job-detail-track-checkbox { width: 1rem; height: 1rem; border-radius: var(--radius-sm); accent-color: var(--color-primary); }
	.job-detail-track-attempts { font-size: 10px; color: var(--color-text-faint); }
	.job-detail-track-error { background: var(--color-danger-soft); color: var(--color-on-danger-soft); }
	.job-detail-fingerprint-value { max-width: 420px; color: var(--color-text-secondary); }
	.job-detail-raw-metadata { border: 1px solid var(--color-border); border-radius: var(--radius-lg); padding: 0.75rem; }
</style>
