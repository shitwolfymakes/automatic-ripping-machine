<script lang="ts">
	import type { JobView, TrackView, MetadataCandidate, MetadataReleaseDetail } from '$lib/types/api.gen';
	import { searchMusicMetadata, fetchMusicDetail, resolveJob, patchJob } from '$lib/api/jobs';
	import { matchIndicator } from '$lib/utils/track-match';
	import { reveal } from '$lib/transitions';
	import PosterImage from './PosterImage.svelte';
	import { isAdmin } from '$lib/stores/auth';

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
		if (ms == null) return '—';
		const total = Math.round(ms / 1000);
		return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
	}

	function fmtSec(secs: number | null | undefined): string {
		if (secs == null) return '—';
		const total = Math.round(secs);
		return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
	}

	const MATCH_GLYPH = { match: '✓', close: '~', mismatch: '✗', unknown: '—' };
	const MATCH_CLASS = {
		match: 'text-green-600 dark:text-green-400',
		close: 'text-amber-600 dark:text-amber-400',
		mismatch: 'text-red-600 dark:text-red-400',
		unknown: 'text-gray-400'
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

	const btnBase = 'rounded-lg px-3 py-1.5 text-sm font-medium disabled:opacity-50 transition-colors';
	const inputBase = 'rounded-lg border border-primary/25 bg-primary/5 px-3 py-1.5 text-sm text-gray-900 focus:border-primary focus:outline-hidden focus:ring-1 focus:ring-primary dark:border-primary/30 dark:bg-primary/10 dark:text-white';
	const selectBase = 'rounded-lg border border-primary/25 bg-primary/5 px-2 py-1.5 text-xs text-gray-900 focus:border-primary focus:outline-hidden focus:ring-1 focus:ring-primary dark:border-primary/30 dark:bg-primary/10 dark:text-white';
</script>

<div class="space-y-3">
	<!-- Search panel -->
	<div class="rounded-lg border border-primary/20 bg-primary/[0.02] p-3 dark:border-primary/20 dark:bg-primary/[0.03]">
		<div class="flex flex-wrap items-end gap-2">
			<label class="min-w-[160px] flex-1">
				<span class="mb-0.5 block text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">Album / Title</span>
				<input
					type="text"
					bind:value={query}
					onkeydown={handleSearchKeydown}
					onfocus={(e) => (e.target as HTMLInputElement).select()}
					placeholder="Album or title..."
					class="w-full {inputBase}"
				/>
			</label>
			<label>
				<span class="mb-0.5 block text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">Artist</span>
				<input
					type="text"
					bind:value={artist}
					onkeydown={handleSearchKeydown}
					placeholder="Artist (optional)"
					class="w-36 {inputBase}"
				/>
			</label>
			<label>
				<span class="mb-0.5 block text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">Type</span>
				<select bind:value={filterType} class="{selectBase}">
					<option value="">Any</option>
					<option value="album">Album</option>
					<option value="single">Single</option>
					<option value="ep">EP</option>
					<option value="compilation">Compilation</option>
					<option value="live">Live</option>
					<option value="soundtrack">Soundtrack</option>
				</select>
			</label>
			<label>
				<span class="mb-0.5 block text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">Format</span>
				<select bind:value={filterFormat} class="{selectBase}">
					<option value="">Any</option>
					<option value="CD">CD</option>
					<option value="Vinyl">Vinyl</option>
					<option value="Digital Media">Digital</option>
					<option value="Cassette">Cassette</option>
					<option value="SACD">SACD</option>
				</select>
			</label>
			<label>
				<span class="mb-0.5 block text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">Country</span>
				<input
					type="text"
					bind:value={filterCountry}
					onkeydown={handleSearchKeydown}
					placeholder="US, GB..."
					class="w-20 {selectBase}"
				/>
			</label>
			<label>
				<span class="mb-0.5 block text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">Status</span>
				<select bind:value={filterStatus} class="{selectBase}">
					<option value="">Any</option>
					<option value="official">Official</option>
					<option value="promotional">Promotional</option>
					<option value="bootleg">Bootleg</option>
				</select>
			</label>
			{#if discTracks.length > 0}
				<label class="flex items-center gap-1.5">
					<span class="mb-0.5 block text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">&nbsp;</span>
					<div class="flex items-center gap-1.5 py-[5px]">
						<input type="checkbox" bind:checked={matchCount} class="h-3.5 w-3.5 rounded border-gray-300 text-primary focus:ring-primary" />
						<span class="text-xs text-gray-600 dark:text-gray-400">{discTracks.length} tracks</span>
					</div>
				</label>
			{/if}
			<div class="flex items-center gap-2">
				<span class="mb-0.5 block text-[10px]">&nbsp;</span>
				<button
					onclick={handleSearch}
					disabled={searching || !query.trim()}
					class="{btnBase} bg-primary text-on-primary hover:bg-primary-hover dark:bg-primary dark:hover:bg-primary-hover"
				>
					{searching ? 'Searching...' : 'Search'}
				</button>
				{#if activeFilterCount > 0}
					<button
						onclick={clearFilters}
						class="rounded-lg px-2 py-1.5 text-xs text-gray-500 hover:text-red-600 dark:text-gray-400 dark:hover:text-red-400"
					>
						Clear
					</button>
				{/if}
			</div>
		</div>
	</div>

	{#if searchError}
		<p in:reveal class="text-xs text-gray-500 dark:text-gray-400">{searchError}</p>
	{/if}

	<!-- Results grid -->
	{#if !detail && results.length > 0}
		<div class="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
			{#each results as c}
				{@const flipKey = c.provider_id ?? ''}
				{@const flipData = flippedCards.get(flipKey)}
				{@const isFlipped = flippedCards.has(flipKey)}
				<div style="perspective: 800px">
					<div class="relative" style="transform-style: preserve-3d; transition: transform 0.5s; {isFlipped ? 'transform: rotateY(180deg)' : ''}">
						<!-- FRONT FACE -->
						<div class="relative" style="backface-visibility: hidden; transform: rotateY(0deg)">
							<button onclick={() => openDetail(c)} class="group flex w-full flex-col rounded-md border border-primary/15 text-left dark:border-primary/20">
								<PosterImage url={c.poster_url} class="aspect-square w-full rounded-t-md object-cover" />
								<div class="p-1.5">
									<p class="truncate text-[11px] font-medium text-gray-900 dark:text-white">{c.title}</p>
									<div class="mt-1 flex flex-wrap items-center gap-1">
										{#if c.year}<span class="text-[10px] text-gray-500">{c.year}</span>{/if}
										{#if c.release_type}<span class="rounded-sm bg-purple-100 px-1 py-0.5 text-[10px] font-medium text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">{c.release_type}</span>{/if}
										{#if c.format}<span class="rounded-sm bg-green-100 px-1 py-0.5 text-[10px] font-medium text-green-700 dark:bg-green-900/30 dark:text-green-400">{c.format}</span>{/if}
										{#if c.country}<span class="rounded-sm bg-gray-100 px-1 py-0.5 text-[10px] font-medium text-gray-600 dark:bg-gray-700 dark:text-gray-300">{c.country}</span>{/if}
										{#if c.track_count}<span class="rounded-sm bg-blue-100 px-1 py-0.5 text-[10px] font-medium text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">{c.track_count} tracks</span>{/if}
									</div>
								</div>
							</button>
							{#if c.track_count}
								<button
									onclick={(e) => toggleFlip(e, c)}
									class="absolute top-1 right-1 z-10 flex items-center gap-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-medium text-white backdrop-blur-sm transition-colors hover:bg-black/80"
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
						<div class="absolute inset-0 flex flex-col overflow-hidden rounded-md border border-primary/15 bg-white dark:border-primary/20 dark:bg-gray-900" style="backface-visibility: hidden; transform: rotateY(180deg)">
							{#if flipData === 'loading'}
								<div class="flex h-full items-center justify-center text-[11px] text-gray-500 dark:text-gray-400">
									<svg class="mr-1.5 h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
										<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
										<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
									</svg>
									Loading...
								</div>
							{:else if flipData && flipData.tracks && flipData.tracks.length > 0}
								<!-- Compact header -->
								<div class="flex items-center gap-2 border-b border-primary/15 p-1.5 dark:border-primary/20">
									<PosterImage url={flipData.poster_url} class="h-8 w-8 shrink-0 rounded object-cover" />
									<div class="min-w-0 flex-1">
										<p class="truncate text-[11px] font-semibold text-gray-900 dark:text-white">{flipData.title}</p>
										<p class="truncate text-[10px] text-gray-500 dark:text-gray-400">{flipData.artist ?? ''}</p>
									</div>
								</div>
								<!-- Scrollable track list -->
								<div class="min-h-0 flex-1 overflow-y-auto">
									<table class="w-full text-[11px]">
										<tbody>
											{#each flipData.tracks as track, i}
												{@const kind = discTracks.length > 0 ? matchIndicator(track.length_ms, discTracks[i]?.expected_duration_seconds) : null}
												<tr class="border-b border-gray-100 last:border-0 dark:border-gray-800">
													<td class="w-6 py-0.5 pl-1.5 pr-1 text-right font-mono text-gray-400 dark:text-gray-500">{track.position}</td>
													<td class="max-w-0 truncate py-0.5 pr-1 text-gray-700 dark:text-gray-300">{track.title}</td>
													<td class="w-10 whitespace-nowrap py-0.5 pr-1 text-right font-mono text-gray-400 dark:text-gray-500">{fmtMs(track.length_ms)}</td>
													{#if kind}<td class="w-4 py-0.5 pr-1 text-center {MATCH_CLASS[kind]}" title={kind}>{MATCH_GLYPH[kind]}</td>{/if}
												</tr>
											{/each}
										</tbody>
									</table>
								</div>
							{:else}
								<div class="flex h-full items-center justify-center text-[10px] text-gray-400 dark:text-gray-500">No track data</div>
							{/if}
							<!-- Flip-back button -->
							<button
								onclick={(e) => toggleFlip(e, c)}
								class="absolute top-1 right-1 z-10 flex items-center gap-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] font-medium text-white backdrop-blur-sm transition-colors hover:bg-black/80"
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
		<p class="text-xs text-gray-400">Loading...</p>
	{:else if detail}
		<div class="space-y-3 rounded-md border border-primary/15 bg-primary/5 p-3 dark:border-primary/20 dark:bg-primary/10">
			<button onclick={() => (detail = null)} class="{btnBase} text-gray-500 hover:text-gray-700 dark:text-gray-400">← Back to results</button>
			<div class="flex items-start gap-3">
				<PosterImage url={detail.poster_url} class="h-24 w-24 rounded object-cover" />
				<div class="min-w-0 text-xs text-gray-600 dark:text-gray-400">
					<p class="text-sm font-semibold text-gray-900 dark:text-white">{detail.title}</p>
					<p>{detail.artist ?? ''}</p>
					<p class="mt-1 space-x-2">
						{#if detail.country}<span>{detail.country}</span>{/if}
						{#if detail.format}<span>{detail.format}</span>{/if}
						{#if detail.status}<span>{detail.status}</span>{/if}
						{#if detail.disc_count && detail.disc_count > 1}<span>{detail.disc_count} discs</span>{/if}
					</p>
					<p class="mt-0.5 font-mono text-[10px]">
						{#if detail.catalog_number}Cat# {detail.catalog_number}{/if}
						{#if detail.barcode}· {detail.barcode}{/if}
					</p>
				</div>
			</div>

			<!-- Tracklist with match indicators -->
			<div class="overflow-x-auto rounded border border-primary/15 dark:border-primary/20">
				<table class="w-full text-left text-xs">
					<thead class="bg-page text-gray-600 dark:bg-primary/5 dark:text-gray-400">
						<tr><th class="px-2 py-1">#</th><th class="px-2 py-1">Title</th>{#if discTracks.length > 0}<th class="px-2 py-1 text-right">Disc Length</th>{/if}<th class="px-2 py-1 text-right">{discTracks.length > 0 ? 'Match Length' : 'Duration'}</th>{#if discTracks.length > 0}<th class="px-2 py-1 text-center">Match</th>{/if}</tr>
					</thead>
					<tbody class="divide-y divide-gray-200 dark:divide-gray-700">
						{#each visibleTracks as t, i}
							{@const kind = matchIndicator(t.length_ms, discTracks[i]?.expected_duration_seconds)}
							<tr>
								<td class="px-2 py-1">{t.position ?? i + 1}</td>
								<td class="px-2 py-1">{t.title}</td>
								{#if discTracks.length > 0}<td class="px-2 py-1 text-right font-mono text-gray-500 dark:text-gray-400">{fmtSec(discTracks[i]?.expected_duration_seconds)}</td>{/if}
								<td class="px-2 py-1 text-right">{fmtMs(t.length_ms)}</td>
								{#if discTracks.length > 0}<td class="px-2 py-1 text-center {MATCH_CLASS[kind]}" title={kind}>{MATCH_GLYPH[kind]}</td>{/if}
							</tr>
						{/each}
					</tbody>
					{#if discTracks.length > 0}
						{@const totalKind = matchIndicator(mbTotalMs, discTotalSec)}
						<tfoot class="border-t border-gray-200 bg-page font-medium dark:border-gray-600 dark:bg-primary/5">
							<tr>
								<td class="px-2 py-1">Total</td>
								<td class="px-2 py-1"></td>
								<td class="px-2 py-1 text-right font-mono">{fmtSec(discTotalSec)}</td>
								<td class="px-2 py-1 text-right font-mono">{fmtMs(mbTotalMs)}</td>
								<td class="px-2 py-1 text-center {MATCH_CLASS[totalKind]}" title={totalKind}>{MATCH_GLYPH[totalKind]}</td>
							</tr>
						</tfoot>
					{/if}
				</table>
			</div>

			<!-- Editable fields -->
			<div class="grid grid-cols-2 gap-2">
				<label class="col-span-2"><span class="mb-0.5 block text-[10px] text-gray-500">Album</span><input bind:value={editAlbum} class="w-full {inputBase}" /></label>
				<label><span class="mb-0.5 block text-[10px] text-gray-500">Artist</span><input bind:value={editArtist} class="w-full {inputBase}" /></label>
				<label><span class="mb-0.5 block text-[10px] text-gray-500">Year</span><input bind:value={editYear} class="w-full {inputBase}" /></label>
				<label><span class="mb-0.5 block text-[10px] text-gray-500">Disc #</span><input bind:value={discNumber} placeholder="—" class="w-full {inputBase}" /></label>
				<label><span class="mb-0.5 block text-[10px] text-gray-500">Disc total</span><input bind:value={discTotal} placeholder="—" class="w-full {inputBase}" /></label>
			</div>

			{#if confirmMismatch}
				<div class="flex flex-wrap items-center gap-2 rounded-md border border-red-300 bg-red-50 p-2 text-xs text-red-700 dark:border-red-700 dark:bg-red-900/20 dark:text-red-400">
					<span class="flex-1">⚠ Total length differs — likely the wrong release</span>
					<button
						onclick={() => {
							mismatchConfirmed = true;
							confirmMismatch = false;
							applyRelease();
						}}
						class="{btnBase} bg-red-600 text-white hover:bg-red-700"
					>
						Apply anyway
					</button>
					<button onclick={() => (confirmMismatch = false)} class="{btnBase} text-gray-600 hover:text-gray-800 dark:text-gray-400">
						Cancel
					</button>
				</div>
			{/if}

			{#if mappingPreview}
				<div class="space-y-2 rounded-md border border-primary/30 bg-primary/5 p-2 text-xs dark:border-primary/30 dark:bg-primary/10">
					<p class="font-medium text-gray-700 dark:text-gray-300">Confirm track title mapping</p>
					<div class="overflow-x-auto rounded border border-primary/15 dark:border-primary/20">
						<table class="w-full text-left">
							<tbody class="divide-y divide-gray-200 dark:divide-gray-700">
								{#each trackMapping as p}
									<tr>
										<td class="px-2 py-1 whitespace-nowrap font-mono text-gray-500 dark:text-gray-400">Disc #{p.disc.index} ({fmtSec(p.disc.expected_duration_seconds)})</td>
										<td class="px-2 py-1 text-center text-gray-400">→</td>
										<td class="px-2 py-1 text-gray-700 dark:text-gray-300">{p.mb.title}</td>
										<td class="px-2 py-1 text-right font-mono text-gray-500 dark:text-gray-400">{fmtMs(p.mb.length_ms)}</td>
										<td class="px-2 py-1 text-center {MATCH_CLASS[p.match]}" title={p.match}>{MATCH_GLYPH[p.match]}</td>
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
							class="{btnBase} bg-green-600 text-white hover:bg-green-700 dark:bg-green-500"
						>
							Apply titles
						</button>
						<button onclick={() => (mappingPreview = false)} class="{btnBase} text-gray-600 hover:text-gray-800 dark:text-gray-400">
							Cancel
						</button>
					</div>
				</div>
			{/if}

			<div class="flex items-center gap-2">
				{#if $isAdmin}
					<button onclick={applyRelease} disabled={applying || !editAlbum.trim()} class="{btnBase} bg-green-600 text-white hover:bg-green-700 dark:bg-green-500">
						{applying ? 'Applying...' : 'Apply'}
					</button>
				{/if}
				{#if feedback}
					<span class="text-xs {feedback.type === 'success' ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}">{feedback.message}</span>
				{/if}
			</div>
		</div>
	{/if}
</div>
