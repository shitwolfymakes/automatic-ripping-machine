<script lang="ts">
	import type { JobView, TrackView, MetadataCandidate, MetadataReleaseDetail } from '$lib/types/api.gen';
	import { searchMusicMetadata, fetchMusicDetail, resolveJob, patchJob } from '$lib/api/jobs';
	import { matchIndicator, type MatchKind } from '$lib/utils/track-match';
	import PosterImage from './PosterImage.svelte';
	import { isAdmin } from '$lib/stores/auth';
	import Glyph from './Glyph.svelte';

	interface Props {
		job: JobView;
		discTracks: TrackView[];
		onapply?: () => void;
	}
	let { job, discTracks, onapply }: Props = $props();

	const meta = (job.metadata_json ?? {}) as Record<string, unknown>;
	let query = $state(job.title || (typeof meta.album === 'string' ? meta.album : ''));
	let artist = $state(typeof meta.artist === 'string' ? meta.artist : '');
	let filterType = $state('');
	let filterFormat = $state('');
	let filterCountry = $state('');
	let filterStatus = $state('');
	let matchCount = $state(discTracks.length > 0);

	let searching = $state(false);
	let results = $state<MetadataCandidate[]>([]);
	let searchError = $state<string | null>(null);

	let detail = $state<MetadataReleaseDetail | null>(null);
	let loadingDetail = $state(false);

	// Cards flipped to show their tracklist on the back face.
	let flippedCards = $state(new Map<string, MetadataReleaseDetail | 'loading'>());
	let editArtist = $state('');
	let editAlbum = $state('');
	let editYear = $state('');
	let discNumber = $state(job.disc_number != null ? String(job.disc_number) : '');
	let discTotal = $state(job.disc_total != null ? String(job.disc_total) : '');

	let applying = $state(false);
	let feedback = $state<{ type: 'success' | 'error'; message: string } | null>(null);
	let confirmMismatch = $state(false);
	let mismatchConfirmed = $state(false);
	let mappingPreview = $state(false);
	let mappingConfirmed = $state(false);

	$effect(() => {
		confirmMismatch = false;
		mismatchConfirmed = false;
		mappingPreview = false;
		mappingConfirmed = false;
		if (detail) {
			editArtist = detail.artist ?? '';
			editAlbum = detail.title;
			editYear = detail.year != null ? String(detail.year) : '';
			if (detail.disc_count != null && detail.disc_count > 1 && !discTotal) {
				discTotal = String(detail.disc_count);
			}
		}
	});

	// When the job knows its disc, scope a multi-disc release's tracklist to it.
	let visibleTracks = $derived(
		detail == null
			? []
			: detail.disc_count != null && detail.disc_count > 1 && job.disc_number != null
				? (detail.tracks ?? []).filter((t) => t.disc_number === job.disc_number)
				: (detail.tracks ?? [])
	);

	async function handleSearch() {
		if (!query.trim()) return;
		searching = true;
		results = [];
		searchError = null;
		detail = null;
		flippedCards = new Map();
		try {
			const opts: {
				artist?: string;
				track_count?: number;
				release_type?: string;
				format?: string;
				country?: string;
				status?: string;
			} = {};
			if (artist.trim()) opts.artist = artist.trim();
			if (matchCount && discTracks.length > 0) opts.track_count = discTracks.length;
			if (filterType) opts.release_type = filterType;
			if (filterFormat) opts.format = filterFormat;
			if (filterCountry.trim()) opts.country = filterCountry.trim();
			if (filterStatus) opts.status = filterStatus;
			const resp = await searchMusicMetadata(query.trim(), opts);
			results = resp.candidates;
			if (resp.detail) searchError = resp.detail;
			else if (results.length === 0) searchError = 'No results found.';
		} catch (e) {
			searchError = e instanceof Error ? e.message : 'Search failed';
		} finally {
			searching = false;
		}
	}

	function handleSearchKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') handleSearch();
	}

	async function openDetail(c: MetadataCandidate) {
		if (!c.provider_id) return;
		loadingDetail = true;
		feedback = null;
		try {
			detail = await fetchMusicDetail(c.provider_id);
		} catch (e) {
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Load failed' };
		} finally {
			loadingDetail = false;
		}
	}

	async function toggleFlip(e: MouseEvent, c: MetadataCandidate) {
		e.stopPropagation();
		if (!c.provider_id) return;
		const id = c.provider_id;
		if (flippedCards.has(id)) {
			const next = new Map(flippedCards);
			next.delete(id);
			flippedCards = next;
			return;
		}
		flippedCards = new Map(flippedCards).set(id, 'loading');
		try {
			const d = await fetchMusicDetail(id);
			flippedCards = new Map(flippedCards).set(id, d);
		} catch {
			flippedCards = new Map(flippedCards).set(id, {
				release_id: id,
				title: c.title,
				artist: null,
				year: c.year ?? null,
				poster_url: c.poster_url ?? null,
				disc_count: null,
				track_count: c.track_count ?? null,
				catalog_number: null,
				barcode: null,
				status: null,
				tracks: []
			} as MetadataReleaseDetail);
		}
	}

	function fmtMs(ms: number | null | undefined): string {
		if (ms == null) return '-';
		const total = Math.round(ms / 1000);
		return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
	}

	function fmtSec(secs: number | null | undefined): string {
		if (secs == null) return '-';
		const total = Math.round(secs);
		return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
	}

	const MATCH_TONE: Record<MatchKind, string> = {
		match: 'success',
		close: 'warning',
		mismatch: 'danger',
		unknown: 'muted'
	};

	let discTotalSec = $derived(
		discTracks.some((t) => t.expected_duration_seconds != null)
			? discTracks.reduce((sum, t) => sum + (t.expected_duration_seconds ?? 0), 0)
			: null
	);
	let mbTotalMs = $derived(visibleTracks.reduce((sum, t) => sum + (t.length_ms ?? 0), 0));

	let audioDiscTracks = $derived(discTracks.filter((t) => t.kind === 'audio_track'));
	let trackMapping = $derived.by(() => {
		const n = Math.min(audioDiscTracks.length, visibleTracks.length);
		const pairs = [];
		for (let i = 0; i < n; i++) {
			const disc = audioDiscTracks[i];
			const mb = visibleTracks[i];
			pairs.push({ disc, mb, match: matchIndicator(mb.length_ms, disc.expected_duration_seconds) });
		}
		return pairs;
	});

	async function applyRelease() {
		if (!editAlbum.trim() || !detail) return;
		const totalMatch = matchIndicator(mbTotalMs, discTotalSec);
		if (discTracks.length > 0 && totalMatch === 'mismatch' && !mismatchConfirmed) {
			confirmMismatch = true;
			return;
		}
		if (audioDiscTracks.length > 0 && visibleTracks.length > 0 && !mappingConfirmed) {
			mappingPreview = true;
			return;
		}
		applying = true;
		feedback = null;
		try {
			const yr = editYear.trim() ? Number(editYear.trim()) : null;
			const dn = discNumber.trim() ? Number(discNumber.trim()) : null;
			const dt = discTotal.trim() ? Number(discTotal.trim()) : null;
			const tracks = visibleTracks.map((t) => ({
				position: t.position,
				title: t.title,
				length_ms: t.length_ms ?? null,
				disc_number: t.disc_number ?? null
			}));
			await resolveJob(job.id, {
				title: editAlbum.trim(),
				year: Number.isFinite(yr as number) ? yr : null,
				disc_number: Number.isFinite(dn as number) ? dn : null,
				disc_total: Number.isFinite(dt as number) ? dt : null,
				metadata: { artist: editArtist.trim(), album: editAlbum.trim(), tracks }
			});
			feedback = { type: 'success', message: 'Release applied' };
			// Persist the release cover + any track-title mappings in one PATCH so
			// the cover art shows on the job's cards/rows (resolve doesn't set it).
			const cover = detail.poster_url ?? null;
			const trackEdits = trackMapping.map((p) => ({ track_id: p.disc.id, title: p.mb.title }));
			if (cover !== null || trackEdits.length > 0) {
				try {
					await patchJob(job.id, {
						...(cover !== null ? { poster_url_manual: cover } : {}),
						...(trackEdits.length > 0 ? { tracks: trackEdits } : {})
					});
				} catch {
					feedback = { type: 'success', message: 'Identified; cover/track titles not saved' };
				}
			}
			onapply?.();
		} catch (e) {
			feedback = { type: 'error', message: e instanceof Error ? e.message : 'Apply failed' };
		} finally {
			applying = false;
		}
	}

	let activeFilterCount = $derived(
		[filterType, filterFormat, filterCountry.trim(), filterStatus, matchCount && discTracks.length > 0 ? 'x' : ''].filter(Boolean).length
	);

	function clearFilters() {
		filterType = '';
		filterFormat = '';
		filterCountry = '';
		filterStatus = '';
		matchCount = false;
	}


</script>

{#snippet matchGlyph(kind: MatchKind)}
	{#if kind === 'match'}
		<Glyph name="check" class="mx-auto h-3.5 w-3.5" />
	{:else if kind === 'mismatch'}
		<Glyph name="x" class="mx-auto h-3.5 w-3.5" />
	{:else if kind === 'close'}
		~
	{:else}
		-
	{/if}
{/snippet}

<div class="stack">
	<!-- Search panel -->
	<div class="panel-section">
		<div class="flex flex-wrap items-end gap-2">
			<label class="flex-1 field music-search-field-min">
				<span class="eyebrow music-search-label">Album / Title</span>
				<input
					type="text"
					bind:value={query}
					onkeydown={handleSearchKeydown}
					onfocus={(e) => (e.target as HTMLInputElement).select()}
					placeholder="Album or title..."
				/>
			</label>
			<label class="field">
				<span class="eyebrow music-search-label">Artist</span>
				<input
					type="text"
					bind:value={artist}
					onkeydown={handleSearchKeydown}
					placeholder="Artist (optional)"
					class="w-36"
				/>
			</label>
			<label class="field">
				<span class="eyebrow music-search-label">Type</span>
				<select bind:value={filterType} class="music-search-select-sm">
					<option value="">Any</option>
					<option value="album">Album</option>
					<option value="single">Single</option>
					<option value="ep">EP</option>
					<option value="compilation">Compilation</option>
					<option value="live">Live</option>
					<option value="soundtrack">Soundtrack</option>
				</select>
			</label>
			<label class="field">
				<span class="eyebrow music-search-label">Format</span>
				<select bind:value={filterFormat} class="music-search-select-sm">
					<option value="">Any</option>
					<option value="CD">CD</option>
					<option value="Vinyl">Vinyl</option>
					<option value="Digital Media">Digital</option>
					<option value="Cassette">Cassette</option>
					<option value="SACD">SACD</option>
				</select>
			</label>
			<label class="field">
				<span class="eyebrow music-search-label">Country</span>
				<input
					type="text"
					bind:value={filterCountry}
					onkeydown={handleSearchKeydown}
					placeholder="US, GB..."
					class="w-20 music-search-select-sm"
				/>
			</label>
			<label class="field">
				<span class="eyebrow music-search-label">Status</span>
				<select bind:value={filterStatus} class="music-search-select-sm">
					<option value="">Any</option>
					<option value="official">Official</option>
					<option value="promotional">Promotional</option>
					<option value="bootleg">Bootleg</option>
				</select>
			</label>
			{#if discTracks.length > 0}
				<label class="flex items-center gap-1.5 field">
					<span class="eyebrow music-search-label">&nbsp;</span>
					<div class="flex items-center gap-1.5 music-search-checkbox-row">
						<input type="checkbox" bind:checked={matchCount} class="music-search-checkbox" />
						<span class="music-search-meta">{discTracks.length} tracks</span>
					</div>
				</label>
			{/if}
			<div class="flex items-center gap-2">
				<span class="eyebrow music-search-label">&nbsp;</span>
				<button
					onclick={handleSearch}
					disabled={searching || !query.trim()}
					class="btn btn-primary music-search-action-btn"
				>
					{searching ? 'Searching...' : 'Search'}
				</button>
				{#if activeFilterCount > 0}
					<button
						onclick={clearFilters}
						class="btn btn-ghost music-search-clear-btn"
					>
						Clear
					</button>
				{/if}
			</div>
		</div>
	</div>

	{#if searchError}
		<p class="music-search-meta">{searchError}</p>
	{/if}

	<!-- Results grid -->
	{#if !detail && results.length > 0}
		<div class="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
			{#each results as c}
				{@const flipKey = c.provider_id ?? ''}
				{@const flipData = flippedCards.get(flipKey)}
				{@const isFlipped = flippedCards.has(flipKey)}
				<div class="music-search-poster-scene">
					<div class="music-search-poster-card" data-flipped={isFlipped}>
						<!-- FRONT FACE -->
						<div class="music-search-poster-face">
							<button onclick={() => openDetail(c)} class="group flex w-full flex-col music-search-result-card">
								<PosterImage url={c.poster_url} class="aspect-square w-full music-search-result-poster" />
								<div class="p-1.5">
									<p class="truncate music-search-result-title">{c.title}</p>
									<div class="mt-1 flex flex-wrap items-center gap-1">
										{#if c.year}<span class="music-search-result-year">{c.year}</span>{/if}
										{#if c.release_type}<span class="music-search-result-pill" data-kind="type">{c.release_type}</span>{/if}
										{#if c.format}<span class="music-search-result-pill" data-kind="format">{c.format}</span>{/if}
										{#if c.country}<span class="music-search-result-pill" data-kind="country">{c.country}</span>{/if}
										{#if c.track_count}<span class="music-search-result-pill" data-kind="tracks">{c.track_count} tracks</span>{/if}
									</div>
								</div>
							</button>
							{#if c.track_count}
								<button
									onclick={(e) => toggleFlip(e, c)}
									class="absolute top-1 right-1 flex items-center gap-1 music-search-flip-btn"
									title="Flip to see tracklist"
								>
									<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
										<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
									</svg>
									{c.track_count} tracks
								</button>
							{/if}
						</div>

						<!-- BACK FACE -->
						<div class="music-search-poster-face music-search-poster-back">
							{#if flipData === 'loading'}
								<div class="flex h-full items-center justify-center music-search-back-loading">
									<svg class="mr-1.5 h-3.5 w-3.5 music-search-spinner" viewBox="0 0 24 24" fill="none">
										<circle class="music-search-spinner-track" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
										<path class="music-search-spinner-arc" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
									</svg>
									Loading...
								</div>
							{:else if flipData && flipData.tracks && flipData.tracks.length > 0}
								<!-- Compact header -->
								<div class="flex items-center gap-2 music-search-back-header">
									<PosterImage url={flipData.poster_url} class="h-8 w-8 shrink-0 music-search-back-poster" />
									<div class="min-w-0 flex-1">
										<p class="truncate music-search-back-title">{flipData.title}</p>
										<p class="truncate music-search-back-artist">{flipData.artist ?? ''}</p>
									</div>
								</div>
								<!-- Scrollable track list -->
								<div class="min-h-0 flex-1 overflow-y-auto">
									<table class="w-full music-search-back-table">
										<tbody>
											{#each flipData.tracks as track, i}
												{@const kind = discTracks.length > 0 ? matchIndicator(track.length_ms, discTracks[i]?.expected_duration_seconds) : null}
												<tr class="music-search-back-row">
													<td class="w-6 py-0.5 pl-1.5 pr-1 mono music-search-back-dim music-search-right">{track.position}</td>
													<td class="max-w-0 truncate py-0.5 pr-1 music-search-back-track-title">{track.title}</td>
													<td class="w-10 whitespace-nowrap py-0.5 pr-1 mono music-search-back-dim music-search-right">{fmtMs(track.length_ms)}</td>
													{#if kind}<td class="w-4 py-0.5 pr-1 music-search-match" data-tone={MATCH_TONE[kind]} title={kind}>{@render matchGlyph(kind)}</td>{/if}
												</tr>
											{/each}
										</tbody>
									</table>
								</div>
							{:else}
								<div class="flex h-full items-center justify-center music-search-back-empty">No track data</div>
							{/if}
							<!-- Flip-back button -->
							<button
								onclick={(e) => toggleFlip(e, c)}
								class="absolute top-1 right-1 flex items-center gap-1 music-search-flip-btn"
								title="Flip back"
							>
								<svg class="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
								</svg>
								Back
							</button>
						</div>
					</div>
				</div>
			{/each}
		</div>
	{/if}

	<!-- Detail / apply -->
	{#if loadingDetail}
		<p class="music-search-meta">Loading...</p>
	{:else if detail}
		<div class="stack panel-section">
			<button onclick={() => (detail = null)} class="btn btn-ghost music-search-action-btn flex items-center gap-1"><Glyph name="arrow-left" /> Back to results</button>
			<div class="flex items-start gap-3">
				<PosterImage url={detail.poster_url} class="h-24 w-24 music-search-detail-poster" />
				<div class="min-w-0 music-search-detail-meta">
					<p class="music-search-detail-title">{detail.title}</p>
					<p>{detail.artist ?? ''}</p>
					<p class="mt-1 flex flex-wrap gap-2">
						{#if detail.country}<span>{detail.country}</span>{/if}
						{#if detail.format}<span>{detail.format}</span>{/if}
						{#if detail.status}<span>{detail.status}</span>{/if}
						{#if detail.disc_count && detail.disc_count > 1}<span>{detail.disc_count} discs</span>{/if}
					</p>
					<p class="mt-0.5 mono music-search-catalog">
						{#if detail.catalog_number}Cat# {detail.catalog_number}{/if}
						{#if detail.barcode}| {detail.barcode}{/if}
					</p>
				</div>
			</div>

			<!-- Tracklist with match indicators -->
			<div class="overflow-x-auto music-search-table-scroll">
				<table class="table music-search-detail-table">
					<thead>
						<tr><th class="table-header">#</th><th class="table-header">Title</th>{#if discTracks.length > 0}<th class="table-header music-search-right">Disc Length</th>{/if}<th class="table-header music-search-right">{discTracks.length > 0 ? 'Match Length' : 'Duration'}</th>{#if discTracks.length > 0}<th class="table-header music-search-center">Match</th>{/if}</tr>
					</thead>
					<tbody>
						{#each visibleTracks as t, i}
							{@const kind = matchIndicator(t.length_ms, discTracks[i]?.expected_duration_seconds)}
							<tr class="table-row">
								<td class="table-cell">{t.position ?? i + 1}</td>
								<td class="table-cell">{t.title}</td>
								{#if discTracks.length > 0}<td class="table-cell mono music-search-right music-search-muted">{fmtSec(discTracks[i]?.expected_duration_seconds)}</td>{/if}
								<td class="table-cell music-search-right">{fmtMs(t.length_ms)}</td>
								{#if discTracks.length > 0}<td class="table-cell music-search-match" data-tone={MATCH_TONE[kind]} title={kind}>{@render matchGlyph(kind)}</td>{/if}
							</tr>
						{/each}
					</tbody>
					{#if discTracks.length > 0}
						{@const totalKind = matchIndicator(mbTotalMs, discTotalSec)}
						<tfoot class="music-search-tfoot">
							<tr>
								<td class="table-cell">Total</td>
								<td class="table-cell"></td>
								<td class="table-cell mono music-search-right">{fmtSec(discTotalSec)}</td>
								<td class="table-cell mono music-search-right">{fmtMs(mbTotalMs)}</td>
								<td class="table-cell music-search-match" data-tone={MATCH_TONE[totalKind]} title={totalKind}>{@render matchGlyph(totalKind)}</td>
							</tr>
						</tfoot>
					{/if}
				</table>
			</div>

			<!-- Editable fields -->
			<div class="grid grid-cols-2 gap-2">
				<label class="field col-span-2"><span class="field-label music-search-field-label-sm">Album</span><input bind:value={editAlbum} /></label>
				<label class="field"><span class="field-label music-search-field-label-sm">Artist</span><input bind:value={editArtist} /></label>
				<label class="field"><span class="field-label music-search-field-label-sm">Year</span><input bind:value={editYear} /></label>
				<label class="field"><span class="field-label music-search-field-label-sm">Disc #</span><input bind:value={discNumber} placeholder="-" /></label>
				<label class="field"><span class="field-label music-search-field-label-sm">Disc total</span><input bind:value={discTotal} placeholder="-" /></label>
			</div>

			{#if confirmMismatch}
				<div class="flex flex-wrap items-center gap-2 alert alert-danger">
					<span class="flex flex-1 items-center gap-1"><Glyph name="warning" /> Total length differs, likely the wrong release</span>
					<button
						onclick={() => {
							mismatchConfirmed = true;
							confirmMismatch = false;
							applyRelease();
						}}
						class="btn music-search-solid-danger music-search-action-btn"
					>
						Apply anyway
					</button>
					<button onclick={() => (confirmMismatch = false)} class="btn btn-ghost music-search-action-btn">
						Cancel
					</button>
				</div>
			{/if}

			{#if mappingPreview}
				<div class="stack panel-section music-search-mapping-preview">
					<p class="music-search-mapping-title">Confirm track title mapping</p>
					<div class="overflow-x-auto music-search-table-scroll">
						<table class="table">
							<tbody>
								{#each trackMapping as p}
									<tr class="table-row">
										<td class="table-cell whitespace-nowrap mono music-search-muted">Disc #{p.disc.index} ({fmtSec(p.disc.expected_duration_seconds)})</td>
										<td class="table-cell music-search-center music-search-faint"><Glyph name="arrow-right" class="mx-auto h-3.5 w-3.5" /></td>
										<td class="table-cell">{p.mb.title}</td>
										<td class="table-cell music-search-right mono music-search-muted">{fmtMs(p.mb.length_ms)}</td>
										<td class="table-cell music-search-match" data-tone={MATCH_TONE[p.match]} title={p.match}>{@render matchGlyph(p.match)}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
					<div class="flex items-center gap-2">
						<button
							onclick={() => {
								mappingConfirmed = true;
								mappingPreview = false;
								applyRelease();
							}}
							class="btn music-search-success-btn music-search-action-btn"
						>
							Apply titles
						</button>
						<button onclick={() => (mappingPreview = false)} class="btn btn-ghost music-search-action-btn">
							Cancel
						</button>
					</div>
				</div>
			{/if}

			<div class="flex items-center gap-2">
				{#if $isAdmin}
					<button onclick={applyRelease} disabled={applying || !editAlbum.trim()} class="btn music-search-success-btn music-search-action-btn">
						{applying ? 'Applying...' : 'Apply'}
					</button>
				{/if}
				{#if feedback}
					<span class="music-search-feedback" data-tone={feedback.type}>{feedback.message}</span>
				{/if}
			</div>
		</div>
	{/if}
</div>

<style>
	.music-search-label { color: var(--color-text-muted); }
	.music-search-field-min { min-width: 160px; }
	.music-search-right { text-align: right; }
	.music-search-spinner { animation: music-search-spin 1s linear infinite; }
	.music-search-spinner-track { opacity: 0.25; }
	.music-search-spinner-arc { opacity: 0.75; }
	@keyframes music-search-spin { to { transform: rotate(360deg); } }
	.music-search-meta { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
	.music-search-checkbox-row { padding: 0.3125rem 0; }
	.music-search-checkbox { width: 0.875rem; height: 0.875rem; border-radius: var(--radius-sm); accent-color: var(--color-primary); }
	.music-search-clear-btn:hover { color: var(--color-danger); }
	/* select/input variants one size down from field-control's default
	   (text-xs vs text-sm, tighter horizontal padding) */
	.music-search-select-sm { padding-left: 0.5rem; padding-right: 0.5rem; font-size: 0.75rem; line-height: 1rem; }

	.music-search-poster-scene { perspective: 800px; }
	.music-search-poster-card { position: relative; transform-style: preserve-3d; transition: transform 0.5s; }
	.music-search-poster-card[data-flipped="true"] { transform: rotateY(180deg); }
	.music-search-poster-face { position: relative; backface-visibility: hidden; }
	.music-search-poster-back { position: absolute; inset: 0; display: flex; flex-direction: column; overflow: hidden; border: 1px solid var(--color-border); border-radius: var(--radius-md); background: var(--color-surface-raised); transform: rotateY(180deg); }
	.music-search-result-card { border: 1px solid var(--color-border); border-radius: var(--radius-md); text-align: left; }
	/* :global: forwarded through PosterImage's class prop */
	:global(.music-search-result-poster) { border-top-left-radius: var(--radius-md); border-top-right-radius: var(--radius-md); }
	.music-search-result-title { font-size: 11px; font-weight: 500; color: var(--color-text); }
	.music-search-result-year { font-size: 10px; color: var(--color-text-muted); }
	.music-search-result-pill { border-radius: var(--radius-sm); padding: 0.125rem 0.25rem; font-size: 10px; font-weight: 500; }
	.music-search-result-pill[data-kind="type"] { background: color-mix(in srgb, var(--color-accent-3) 15%, transparent); color: var(--color-accent-3); }
	.music-search-result-pill[data-kind="format"] { background: var(--color-success-soft); color: var(--color-on-success-soft); }
	.music-search-result-pill[data-kind="country"] { background: var(--color-primary-tint-2); color: var(--color-text-secondary); }
	.music-search-result-pill[data-kind="tracks"] { background: var(--color-info-soft); color: var(--color-on-info-soft); }
	.music-search-flip-btn { border-radius: var(--radius-sm); padding: 0.125rem 0.375rem; font-size: 10px; font-weight: 500; color: var(--color-on-primary); background: color-mix(in srgb, var(--color-on-frame-accent) 60%, transparent); backdrop-filter: blur(4px); transition: background-color var(--motion-fast) var(--ease); }
	.music-search-flip-btn:hover { background: color-mix(in srgb, var(--color-on-frame-accent) 80%, transparent); }
	.music-search-back-loading { font-size: 11px; color: var(--color-text-muted); }
	.music-search-back-header { border-bottom: 1px solid var(--color-border); padding: 0.375rem; }
	/* :global: forwarded through PosterImage's class prop */
	:global(.music-search-back-poster) { border-radius: var(--radius-sm); }
	.music-search-back-title { font-size: 11px; font-weight: 600; color: var(--color-text); }
	.music-search-back-artist { font-size: 10px; color: var(--color-text-muted); }
	.music-search-back-table { font-size: 11px; }
	.music-search-back-row { border-bottom: 1px solid var(--color-border); }
	.music-search-back-row:last-child { border-bottom: 0; }
	.music-search-back-dim { color: var(--color-text-faint); }
	.music-search-back-track-title { color: var(--color-text-secondary); }
	.music-search-back-empty { font-size: 10px; color: var(--color-text-faint); }

	.music-search-match { text-align: center; }
	.music-search-match[data-tone="success"] { color: var(--color-success); }
	.music-search-match[data-tone="warning"] { color: var(--color-on-warning-soft); }
	.music-search-match[data-tone="danger"] { color: var(--color-danger); }
	.music-search-match[data-tone="muted"] { color: var(--color-text-faint); }

	/* :global: forwarded through PosterImage's class prop */
	:global(.music-search-detail-poster) { border-radius: var(--radius-md); object-fit: cover; }
	.music-search-detail-meta { font-size: 0.75rem; line-height: 1rem; color: var(--color-text-muted); }
	.music-search-detail-title { font-size: 0.875rem; line-height: 1.25rem; font-weight: 600; color: var(--color-text); }
	.music-search-catalog { font-size: 10px; }
	.music-search-table-scroll { border: 1px solid var(--color-border); border-radius: var(--radius-md); }
	.music-search-detail-table { font-size: 0.75rem; line-height: 1rem; }
	.music-search-detail-table .table-header, .music-search-detail-table .table-cell { padding: 0.25rem 0.5rem; }
	.music-search-center { text-align: center; }
	.music-search-muted { color: var(--color-text-muted); }
	.music-search-faint { color: var(--color-text-faint); }
	.music-search-tfoot { border-top: 1px solid var(--color-border); background: var(--color-surface-raised); font-weight: 500; }
	.music-search-field-label-sm { font-size: 10px; }
	.music-search-solid-danger { border: 0; background: var(--color-danger); color: var(--color-on-primary); }
	.music-search-mapping-preview { border-color: color-mix(in srgb, var(--color-primary) 30%, transparent); }
	.music-search-mapping-title { font-weight: 500; color: var(--color-text-secondary); }
	.music-search-success-btn { border: 0; background: var(--color-success); color: var(--color-on-primary); }
	.music-search-success-btn:hover { filter: brightness(0.9); }
	/* the original action buttons were px-3 py-1.5 (0.75rem/0.375rem),
	   narrower than .btn's default */
	.music-search-action-btn { padding: 0.375rem 0.75rem; border: 0; }
	.music-search-clear-btn { padding: 0.375rem 0.5rem; font-size: 0.75rem; line-height: 1rem; border: 0; }
	.music-search-feedback { font-size: 0.75rem; line-height: 1rem; }
	.music-search-feedback[data-tone="success"] { color: var(--color-success); }
	.music-search-feedback[data-tone="error"] { color: var(--color-danger); }
</style>
