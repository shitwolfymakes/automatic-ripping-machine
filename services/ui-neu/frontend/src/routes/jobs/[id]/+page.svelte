<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { onMount } from 'svelte';
	import { fetchJob, fetchNamingPreview, updateTrack } from '$lib/api/jobs';
	import { posterSrc, posterFallback } from '$lib/utils/poster';
	import PosterImage from '$lib/components/PosterImage.svelte';
	import type { JobDetailView, ResolveResponse, ApplySessionResponse, NamingPreviewItem } from '$lib/types/api.gen';
	import JobActions from '$lib/components/JobActions.svelte';
	import StatusBadge from '$lib/components/StatusBadge.svelte';
	import TitleSearch from '$lib/components/TitleSearch.svelte';
	import TrackTitleSearch from '$lib/components/TrackTitleSearch.svelte';
	import IdentifyDialog from '$lib/components/IdentifyDialog.svelte';
	import ApplySessionDialog from '$lib/components/ApplySessionDialog.svelte';
	import JobLifecycle from '$lib/components/JobLifecycle.svelte';
	import { discTypeLabel, isJobActive } from '$lib/utils/job-type';
	import { buildMetadataFields } from '$lib/utils/job-fields';
	import { extractMusicTracks } from '$lib/utils/music-tracks';
	import { trackKindLabel, trackSizeLabel } from '$lib/utils/track-fields';
	import LoadState from '$lib/components/LoadState.svelte';
	import SkeletonCard from '$lib/components/SkeletonCard.svelte';

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

	let metadataFields = $derived(detail ? buildMetadataFields(detail.job) : []);
	let musicTracks = $derived(detail ? extractMusicTracks(detail.job.metadata_json) : []);

	const panelTabBase = 'flex-1 border-r border-primary/15 px-4 py-2.5 text-center text-sm font-medium transition-colors dark:border-primary/15';
	const panelTabActive = 'text-primary border-b-2 border-b-primary bg-primary/5 dark:bg-primary/10';
	const panelTabInactive = 'text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300';
	function panelTabClass(id: string, last = false): string {
		const base = last ? panelTabBase.replace(' border-r border-primary/15', '') : panelTabBase;
		return `${base} ${activePanel === id ? panelTabActive : panelTabInactive}`;
	}

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

	function formatDuration(seconds: number | null | undefined): string {
		if (seconds == null) return '';
		const m = Math.floor(seconds / 60);
		const s = seconds % 60;
		return `${m}:${String(s).padStart(2, '0')}`;
	}

	onMount(() => {
		let stopped = false;
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
	<div class="space-y-6">
		<!-- Breadcrumb -->
		<nav class="text-sm">
			<a href="/" class="text-primary-text hover:underline dark:text-primary-text-dark">Dashboard</a>
			<span class="mx-1.5 text-gray-400 dark:text-gray-500">&rsaquo;</span>
			<span class="text-gray-500 dark:text-gray-400">{job.title || 'Untitled'}</span>
		</nav>

		{#if actionNote}
			<div
				data-testid="action-note"
				class="rounded-lg border border-primary/30 bg-primary/5 px-4 py-2 text-sm text-primary-text dark:border-primary/30 dark:bg-primary/10 dark:text-primary-text-dark"
			>
				{actionNote}
			</div>
		{/if}

		<!-- Main header container -->
		<div class="rounded-lg border border-primary/20 bg-surface shadow-xs overflow-hidden dark:border-primary/20 dark:bg-surface-dark">

			<!-- Title bar -->
			<div class="flex flex-wrap items-center gap-2 border-b border-primary/15 px-5 py-3 dark:border-primary/15">
				<h1 class="text-xl font-bold text-gray-900 dark:text-white">
					{job.title || 'Untitled'}
				</h1>
				{#if job.year}
					<span class="text-base text-gray-400 dark:text-gray-500">({job.year})</span>
				{/if}
				<StatusBadge status={job.status} />

				<!-- Action buttons pushed right -->
				<div class="flex flex-wrap items-center gap-2 ml-auto">
					{#if canResolve}
						<button
							type="button"
							data-testid="identify-open"
							onclick={() => (showIdentify = true)}
							class="rounded-lg border border-primary/30 px-3 py-1.5 text-sm font-medium text-primary hover:bg-primary/10 dark:border-primary/30 dark:text-primary dark:hover:bg-primary/10"
						>
							{identifyLabel}
						</button>
					{/if}
					{#if canApply}
						<button
							type="button"
							data-testid="apply-open"
							onclick={() => (showApply = true)}
							class="rounded-lg border border-primary/30 px-3 py-1.5 text-sm font-medium text-primary hover:bg-primary/10 dark:border-primary/30 dark:text-primary dark:hover:bg-primary/10"
						>
							Apply session
						</button>
					{/if}
					<JobActions {job} onaction={loadJob} ondelete={() => goto('/')} />
				</div>
			</div>

			<!-- Poster + Metadata grid -->
			<div class="flex flex-col sm:flex-row items-start">
				<!-- Poster -->
				<div class="shrink-0 border-b sm:border-b-0 sm:border-r border-primary/15 p-4 dark:border-primary/15">
					<PosterImage
						url={job.poster_url}
						alt={job.title ?? 'Poster'}
						class="rounded-md object-cover shadow-sm w-[120px]"
						style="aspect-ratio: 2/3"
					/>
				</div>

				<!-- Metadata grid -->
				<div class="metadata-grid w-full sm:w-auto flex-1 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4">
					{#each metadataFields as field}
						<div class="metadata-cell px-4 py-3 border-b border-r border-primary/15 dark:border-primary/15">
							{#if !field.empty}
								<div class="text-[11px] uppercase tracking-wider text-gray-500 dark:text-gray-400">{field.label}</div>
								{#if field.link}
									<a href={field.link} target="_blank" rel="noopener noreferrer" class="mt-1 block text-sm font-medium text-primary hover:underline dark:text-primary {field.mono ? 'font-mono text-xs' : ''}">{field.value}</a>
								{:else}
									<div class="mt-1 text-sm font-medium text-gray-900 dark:text-white {field.mono ? 'font-mono text-xs truncate' : ''}" title={field.mono ? field.value : undefined}>{field.value}</div>
								{/if}
							{/if}
						</div>
					{/each}
				</div>
			</div>

			<!-- Panel toggle bar: poster override (manual poster_url_manual quick-edit).
			     Disc identity now commits through the IdentifyDialog (resolve), not here. -->
			{#if isVideoDisc}
				<div class="flex border-t border-primary/15 bg-surface/50 dark:border-primary/15 dark:bg-surface-dark/50">
					<button onclick={() => (activePanel = activePanel === 'title' ? null : 'title')} class={panelTabClass('title', true)}>Poster &amp; metadata search</button>
				</div>
			{/if}

			<!-- Active panel content -->
			{#if activePanel === 'title'}
				<div class="border-t border-primary/15 p-5 dark:border-primary/15">
					<TitleSearch {job} onapply={handleTitleApply} />
				</div>
			{/if}
		</div>

		<!-- Lifecycle widget: visual stage progression below header, above status bars -->
		<div class="rounded-lg border border-primary/20 bg-surface px-4 py-3 shadow-xs dark:border-primary/20 dark:bg-surface-dark">
			<JobLifecycle status={job.status} sourceType={null} size="md" />
		</div>

		<!-- Tracks -->
		{#if tracks.length > 0}
			<section>
				<div class="mb-3 flex items-center justify-between">
					<h2 class="text-lg font-semibold text-gray-900 dark:text-white">
						Tracks ({tracks.length})
					</h2>
				</div>
				<div class="overflow-x-auto rounded-lg border border-primary/20 dark:border-primary/20">
					<table class="responsive-table w-full text-left text-sm">
						<thead class="bg-page text-gray-600 dark:bg-primary/5 dark:text-gray-400">
							<tr>
								<th class="px-4 py-3 font-medium">#</th>
								<th class="px-4 py-3 font-medium">Kind</th>
								<th class="px-4 py-3 font-medium">Title</th>
								<th class="px-4 py-3 font-medium">Filename</th>
								<th class="px-4 py-3 font-medium">Length</th>
								<th class="px-4 py-3 font-medium">Size</th>
								<th class="px-4 py-3 font-medium">Rip</th>
								<th class="px-4 py-3 font-medium">Status</th>
							</tr>
						</thead>
						<tbody class="divide-y divide-gray-200 dark:divide-gray-700">
							{#each tracks as track}
								{@const preview = previewByTrack.get(track.id)}
								<tr class="hover:bg-page dark:hover:bg-gray-800/50 {track.excluded ? 'opacity-50' : ''}">
									<td class="px-4 py-3" data-label="#">{track.index}</td>
									<td class="px-4 py-3 text-gray-700 dark:text-gray-300" data-label="Kind">{trackKindLabel(track.kind)}</td>
									<td
										class="px-4 py-3 cursor-pointer hover:bg-primary/5 dark:hover:bg-primary/10"
										data-label="Title"
										onclick={() => { editingTrackId = editingTrackId === track.id ? null : track.id; }}
									>
										{#if track.title}
											<div class="flex items-center gap-1.5">
												{#if track.poster_url}
													<img src={posterSrc(track.poster_url)} alt="" class="h-8 w-5 rounded-sm object-cover" onerror={posterFallback} />
												{/if}
												<div>
													<span class="font-medium text-gray-900 dark:text-white">{track.title}</span>
													{#if track.year}
														<span class="text-gray-400"> ({track.year})</span>
													{/if}
												</div>
											</div>
										{:else}
											<span class="text-xs text-gray-400">{job.title || 'Untitled'}{#if job.year} ({job.year}){/if}</span>
										{/if}
									</td>
									<td class="max-w-[260px] truncate px-4 py-3 font-mono text-xs text-gray-700 dark:text-gray-300" data-label="Filename" title={preview?.output_name ?? ''}>
										{#if preview?.output_name}
											<span>{preview.output_name}</span>
											{#if track.custom_filename}
												<span class="ml-1 rounded-sm bg-amber-100 px-1 py-0.5 text-[9px] font-semibold uppercase text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">custom</span>
											{/if}
										{:else}
											<span class="text-gray-400">{track.excluded ? 'excluded' : '—'}</span>
										{/if}
									</td>
									<td class="px-4 py-3" data-label="Length">
										{#if track.duration_seconds != null}
											{formatDuration(track.duration_seconds)}
										{:else if track.expected_duration_seconds != null}
											<span class="text-gray-400">~{formatDuration(track.expected_duration_seconds)}</span>
										{:else}—{/if}
									</td>
									<td class="px-4 py-3 text-gray-700 dark:text-gray-300" data-label="Size">{trackSizeLabel(track)}</td>
									<td class="px-4 py-3" data-label="Rip">
										<input
											type="checkbox"
											checked={!track.excluded}
											onchange={(e) => toggleExcluded(track.id, !(e.currentTarget as HTMLInputElement).checked)}
											title="Include this track in transcode output (the disc still rips in full)"
											class="h-4 w-4 rounded border-primary/30 text-primary focus:ring-primary"
										/>
									</td>
									<td class="px-4 py-3" data-label="Status">
										<StatusBadge status={track.status} />
										{#if track.attempts > 1}
											<span class="ml-1 text-[10px] text-gray-400" title="Rip attempts">×{track.attempts}</span>
										{/if}
									</td>
								</tr>
								{#if track.status === 'failed' && track.last_error}
									<tr>
										<td colspan="99" class="bg-red-50 px-4 py-2 text-xs text-red-700 dark:bg-red-900/15 dark:text-red-300" data-label="">
											<span class="font-semibold">Error:</span> {track.last_error}
										</td>
									</tr>
								{/if}
								{#if editingTrackId === track.id}
									<tr>
										<td colspan="99" class="px-4 py-3" data-label="">
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
				<h2 class="mb-3 text-lg font-semibold text-gray-900 dark:text-white">Disc fingerprints</h2>
				<div class="overflow-x-auto rounded-lg border border-primary/20 dark:border-primary/20">
					<table class="responsive-table w-full text-left text-sm">
						<thead class="bg-page text-gray-600 dark:bg-primary/5 dark:text-gray-400">
							<tr>
								<th class="px-4 py-3 font-medium">Algorithm</th>
								<th class="px-4 py-3 font-medium">Value</th>
							</tr>
						</thead>
						<tbody class="divide-y divide-gray-200 dark:divide-gray-700">
							{#each d.fingerprints as fp}
								<tr>
									<td class="px-4 py-3 uppercase" data-label="Algorithm">{fp.algo}</td>
									<td class="max-w-[420px] truncate px-4 py-3 font-mono text-xs text-gray-700 dark:text-gray-300" data-label="Value" title={fp.value}>{fp.value}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</section>
		{/if}

		<!-- Music tracklist (CD jobs; read-only) -->
		{#if musicTracks.length > 0}
			<section>
				<h2 class="mb-3 text-lg font-semibold text-gray-900 dark:text-white">Tracklist</h2>
				<div class="overflow-x-auto rounded-lg border border-primary/20 dark:border-primary/20">
					<table class="responsive-table w-full text-left text-sm">
						<thead class="bg-page text-gray-600 dark:bg-primary/5 dark:text-gray-400">
							<tr>
								<th class="px-4 py-3 font-medium">#</th>
								<th class="px-4 py-3 font-medium">Title</th>
								<th class="px-4 py-3 text-right font-medium">Duration</th>
							</tr>
						</thead>
						<tbody class="divide-y divide-gray-200 dark:divide-gray-700">
							{#each musicTracks as mt}
								<tr>
									<td class="px-4 py-3" data-label="#">{mt.number}</td>
									<td class="px-4 py-3 text-gray-900 dark:text-white" data-label="Title">{mt.title}</td>
									<td class="px-4 py-3 text-right text-gray-700 dark:text-gray-300" data-label="Duration">{mt.durationLabel}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</section>
		{/if}
	</div>

	{#if showIdentify}
		<IdentifyDialog {job} onclose={() => (showIdentify = false)} onidentified={handleIdentified} />
	{/if}
	{#if showApply}
		<ApplySessionDialog {job} onclose={() => (showApply = false)} onapplied={handleApplied} />
	{/if}
	{/snippet}
</LoadState>
